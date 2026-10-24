from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
from PIL import Image

from backend.demo_catalog import CatalogConflict, DemoCatalog
from backend.demo_catalog_api import create_demo_catalog_router


class ProductManagementTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'catalog.db'
        self.store = DemoCatalog(self.path, 3, 'test')
        self.red = Image.new('RGB', (12, 12), 'red')
        self.blue = Image.new('RGB', (12, 12), 'blue')
        self.encode = lambda image: [1, 0, 0] if image.getpixel((0, 0))[0] else [0, 0, 1]
        self.pid = self.store.add('original', [self.red, self.blue], self.encode)['product_id']

    def product(self):
        return next(p for p in self.store.list_products() if p['product_id'] == self.pid)

    def dump(self):
        with self.store.connect() as db:
            return list(db.iterdump())

    def test_reorder_photos_and_edit_price_without_reencoding(self):
        before = self.product(); order = [p['image_id'] for p in reversed(before['images'])]
        with self.store.connect() as db:
            photos = db.execute('SELECT id,photo,vector FROM images ORDER BY id').fetchall()
        def no_encoding(image):
            self.fail('Existing photo must not be re-encoded')
        updated = self.store.save(self.pid, 'updated', order, [], no_encoding,
                                  price='12000.50', currency='YER', expected_revision=1)
        self.assertEqual(updated['price'], '12000.50')
        self.assertEqual([p['image_id'] for p in self.product()['images']], order)
        self.assertEqual(self.product()['revision'], 2)
        with self.store.connect() as db:
            self.assertEqual(photos, db.execute('SELECT id,photo,vector FROM images ORDER BY id').fetchall())
        reopened = DemoCatalog(self.path, 3, 'test')
        self.assertEqual(reopened.list_products()[0], self.product())

    def test_new_cover_and_removal_are_reflected_in_search(self):
        original = self.product()['images']
        order = ['new:0', original[1]['image_id']]
        self.store.save(self.pid, 'new cover', order, [self.blue], self.encode, available=False)
        after = self.product()
        self.assertNotEqual(after['images'][0]['image_id'], original[0]['image_id'])
        self.assertEqual(after['images'][1], original[1])
        with self.assertRaises(KeyError): self.store.image_bytes(original[0]['image_id'])
        self.assertEqual(self.store.search([1, 0, 0]), [])
        self.store.update(self.pid, 'available', available=True)
        self.assertEqual(len(self.store.search([0, 0, 1])[0]['images']), 2)

    def test_invalid_photo_orders_do_not_change_any_data(self):
        ids = [p['image_id'] for p in self.product()['images']]
        other = self.store.add('other', [self.red], self.encode)['product_id']
        foreign = next(p for p in self.store.list_products() if p['product_id']==other)['images'][0]['image_id']
        before = self.dump()
        for order, images in [([], []), ([ids[0]]*2, []), ([foreign], []),
                              (['new:1'], [self.red]), ([ids[0]], [self.red]),
                              (['new:'+str(i) for i in range(6)], [self.red]*6),
                              ([{}], []), ('invalid', [])]:
            with self.subTest(order=order), self.assertRaises(ValueError):
                self.store.save(self.pid, 'must not change', order, images, self.encode)
            self.assertEqual(self.dump(), before)

    def test_failed_new_image_encoding_rolls_back_details_and_removals(self):
        before = self.dump(); calls = []
        def fail_second(image):
            calls.append(image)
            if len(calls)==2: raise RuntimeError('encoder unavailable')
            return [1, 0, 0]
        with self.assertRaises(RuntimeError):
            self.store.save(self.pid, 'new', ['new:0','new:1'], [self.red,self.blue], fail_second)
        self.assertEqual(before, self.dump())

    def test_stale_save_and_delete_leave_newer_product_untouched(self):
        order = [p['image_id'] for p in self.product()['images']]
        self.store.update(self.pid, 'newer', price='50')
        before = self.dump()
        with self.assertRaises(CatalogConflict):
            self.store.save(self.pid, 'stale', order, [], self.encode, expected_revision=1)
        with self.assertRaises(CatalogConflict): self.store.delete(self.pid, expected_revision=1)
        self.assertEqual(before, self.dump())

    def test_update_during_encoding_cannot_be_overwritten(self):
        def concurrent_update(image):
            self.store.update(self.pid, 'concurrent', price='70')
            return self.encode(image)
        with self.assertRaises(CatalogConflict):
            self.store.save(self.pid, 'stale', ['new:0'], [self.red], concurrent_update)
        self.assertEqual(self.product()['name'], 'concurrent')
        self.assertEqual(len(self.product()['images']), 2)

    def test_delete_removes_photos_vectors_and_preserves_other_products(self):
        self.store.add('other', [self.blue], self.encode)
        original = self.product(); result = self.store.delete(self.pid, expected_revision=1)
        self.assertEqual(result['deleted_image_count'], 2)
        self.assertEqual([p['name'] for p in self.store.list_products()], ['other'])
        self.assertEqual([p['name'] for p in self.store.search([1, 0, 0])], ['other'])
        for photo in original['images']:
            with self.assertRaises(KeyError): self.store.image_bytes(photo['image_id'])
        with self.store.connect() as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        with self.assertRaises(KeyError): self.store.delete(self.pid)


