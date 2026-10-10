import tempfile
import sqlite3
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


    def test_update_preserves_images_and_embeddings_and_survives_reopening(self):
        added=self.store.add('old',[self.red],self.encode)
        with self.store.connect() as db:before=db.execute('SELECT id,photo,vector FROM images').fetchall()
        updated=self.store.update(added['product_id'],'new','outwear','12000.50','YER',True)
        self.assertEqual(updated['price'],'12000.50')
        reopened=DemoCatalog(self.path,3,'test-encoder')
        result=reopened.search([1,0,0])[0]
        self.assertEqual(result['name'],'new');self.assertEqual(result['category'],'outwear')
        self.assertEqual(result['price'],'12000.50')
        with reopened.connect() as db:self.assertEqual(before,db.execute('SELECT id,photo,vector FROM images').fetchall())

    def test_unavailable_product_stays_in_admin_but_not_search(self):
        added=self.store.add('unavailable',[self.red],self.encode)
        self.store.update(added['product_id'],'unavailable',available=False)
        self.assertFalse(self.store.list_products()[0]['available'])
        self.assertEqual(self.store.search([1,0,0]),[])
        self.store.update(added['product_id'],'available',available=True)
        self.assertEqual(len(self.store.search([1,0,0])),1)

    def test_category_filter_applies_before_top_k(self):
        self.store.add('dress',[self.red],self.encode,category='dress')
        pants=self.store.add('pants',[self.blue],self.encode,category='pants')
        result=self.store.search([1,0,0],1,'pants')
        self.assertEqual(result[0]['product_id'],pants['product_id'])

    def test_invalid_details_do_not_change_product(self):
        added=self.store.add('old',[self.red],self.encode)
        before=self.store.list_products()
        for params in [{'price':'-1'},{'price':'1.234'},{'price':'NaN'},{'price':'1e3'},{'currency':'BAD'},{'category':'invalid'},{'available':'false'}]:
            with self.assertRaises(ValueError):self.store.update(added['product_id'],'new',**params)
        self.assertEqual(before,self.store.list_products())

    def test_optional_and_zero_prices(self):
        self.assertIsNone(self.store.details('name')['price'])
        self.assertIsNone(self.store.details('name',price='')['price'])
        self.assertEqual(self.store.details('name',price='0')['price'],'0.00')
        self.assertEqual(self.store.details('name',price='12.1')['price'],'12.10')
        with self.assertRaises(KeyError):self.store.update('missing','name')

    def test_legacy_database_migration_preserves_product_images(self):
        old=self.path.parent/'legacy.db'
        with sqlite3.connect(old) as db:
            db.executescript('CREATE TABLE products(id TEXT PRIMARY KEY,name TEXT NOT NULL); CREATE TABLE images(id TEXT PRIMARY KEY,product_id TEXT NOT NULL,photo BLOB NOT NULL,vector BLOB NOT NULL);')
            db.execute('INSERT INTO products VALUES (?,?)',('p1','legacy'))
            db.execute('INSERT INTO images VALUES (?,?,?,?)',('i1','p1',b'old-photo',np.array([1,0,0],dtype=np.float32).tobytes()))
        db.close()
        migrated=DemoCatalog(old,3,'test-encoder')
        product=migrated.list_products()[0]
        self.assertEqual(product['product_id'],'p1');self.assertEqual(product['category'],'')
        self.assertIsNone(product['price']);self.assertTrue(product['available'])
        self.assertEqual(migrated.image_bytes('i1'),b'old-photo')
        self.assertEqual(migrated.search([1,0,0])[0]['product_id'],'p1')
        self.assertEqual(len(DemoCatalog(old,3,'test-encoder').list_products()),1)


    def test_auto_uses_only_available_added_categories_with_clear_match(self):
        dress=self.store.add('dress',[self.red],self.encode,category='dress')
        self.store.add('pants',[self.blue],self.encode,category='pants')
        hidden=self.store.add('hidden',[self.red],self.encode,category='hat',available=False)
        results,routing=self.store.search_with_routing([1,0,0],8,'auto')
        self.assertEqual(routing['applied_category'],'dress')
        self.assertEqual(routing['available_categories'],['dress','pants'])
        self.assertIsNone(routing['fallback_reason'])
        self.assertEqual([r['product_id'] for r in results],[dress['product_id']])

    def test_auto_ambiguous_and_weak_query_search_all(self):
        self.store.add('dress',[self.red],self.encode,category='dress')
        self.store.add('pants',[self.blue],self.encode,category='pants')
        for query,reason in [([1,0,1],'ambiguous_categories'),([0,1,0],'weak_similarity')]:
            with self.subTest(reason=reason):
                results,routing=self.store.search_with_routing(query,8,'auto')
                self.assertEqual(len(results),2)
                self.assertIsNone(routing['applied_category'])
                self.assertEqual(routing['fallback_reason'],reason)

    def test_auto_keeps_uncategorized_products_searchable(self):
        self.store.add('dress',[self.red],self.encode,category='dress')
        self.store.add('pants',[self.blue],self.encode,category='pants')
        self.store.add('unknown',[self.red],self.encode)
        results,routing=self.store.search_with_routing([1,0,0],8,'auto')
        self.assertEqual(len(results),3)
        self.assertEqual(routing['fallback_reason'],'uncategorized_products')
        self.assertIsNone(routing['applied_category'])

    def test_auto_empty_and_single_category_are_safe(self):
        results,routing=self.store.search_with_routing([1,0,0],8,'auto')
        self.assertEqual(results,[])
        self.assertEqual(routing['fallback_reason'],'empty_catalog')
        self.store.add('dress',[self.red],self.encode,category='dress')
        results,routing=self.store.search_with_routing([0,0,1],8,'auto')
        self.assertEqual(len(results),1)
        self.assertEqual(routing['fallback_reason'],'insufficient_categories')

    def test_duplicate_views_do_not_add_category_votes(self):
        self.store.add('dress',[self.red]*5,self.encode,category='dress')
        self.store.add('pants',[self.blue],self.encode,category='pants')
        results,routing=self.store.search_with_routing([1,0,1],8,'auto')
        self.assertEqual(len(results),2)
        self.assertEqual(routing['fallback_reason'],'ambiguous_categories')
        self.assertEqual(routing['similarity_margin'],0)

    def test_all_and_manual_category_keep_their_meaning(self):
        self.store.add('dress',[self.red],self.encode,category='dress')
        self.store.add('pants',[self.blue],self.encode,category='pants')
        results,routing=self.store.search_with_routing([1,0,0],8,'all')
        self.assertEqual(len(results),2)
        self.assertIsNone(routing['applied_category'])
        results,routing=self.store.search_with_routing([1,0,0],8,'pants')
        self.assertEqual(len(results),1)
        self.assertEqual(routing['applied_category'],'pants')
        with self.assertRaises(ValueError):self.store.search([1,0,0],8,'bad')
