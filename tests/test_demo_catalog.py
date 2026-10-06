import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image
from backend.demo_catalog import DemoCatalog


class DemoCatalogTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.path=Path(temp.name)/'independent'/'catalog.db'
        self.store=DemoCatalog(self.path,3,'test-encoder')
        self.red=Image.new('RGB',(10,10),(255,0,0))
        self.blue=Image.new('RGB',(10,10),(0,0,255))

    @staticmethod
    def encode(image):return np.array(image.getpixel((0,0)),dtype=np.float32)

    def test_multiple_images_are_one_product_and_best_photo_matches(self):
        product=self.store.add('two views',[self.blue,self.red],self.encode)
        other=self.store.add('other product',[self.blue],self.encode)
        results=self.store.search([1,0,0])
        self.assertEqual(len(results),2)
        self.assertEqual(results[0]['product_id'],product['product_id'])
        self.assertEqual(len(results[0]['images']),2)
        self.assertEqual(results[0]['image_url'],results[0]['images'][1]['url'])
        self.assertEqual(results[1]['product_id'],other['product_id'])

    def test_products_and_images_survive_reopening_database(self):
        added=self.store.add('saved',[self.red],self.encode)
        reopened=DemoCatalog(self.path,3,'test-encoder')
        self.assertEqual(reopened.list_products()[0]['product_id'],added['product_id'])
        iid=reopened.list_products()[0]['images'][0]['image_id']
        self.assertTrue(reopened.image_bytes(iid).startswith(b'\xff\xd8'))
        self.assertEqual(len(reopened.search([1,0,0])),1)

    def test_embedding_failure_does_not_save_partial_product(self):
        calls=[]
        def fail(image):
            calls.append(image)
            if len(calls)==2:raise RuntimeError('encoder failed')
            return self.encode(image)
        with self.assertRaises(RuntimeError):self.store.add('failed',[self.red,self.blue],fail)
        self.assertEqual(self.store.list_products(),[])

    def test_invalid_embeddings_rejected_before_save(self):
        for vector in [[0,0,0],[1,0],[float('nan'),0,1]]:
            with self.assertRaises(ValueError):self.store.add('invalid',[self.red],lambda image:vector)
        self.assertEqual(self.store.list_products(),[])

    def test_invalid_name_and_image_count_rejected(self):
        for name,images in [(' ',[self.red]),('a'*121,[self.red]),('okay',[]),('okay',[self.red]*6)]:
            with self.assertRaises(ValueError):self.store.add(name,images,self.encode)
        self.assertEqual(self.store.list_products(),[])

    def test_encoder_change_requires_separate_database(self):
        with self.assertRaisesRegex(ValueError,'configuration changed'):DemoCatalog(self.path,3,'another-model')

    def test_empty_search_and_missing_image(self):
        self.assertEqual(self.store.search([1,0,0]),[])
        with self.assertRaises(KeyError):self.store.image_bytes('missing')
        with self.assertRaises(ValueError):self.store.search([1,0,0],51)

    def test_same_named_products_keep_distinct_ids(self):
        a=self.store.add('same name',[self.red],self.encode)
        b=self.store.add('same name',[self.red],self.encode)
        self.assertNotEqual(a['product_id'],b['product_id'])
        self.assertEqual(len(self.store.search([1,0,0])),2)
