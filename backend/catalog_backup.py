"""Bounded, portable product backups and transactional, previewed restoration.

Only declarative JSON, JPEGs and little-endian float32 vectors cross this
boundary. Uploaded SQLite databases are never opened and archives never extract
files. Authentication data and the original research catalog are outside scope.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import threading
import time
from uuid import UUID, uuid4
import zipfile
import zlib

import numpy as np
from PIL import Image

from backend.request_validation import validate_image_bytes

MAX_BACKUP_BYTES = 200 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_PHOTO_BYTES = 32 * 1024 * 1024
MAX_PRODUCTS = 10_000
MAX_IMAGES = MAX_PRODUCTS * 5
PREVIEW_SECONDS = 600
FORMAT = 'fashion-search-added-catalog'
MAX_REVISION = 2**53 - 2


class BackupError(ValueError):
    def __init__(self, code='backup_invalid', status=400):
        self.code, self.status = code, status
        super().__init__(code)


@dataclass
class ValidatedBackup:
    created_at: str
    products: list
    images: list


def digest(content):
    return hashlib.sha256(content).hexdigest()


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BackupError()
        result[key] = value
    return result


def valid_id(value):
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


class CatalogBackups:
    def __init__(self, store, *, clock=time.time, backup_directory=None):
        self.store = store
        self.clock = clock
        self.backup_directory = Path(backup_directory or store.database.parent/'backups')
        self.preview_lock = threading.RLock()
        self.previews = {}
        self.preview_serial = 0
        # A generation survives empty restores, preventing stale editor revisions
        # from becoming valid again after a product disappears and reappears.
        with store.lock, store.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS catalog_backup_state (
                id INTEGER PRIMARY KEY CHECK(id=1), restore_revision INTEGER NOT NULL)''')
            db.execute('INSERT OR IGNORE INTO catalog_backup_state VALUES (1,0)')

    def _snapshot(self, db):
        return {
            'signature':db.execute('SELECT signature FROM config').fetchone()[0],
            'generation':db.execute('SELECT restore_revision FROM catalog_backup_state WHERE id=1').fetchone()[0],
            'products':db.execute('SELECT id,name,category,price,currency,available,revision FROM products ORDER BY rowid').fetchall(),
            'images':db.execute('SELECT id,product_id,photo,vector,position FROM images ORDER BY rowid').fetchall(),
        }

    def snapshot(self):
        with self.store.lock, self.store.connect() as db:
            db.execute('BEGIN')
            return self._snapshot(db)

    @staticmethod
    def fingerprint(snapshot):
        state = hashlib.sha256()
        def add(value):
            data = json.dumps(value,ensure_ascii=False,separators=(',',':')).encode('utf-8')
            state.update(len(data).to_bytes(8,'big')); state.update(data)
        add([snapshot['signature'],snapshot['generation']])
        for row in snapshot['products']:
            add(list(row))
        for iid,pid,photo,vector,position in snapshot['images']:
            add([iid,pid,digest(photo),digest(vector),position])
        return state.hexdigest()

    def _archive(self, snapshot):
        created_at = datetime.fromtimestamp(self.clock(),timezone.utc).isoformat()
        products = [dict(zip(('id','name','category','price','currency','available','revision'),row))
                    for row in snapshot['products']]
        for item in products:
            item['available'] = bool(item['available'])
        # The first schema migration gave every old photo position=0. Serialize
        # the same logical ordering as list_products (position, then rowid),
        # without repairing or otherwise mutating the source database.
        grouped = {}
        for source_order,row in enumerate(snapshot['images']):
            grouped.setdefault(row[1],[]).append((row[4],source_order,row[0]))
        logical_positions = {iid:position for rows in grouped.values()
                             for position,(_,_,iid) in enumerate(sorted(rows))}
        images = []
        for iid,pid,photo,vector,position in snapshot['images']:
            images.append({'id':iid,'product_id':pid,'position':logical_positions[iid],
                           'photo':f'images/{iid}.jpg','vector':f'vectors/{iid}.f32',
                           'photo_sha256':digest(photo),'vector_sha256':digest(vector)})
        manifest = {'format':FORMAT,'version':1,'created_at':created_at,
                    'encoder':json.loads(snapshot['signature']), 'products':products,'images':images}
        content = json.dumps(manifest,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        total = len(content)+sum(len(row[2])+len(row[3]) for row in snapshot['images'])
        if (len(content)>MAX_MANIFEST_BYTES or total>MAX_BACKUP_BYTES
                or len(products)>MAX_PRODUCTS or len(images)>MAX_IMAGES):
            raise BackupError('backup_too_large',413)
        stream = BytesIO()
        with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            archive.writestr('manifest.json',content)
            for iid,_,photo,vector,_ in snapshot['images']:
                archive.writestr(f'images/{iid}.jpg',photo)
                archive.writestr(f'vectors/{iid}.f32',vector)
                if stream.tell()>MAX_BACKUP_BYTES:
                    raise BackupError('backup_too_large',413)
        content = stream.getvalue()
        if len(content)>MAX_BACKUP_BYTES:
            raise BackupError('backup_too_large',413)
        return content, manifest

    def export(self):
        return self._archive(self.snapshot())[0]

    @staticmethod
    def _read_entry(archive, name, limit):
        info = archive.getinfo(name)
        if info.file_size>limit:
            raise BackupError('backup_too_large',413)
        with archive.open(info) as entry:
            content = entry.read(limit+1)
        if len(content)>limit:
            raise BackupError('backup_too_large',413)
        if len(content)!=info.file_size:
            raise BackupError()
        return content

    def validate(self, content):
        if not isinstance(content,bytes) or not content:
            raise BackupError()
        if len(content)>MAX_BACKUP_BYTES:
            raise BackupError('backup_too_large',413)
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                names = [entry.filename for entry in entries]
                if (len(entries)>1+2*MAX_IMAGES or len(set(names))!=len(names)
                        or 'manifest.json' not in names):
                    raise BackupError()
                if sum(entry.file_size for entry in entries)>MAX_BACKUP_BYTES:
                    raise BackupError('backup_too_large',413)
                for entry in entries:
                    if (entry.is_dir() or entry.flag_bits&1
                            or stat.S_ISLNK(entry.external_attr>>16)
                            or entry.compress_type not in {zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED}
                            or entry.file_size>max(entry.compress_size,1)*1000):
                        raise BackupError()
                raw = self._read_entry(archive,'manifest.json',MAX_MANIFEST_BYTES)
                manifest = json.loads(raw,object_pairs_hook=strict_object,
                                      parse_constant=lambda _: (_ for _ in ()).throw(BackupError()))
                if (not isinstance(manifest,dict) or set(manifest)!=
                        {'format','version','created_at','encoder','products','images'}
                        or manifest['format']!=FORMAT or type(manifest['version']) is not int
                        or manifest['version']!=1):
                    raise BackupError()
                with self.store.lock, self.store.connect() as db:
                    expected = json.loads(db.execute('SELECT signature FROM config').fetchone()[0])
                encoder = manifest['encoder']
                if (not isinstance(encoder,dict) or set(encoder)!={'dimension','encoder'}
                        or type(encoder['dimension']) is not int or not isinstance(encoder['encoder'],str)
                        or encoder!=expected):
                    raise BackupError('backup_incompatible')
                created_at = manifest['created_at']
                if not isinstance(created_at,str) or len(created_at)>40:
                    raise BackupError()
                if datetime.fromisoformat(created_at).utcoffset() is None:
                    raise BackupError()
                products, image_items = manifest['products'], manifest['images']
                if (not isinstance(products,list) or not isinstance(image_items,list)
                        or len(products)>MAX_PRODUCTS or len(image_items)>MAX_IMAGES):
                    raise BackupError()
                product_rows, product_ids = [], set()
                for item in products:
                    if (not isinstance(item,dict) or set(item)!=
                            {'id','name','category','price','currency','available','revision'}
                            or not valid_id(item['id']) or item['id'] in product_ids
                            or not isinstance(item['name'],str) or not isinstance(item['category'],str)
                            or not isinstance(item['currency'],str)
                            or item['price'] is not None and not isinstance(item['price'],str)
                            or type(item['available']) is not bool
                            or type(item['revision']) is not int or not 1<=item['revision']<=MAX_REVISION):
                        raise BackupError()
                    fields = self.store.details(item['name'],item['category'],item['price'],item['currency'],item['available'])
                    if any(item[key]!=fields[key] for key in fields):
                        raise BackupError()
                    product_ids.add(item['id'])
                    product_rows.append((item['id'],item['name'],item['category'],item['price'],item['currency'],int(item['available']),item['revision']))
                allowed = {'manifest.json'}
                image_rows, image_ids, positions = [], set(), {pid:[] for pid in product_ids}
                for item in image_items:
                    if (not isinstance(item,dict) or set(item)!=
                            {'id','product_id','position','photo','vector','photo_sha256','vector_sha256'}
                            or not valid_id(item['id']) or item['id'] in image_ids
                            or item['product_id'] not in product_ids
                            or type(item['position']) is not int or not 0<=item['position']<5
                            or item['photo']!=f"images/{item['id']}.jpg"
                            or item['vector']!=f"vectors/{item['id']}.f32"):
                        raise BackupError()
                    for field in ('photo_sha256','vector_sha256'):
                        if not isinstance(item[field],str) or not re.fullmatch('[0-9a-f]{64}',item[field]):
                            raise BackupError()
                    photo = self._read_entry(archive,item['photo'],MAX_PHOTO_BYTES)
                    vector = self._read_entry(archive,item['vector'],self.store.dimension*4)
                    if (digest(photo)!=item['photo_sha256'] or digest(vector)!=item['vector_sha256']
                            or len(vector)!=self.store.dimension*4):
                        raise BackupError()
                    with Image.open(BytesIO(photo)) as probe:
                        if probe.format!='JPEG': raise BackupError()
                    validate_image_bytes(photo,'image/jpeg',max_bytes=MAX_PHOTO_BYTES)
                    values = np.frombuffer(vector,dtype='<f4')
                    if (not np.isfinite(values).all()
                            or abs(float(np.linalg.norm(values.astype('float64')))-1)>1e-4):
                        raise BackupError()
                    image_ids.add(item['id']); allowed.update((item['photo'],item['vector']))
                    positions[item['product_id']].append(item['position'])
                    image_rows.append((item['id'],item['product_id'],photo,vector,item['position']))
                if set(names)!=allowed or any(sorted(items)!=list(range(len(items)))
                                              or not 1<=len(items)<=5 for items in positions.values()):
                    raise BackupError()
                return ValidatedBackup(created_at,product_rows,image_rows)
        except BackupError:
            raise
        except (ValueError,KeyError,TypeError,OverflowError,OSError,RuntimeError,zipfile.BadZipFile,NotImplementedError,zlib.error) as error:
            raise BackupError() from error

    def preview(self, content, owner):
        # Register request order before validation, which may be slow for a
        # large upload. An older validation must not evict a newer preview.
        with self.preview_lock:
            self.preview_serial += 1
            serial = self.preview_serial
        validated = self.validate(content)
        snapshot = self.snapshot()
        token = secrets.token_urlsafe(32)
        owner_hash = digest(owner.encode('utf-8'))
        with self.preview_lock:
            if serial != self.preview_serial:
                raise BackupError('restore_preview_expired',409)
            # Keep a single pending upload, so repeated previews cannot retain
            # unbounded copies of 200 MiB archives in server memory.
            self.previews.clear()
            self.previews[token] = (self.clock()+PREVIEW_SECONDS,owner_hash,
                                    self.fingerprint(snapshot),validated)
        return {'token':token,'product_count':len(validated.products),'image_count':len(validated.images),
                'current_product_count':len(snapshot['products']),'current_image_count':len(snapshot['images']),
                'created_at':validated.created_at,'expires_in_seconds':PREVIEW_SECONDS}

    def _save_recovery(self, snapshot):
        content, manifest = self._archive(snapshot)
        self.backup_directory.mkdir(parents=True,exist_ok=True)
        backup_id = uuid4().hex
        target = self.backup_directory/(backup_id+'.fashion-catalog.zip')
        temporary = target.with_suffix('.tmp')
        try:
            with temporary.open('xb') as stream:
                stream.write(content); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary,target)
        finally:
            temporary.unlink(missing_ok=True)
        return backup_id

    def restore(self, token, owner):
        with self.preview_lock:
            pending = self.previews.get(token) if isinstance(token,str) else None
            if (not pending or pending[0]<=self.clock()
                    or not hmac.compare_digest(pending[1],digest(owner.encode('utf-8')))):
                raise BackupError('restore_preview_expired',409)
            _,_,expected,validated = pending
            with self.store.lock, self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                snapshot = self._snapshot(db)
                if self.fingerprint(snapshot)!=expected:
                    self.previews.pop(token,None)
                    raise BackupError('catalog_changed',409)
                backup_id = self._save_recovery(snapshot)
                revision = max([int(self.clock()*1_000_000),snapshot['generation']+1]
                               +[row[6]+1 for row in snapshot['products']]
                               +[row[6]+1 for row in validated.products])
                if revision>MAX_REVISION:
                    raise BackupError('restore_failed',500)
                db.execute('DELETE FROM images'); db.execute('DELETE FROM products')
                db.executemany('INSERT INTO products (id,name,category,price,currency,available,revision) VALUES (?,?,?,?,?,?,?)',
                               [(*row[:6],revision) for row in validated.products])
                db.executemany('INSERT INTO images (id,product_id,photo,vector,position) VALUES (?,?,?,?,?)',validated.images)
                db.execute('UPDATE catalog_backup_state SET restore_revision=? WHERE id=1',(revision,))
                if db.execute('PRAGMA foreign_key_check').fetchone():
                    raise BackupError('restore_failed',500)
            self.previews.clear()
        return {'restored':True,'product_count':len(validated.products),'image_count':len(validated.images),
                'recovery_backup_url':'/api/demo-catalog/products/recovery/'+backup_id}

    def recovery_path(self, backup_id):
        if not isinstance(backup_id,str) or not re.fullmatch('[a-f0-9]{32}',backup_id):
            raise BackupError('recovery_not_found',404)
        base = self.backup_directory.resolve()
        path = self.backup_directory/(backup_id+'.fashion-catalog.zip')
        if not path.is_file() or not path.resolve().is_relative_to(base):
            raise BackupError('recovery_not_found',404)
        if path.stat().st_size>MAX_BACKUP_BYTES:
            raise BackupError('recovery_not_found',404)
        return path

    def list_recovery(self):
        if not self.backup_directory.is_dir():
            return []
        candidates = sorted(self.backup_directory.glob('*.fashion-catalog.zip'),
                            key=lambda p:p.stat().st_mtime,reverse=True)
        backups = []
        for path in candidates:
            backup_id = path.name.removesuffix('.fashion-catalog.zip')
            try:
                path = self.recovery_path(backup_id)
                with zipfile.ZipFile(path) as archive:
                    raw = self._read_entry(archive,'manifest.json',MAX_MANIFEST_BYTES)
                    manifest = json.loads(raw,object_pairs_hook=strict_object)
                if manifest.get('format')!=FORMAT or manifest.get('version')!=1:
                    continue
                backups.append({'backup_id':backup_id,'created_at':manifest['created_at'],
                                'product_count':len(manifest['products']),'image_count':len(manifest['images']),
                                'download_url':'/api/demo-catalog/products/recovery/'+backup_id,
                                'byte_size':path.stat().st_size})
            except (BackupError,ValueError,KeyError,TypeError,OSError,zipfile.BadZipFile):
                continue
            if len(backups)==20:
                break
        return backups