class ProductManagementAPITests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        engine = SimpleNamespace(index=SimpleNamespace(d=3), _index_lock=threading.RLock(),
                                 encode_image=lambda image: np.array([[1, 0, 0]], dtype=np.float32))
        app = FastAPI(); app.include_router(create_demo_catalog_router(engine, Path(temp.name)/'catalog.db'))
        self.client = TestClient(app); self.addCleanup(self.client.close)
        stream = BytesIO(); Image.new('RGB', (12, 12), 'red').save(stream, format='PNG'); self.photo=stream.getvalue()
        self.pid = self.client.post('/api/demo-catalog/products', data={'name':'initial'}, files={'images':('a.png',self.photo,'image/png')}).json()['product_id']
        self.url = '/api/demo-catalog/products/'+self.pid

    def product(self): return self.client.get('/api/demo-catalog/products').json()['products'][0]

    def payload(self):
        p = self.product()
        return dict(name='updated', price='42.25', currency='SAR', category='dress',
                    available='true', revision=str(p['revision']),
                    image_order=json.dumps([i['image_id'] for i in p['images']]))

    def test_edit_add_photos_change_cover_and_search_updated_price(self):
        old = self.product()['images'][0]['image_id']; data=self.payload()
        data['image_order']=json.dumps(['new:0', old])
        response=self.client.put(self.url+'/content',data=data,files={'images':('b.png',self.photo,'image/png')})
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(self.product()['images'][0]['image_id'], old)
        result=self.client.post('/api/demo-catalog/search',files={'image':('q.png',self.photo,'image/png')}).json()['results'][0]
        self.assertEqual((result['name'],result['price'],result['currency']),('updated','42.25','SAR'))
        self.assertEqual(len(result['images']),2)

    def test_edit_without_new_uploads_preserves_photos_and_can_clear_price(self):
        old=self.product()['images'];data=self.payload();data['price']=''
        self.assertEqual(self.client.put(self.url+'/content',data=data).status_code,200)
        self.assertIsNone(self.product()['price']);self.assertEqual(self.product()['images'],old)

    def test_invalid_image_or_order_does_not_partially_save(self):
        before=self.product(); data=self.payload()
        data['image_order']='["new:0"]'
        response=self.client.put(self.url+'/content',data=data,files={'images':('bad.png',b'broken','image/png')})
        self.assertEqual(response.status_code,400);self.assertEqual(self.product(),before)
        for order in ['null','{}','not-json','[]','["foreign"]']:
            data=self.payload();data['image_order']=order
            self.assertEqual(self.client.put(self.url+'/content',data=data).status_code,400)
            self.assertEqual(self.product(),before)

    def test_stale_revision_is_conflict_for_save_and_delete(self):
        stale=self.payload()
        self.assertEqual(self.client.put(self.url+'/content',data=self.payload()).status_code,200)
        before=self.product()
        self.assertEqual(self.client.put(self.url+'/content',data=stale).status_code,409)
        self.assertEqual(self.client.delete(self.url+'?revision=1').status_code,409)
        self.assertEqual(self.product(),before)

    def test_delete_cleans_up_image_routes_and_search(self):
        photo_url=self.product()['images'][0]['url']
        self.assertEqual(self.client.delete(self.url+'?revision=1').status_code,200)
        self.assertEqual(self.client.get(photo_url).status_code,404)
        self.assertEqual(self.client.get('/api/demo-catalog/products').json()['products'],[])
        response=self.client.post('/api/demo-catalog/search',files={'image':('q.png',self.photo,'image/png')})
        self.assertEqual(response.json()['results'],[])
        self.assertEqual(self.client.delete(self.url+'?revision=1').status_code,404)

    def test_save_requires_revision_and_rejects_invalid_price(self):
        data=self.payload();data.pop('revision')
        self.assertEqual(self.client.put(self.url+'/content',data=data).status_code,422)
        data=self.payload();data['price']='-1'
        self.assertEqual(self.client.put(self.url+'/content',data=data).status_code,400)
