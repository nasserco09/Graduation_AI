"""Small local catalog prototype: products own multiple images and embeddings."""
from contextlib import contextmanager
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4
import faiss
import numpy as np


class DemoCatalog:
    def __init__(self, database, dimension, signature):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.dimension = dimension
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript("CREATE TABLE IF NOT EXISTS config (signature TEXT NOT NULL); CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT NOT NULL); CREATE TABLE IF NOT EXISTS images (id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id), photo BLOB NOT NULL, vector BLOB NOT NULL);")
            expected = json.dumps({'dimension': dimension, 'encoder': signature}, sort_keys=True)
            row = db.execute('SELECT signature FROM config').fetchone()
            if row and row[0] != expected:
                raise ValueError('Demo catalog encoder configuration changed; use a separate database')
            if not row:
                db.execute('INSERT INTO config VALUES (?)', (expected,))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                yield db
        finally:
            db.close()

    def vector(self, raw):
        vector = np.asarray(raw, dtype=np.float32).reshape(-1)
        if len(vector) != self.dimension or not np.isfinite(vector).all():
            raise ValueError('Invalid demo catalog embedding')
        norm = np.linalg.norm(vector)
        if not np.isfinite(norm) or norm <= 0:
            raise ValueError('Empty demo catalog embedding')
        return np.ascontiguousarray(vector / norm)

    def add(self, name, images, encode):
        name = name.strip()
        if not name or len(name) > 120:
            raise ValueError('Product name must contain 1 to 120 characters')
        if not 1 <= len(images) <= 5:
            raise ValueError('Upload 1 to 5 images for one product')
        # Complete every embedding before committing any product or image.
        prepared = []
        for image in images:
            vector = self.vector(encode(image))
            stream = BytesIO()
            image.convert('RGB').save(stream, format='JPEG', quality=95)
            prepared.append((str(uuid4()), stream.getvalue(), vector.tobytes()))
        pid = str(uuid4())
        with self.lock, self.connect() as db:
            db.execute('INSERT INTO products VALUES (?,?)', (pid, name))
            db.executemany('INSERT INTO images VALUES (?,?,?,?)', [(iid,pid,photo,vector) for iid,photo,vector in prepared])
        return {'product_id':pid, 'name':name, 'image_count':len(prepared)}

    @staticmethod
    def image_info(iid):
        return {'image_id':iid, 'url':'/api/demo-catalog/images/' + iid}

    def list_products(self):
        with self.lock, self.connect() as db:
            products = db.execute('SELECT id,name FROM products ORDER BY rowid DESC').fetchall()
            images = db.execute('SELECT id,product_id FROM images ORDER BY rowid').fetchall()
        return [{'product_id':pid,'name':name,'images':[self.image_info(iid) for iid,p in images if p==pid]} for pid,name in products]

    def image_bytes(self, iid):
        with self.lock, self.connect() as db:
            row = db.execute('SELECT photo FROM images WHERE id=?', (iid,)).fetchone()
        if not row:raise KeyError(iid)
        return row[0]

    def search(self, raw_vector, top_k=8):
        if not 1 <= top_k <= 50:raise ValueError('top_k must be between 1 and 50')
        query = self.vector(raw_vector)
        with self.lock, self.connect() as db:
            rows = db.execute('SELECT images.id,products.id,products.name,images.vector FROM images JOIN products ON products.id=images.product_id ORDER BY images.rowid').fetchall()
        if not rows:return []
        vectors = np.stack([self.vector(np.frombuffer(row[3], dtype=np.float32)) for row in rows])
        index = faiss.IndexFlatIP(self.dimension)
        index.add(vectors)
        scores, ranks = index.search(query.reshape(1,-1), len(rows))
        results, seen = [], set()
        for score, rank in zip(scores[0],ranks[0]):
            iid,pid,name,_ = rows[int(rank)]
            if pid in seen:continue
            seen.add(pid)
            results.append({'product_id':pid,'name':name,'score':float(score),'image_url':self.image_info(iid)['url'],'images':[self.image_info(row[0]) for row in rows if row[1]==pid]})
            if len(results)==top_k:break
        return results
