from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import unittest
import numpy as np
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.demo_catalog_api import create_demo_catalog_router


class DemoCatalogAPITests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        engine=SimpleNamespace(index=SimpleNamespace(d=3),_index_lock=threading.RLock(),encode_image=lambda image:np.array([[1,0,0]],dtype=np.float32))
        self.engine = engine
        app=FastAPI();app.include_router(create_demo_catalog_router(engine,Path(temp.name)/'catalog.db'))
        self.client=TestClient(app);self.addCleanup(self.client.close)
        stream=BytesIO();Image.new('RGB',(10,10),'red').save(stream,format='PNG');self.photo=stream.getvalue()
        response=self.client.post('/api/demo-catalog/products',data={'name':'initial','category':'outwear','price':'12.50','currency':'SAR'},files={'images':('photo.png',self.photo,'image/png')})
        self.assertEqual(response.status_code,201);self.pid=response.json()['product_id']

    def test_edit_then_search_returns_updated_details_and_availability(self):
        payload=dict(name='updated',category='outwear',price='15',currency='SAR',available=True)
        response=self.client.put('/api/demo-catalog/products/'+self.pid,json=payload)
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['price'],'15.00')
        response=self.client.post('/api/demo-catalog/search',data={'category':'outwear'},files={'image':('q.png',self.photo,'image/png')})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['results'][0]['name'],'updated')
        payload['available']=False
        self.assertEqual(self.client.put('/api/demo-catalog/products/'+self.pid,json=payload).status_code,200)
        response=self.client.post('/api/demo-catalog/search',files={'image':('q.png',self.photo,'image/png')})
        self.assertEqual(response.json()['results'],[])
        self.assertEqual(len(self.client.get('/api/demo-catalog/products').json()['products']),1)

    def test_transparent_query_reaches_encoder_on_white_background(self):
        import hashlib
        captured = []
        def capture(image):
            captured.append(image.copy())
            return np.array([[1, 0, 0]], dtype=np.float32)
        self.engine.encode_image = capture
        source = Image.new('RGBA', (10, 10), (0, 0, 0, 0))
        source.putpixel((5, 5), (255, 0, 0, 255))
        stream = BytesIO(); source.save(stream, format='PNG')
        content = stream.getvalue()
        response = self.client.post('/api/demo-catalog/search', files={'image': ('cutout.png', content, 'image/png')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0].mode, 'RGB')
        self.assertEqual(captured[0].getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(captured[0].getpixel((5, 5)), (255, 0, 0))
        self.assertEqual(response.json()['query']['sha256'], hashlib.sha256(content).hexdigest())

    def test_invalid_update_and_unknown_product_do_not_change_data(self):
        before=self.client.get('/api/demo-catalog/products').json()
        payload=dict(name='updated',price='-1',currency='YER',available=True)
        self.assertEqual(self.client.put('/api/demo-catalog/products/'+self.pid,json=payload).status_code,400)
        payload['price']='1';payload['available']='false'
        self.assertEqual(self.client.put('/api/demo-catalog/products/'+self.pid,json=payload).status_code,422)
        payload['available']=True
        self.assertEqual(self.client.put('/api/demo-catalog/products/missing',json=payload).status_code,404)
        self.assertEqual(before,self.client.get('/api/demo-catalog/products').json())

    def test_category_filter_and_invalid_creation(self):
        response=self.client.post('/api/demo-catalog/search',data={'category':'pants'},files={'image':('q.png',self.photo,'image/png')})
        self.assertEqual(response.json()['results'],[])
        response=self.client.post('/api/demo-catalog/products',data={'name':'bad','price':'NaN'},files={'images':('p.png',self.photo,'image/png')})
        self.assertEqual(response.status_code,400)
        self.assertEqual(len(self.client.get('/api/demo-catalog/products').json()['products']),1)

    def test_search_receipt_identifies_added_catalog_and_uploaded_cutout(self):
        import hashlib
        response=self.client.post('/api/demo-catalog/search', data={'category':'outwear'},
                                  files={'image':('sam2-cutout.png',self.photo,'image/png')})
        self.assertEqual(response.status_code,200)
        body=response.json()
        self.assertEqual(body['query']['sha256'],hashlib.sha256(self.photo).hexdigest())
        self.assertEqual(body['query']['catalog_source'],'added_products')
        self.assertEqual(body['query']['category_routing']['requested_category'],'outwear')
        self.assertTrue(body['results'][0]['category_label'])
        self.assertNotIn('search_id',body['query'])


    def test_auto_reports_fallback_and_preserves_all_products(self):
        self.client.post('/api/demo-catalog/products',data={'name':'unknown'},files={'images':('p.png',self.photo,'image/png')})
        response=self.client.post('/api/demo-catalog/search',data={'category':'auto'},files={'image':('q.png',self.photo,'image/png')})
        self.assertEqual(response.status_code,200)
        body=response.json()
        self.assertEqual(len(body['results']),2)
        self.assertEqual(body['query']['category_routing']['requested_category'],'auto')
        self.assertEqual(body['query']['category_routing']['fallback_reason'],'uncategorized_products')
        self.assertIsNone(body['query']['category_routing']['applied_category'])
