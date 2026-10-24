"""Local product catalog with transactional photo management and retrieval."""
from contextlib import contextmanager
from io import BytesIO
import json
import re
from decimal import Decimal
from backend.category_routing import CATEGORY_LABELS, normalize_category
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4
import faiss
import numpy as np


class CatalogConflict(ValueError):
    """The product changed after the editor loaded it."""


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
            columns = {r[1] for r in db.execute('PRAGMA table_info(products)')}
            for name, declaration in [('category', "TEXT NOT NULL DEFAULT ''"), ('price', 'TEXT'), ('currency', "TEXT NOT NULL DEFAULT 'YER'"), ('available', 'INTEGER NOT NULL DEFAULT 1'), ('revision', 'INTEGER NOT NULL DEFAULT 1')]:
                if name not in columns:
                    db.execute(f'ALTER TABLE products ADD COLUMN {name} {declaration}')
            image_columns = {r[1] for r in db.execute('PRAGMA table_info(images)')}
            if 'position' not in image_columns:
                db.execute('ALTER TABLE images ADD COLUMN position INTEGER NOT NULL DEFAULT 0')

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

    @staticmethod
    def details(name, category='', price=None, currency='YER', available=True):
        name = name.strip()
        if not name or len(name) > 120:
            raise ValueError('Product name must contain 1 to 120 characters')
        if category and category not in CATEGORY_LABELS:
            raise ValueError('Unsupported product category')
        if currency not in {'YER', 'SAR', 'USD'}:
            raise ValueError('Unsupported currency')
        if type(available) is not bool:
            raise ValueError('Availability must be true or false')
        price = None if price is None or price == '' else str(price).strip()
        if price is not None:
            if not re.fullmatch(r'[0-9]{1,9}(?:\.[0-9]{1,2})?', price):
                raise ValueError('Price must be non-negative with at most two decimal places')
            price = format(Decimal(price), '.2f')
        return {'name':name, 'category':category, 'price':price, 'currency':currency, 'available':available}

    def prepare_images(self, images, encode):
        """Encode all new images before changing stored product data."""
        prepared = []
        for image in images:
            vector = self.vector(encode(image))
            stream = BytesIO()
            image.convert('RGB').save(stream, format='JPEG', quality=95)
            prepared.append((str(uuid4()), stream.getvalue(), vector.tobytes()))
        return prepared

    def add(self, name, images, encode, category='', price=None, currency='YER', available=True):
        details = self.details(name, category, price, currency, available)
        if not 1 <= len(images) <= 5:
            raise ValueError('Upload 1 to 5 images for one product')
        prepared = self.prepare_images(images, encode)
        pid = str(uuid4())
        with self.lock, self.connect() as db:
            db.execute('INSERT INTO products (id,name,category,price,currency,available) VALUES (?,?,?,?,?,?)', (pid,details['name'],category,details['price'],currency,int(available)))
            db.executemany('INSERT INTO images (id,product_id,photo,vector,position) VALUES (?,?,?,?,?)', [(iid,pid,photo,vector,position) for position,(iid,photo,vector) in enumerate(prepared)])
        return dict(details, product_id=pid, image_count=len(prepared), revision=1)

    @staticmethod
    def image_info(iid):
        return {'image_id':iid, 'url':'/api/demo-catalog/images/' + iid}

    def list_products(self):
        with self.lock, self.connect() as db:
            products = db.execute('SELECT id,name,category,price,currency,available,revision FROM products ORDER BY rowid DESC').fetchall()
            images = db.execute('SELECT id,product_id FROM images ORDER BY position,rowid').fetchall()
        grouped = {}
        for iid, pid in images:
            grouped.setdefault(pid, []).append(self.image_info(iid))
        return [{'product_id':pid,'name':name,'category':category,'price':price,'currency':currency,'available':bool(available),'revision':revision,'images':grouped.get(pid, [])} for pid,name,category,price,currency,available,revision in products]

    def update(self, pid, name, category='', price=None, currency='YER', available=True):
        details = self.details(name, category, price, currency, available)
        with self.lock, self.connect() as db:
            cursor = db.execute('UPDATE products SET name=?,category=?,price=?,currency=?,available=?,revision=revision+1 WHERE id=?', (details['name'],category,details['price'],currency,int(available),pid))
            if cursor.rowcount != 1:
                raise KeyError(pid)
        return dict(details, product_id=pid)

    @staticmethod
    def check_revision(actual, expected):
        if expected is not None and actual != expected:
            raise CatalogConflict('Product changed; refresh the catalog before saving or deleting')

    def save(self, pid, name, image_order, images, encode, category='', price=None,
             currency='YER', available=True, expected_revision=None):
        """Save details and photo changes in one transaction.

        Image order contains retained image IDs and new:0, new:1, etc. The first
        entry is the cover. Existing photos and embeddings are never re-encoded.
        """
        details = self.details(name, category, price, currency, available)
        with self.lock, self.connect() as db:
            row = db.execute('SELECT revision FROM products WHERE id=?', (pid,)).fetchone()
            if not row:
                raise KeyError(pid)
            revision = row[0]
            self.check_revision(revision, expected_revision)
            existing = {r[0] for r in db.execute('SELECT id FROM images WHERE product_id=?', (pid,))}
        if (not isinstance(image_order, list) or not 1 <= len(image_order) <= 5
                or not all(isinstance(i, str) for i in image_order)
                or len(set(image_order)) != len(image_order)):
            raise ValueError('Keep 1 to 5 unique images for the product')
        new_keys = {f'new:{i}' for i in range(len(images))}
        if set(image_order) - existing != new_keys:
            raise ValueError('Image order contains an unknown image or an unused upload')
        prepared = self.prepare_images(images, encode)
        new_ids = {f'new:{i}': item[0] for i, item in enumerate(prepared)}
        ordered = [new_ids.get(key, key) for key in image_order]
        retained = existing.intersection(image_order)
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision FROM products WHERE id=?', (pid,)).fetchone()
            if not row:
                raise KeyError(pid)
            self.check_revision(row[0], revision)
            for iid in existing - retained:
                db.execute('DELETE FROM images WHERE id=? AND product_id=?', (iid, pid))
            db.executemany('INSERT INTO images (id,product_id,photo,vector) VALUES (?,?,?,?)',
                           [(iid,pid,photo,vector) for iid,photo,vector in prepared])
            db.executemany('UPDATE images SET position=? WHERE id=? AND product_id=?',
                           [(position,iid,pid) for position,iid in enumerate(ordered)])
            db.execute('UPDATE products SET name=?,category=?,price=?,currency=?,available=?,revision=revision+1 WHERE id=?',
                       (details['name'], category, details['price'], currency, int(available), pid))
        return dict(details, product_id=pid, image_count=len(ordered), revision=revision+1,
                    images=[self.image_info(iid) for iid in ordered])

    def delete(self, pid, expected_revision=None):
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT revision FROM products WHERE id=?', (pid,)).fetchone()
            if not row:
                raise KeyError(pid)
            self.check_revision(row[0], expected_revision)
            removed = db.execute('DELETE FROM images WHERE product_id=?', (pid,)).rowcount
            db.execute('DELETE FROM products WHERE id=?', (pid,))
        return {'product_id': pid, 'deleted': True, 'deleted_image_count': removed}

    def image_bytes(self, iid):
        with self.lock, self.connect() as db:
            row = db.execute('SELECT photo FROM images WHERE id=?', (iid,)).fetchone()
        if not row:raise KeyError(iid)
        return row[0]

    def search(self, raw_vector, top_k=8, category=''):
        return self.search_with_routing(raw_vector, top_k, category)[0]

    def search_with_routing(self, raw_vector, top_k=8, category=''):
        if not 1 <= top_k <= 50:raise ValueError('top_k must be between 1 and 50')
        requested = normalize_category(category or 'all')
        query = self.vector(raw_vector)
        with self.lock, self.connect() as db:
            rows = db.execute('SELECT images.id,products.id,products.name,images.vector,products.category,products.price,products.currency FROM images JOIN products ON products.id=images.product_id WHERE products.available=1 ORDER BY images.rowid').fetchall()
        routing = {'requested_category': requested, 'applied_category': None,
                   'applied_label': None, 'predicted_category': None, 'fallback_reason': None}
        applied = None if requested in {'auto', 'all'} else requested
        if requested == 'auto':
            applied, prediction = self.automatic_category(query, rows)
            routing.update(prediction)
        routing.update(applied_category=applied, applied_label=CATEGORY_LABELS.get(applied))
        if applied:
            rows = [row for row in rows if row[4] == applied]
        if not rows:return [], routing
        vectors = np.stack([self.vector(np.frombuffer(row[3], dtype=np.float32)) for row in rows])
        index = faiss.IndexFlatIP(self.dimension)
        index.add(vectors)
        scores, ranks = index.search(query.reshape(1,-1), len(rows))
        results, seen = [], set()
        for score, rank in zip(scores[0],ranks[0]):
            iid,pid,name,_,item_category,price,currency = rows[int(rank)]
            if pid in seen:continue
            seen.add(pid)
            results.append({'product_id':pid,'name':name,'category':item_category,'price':price,'currency':currency,'available':True,'score':float(score),'image_url':self.image_info(iid)['url'],'images':[self.image_info(row[0]) for row in rows if row[1]==pid]})
            if len(results)==top_k:break
        return results, routing


    def automatic_category(self, query, rows):
        """Conservative local routing, using only available added-product embeddings.

        Similarity and margin are heuristic gates, not calibrated probabilities.
        Unknown product categories keep the entire catalog searchable.
        """
        categories = sorted({row[4] for row in rows if row[4]})
        info = {'available_categories': categories, 'fallback_reason': None,
                'predicted_category': None, 'best_similarity': None, 'similarity_margin': None}
        if not rows:
            info['fallback_reason'] = 'empty_catalog'
        elif any(not row[4] for row in rows):
            info['fallback_reason'] = 'uncategorized_products'
        elif len(categories) < 2:
            info['fallback_reason'] = 'insufficient_categories'
        else:
            # Maximum per category: repeated photos do not add votes or alter the margin.
            scores = {category: max(float(np.dot(query, self.vector(np.frombuffer(row[3], dtype=np.float32))))
                                    for row in rows if row[4] == category) for category in categories}
            ranked = sorted(scores, key=lambda key: (-scores[key], key))
            best = ranked[0]
            margin = scores[best] - scores[ranked[1]]
            info.update(predicted_category=best, best_similarity=round(scores[best], 6),
                        similarity_margin=round(margin, 6))
            if scores[best] < 0.55:
                info['fallback_reason'] = 'weak_similarity'
            elif margin < 0.08:
                info['fallback_reason'] = 'ambiguous_categories'
            else:
                return best, info
        return None, info
