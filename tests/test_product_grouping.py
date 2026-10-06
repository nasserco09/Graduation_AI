import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from backend.product_grouping import ReviewedProductGroups


class ProductGroupingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.items = {}
        self.members = []
        for pid in ['a', 'b', 'c', 'd']:
            path = self.root / (pid + '.jpg')
            path.write_bytes(pid.encode())
            self.items[pid + '.jpg'] = dict(product_id=pid, image=pid+'.jpg', category_key='outwear')
            self.members.append(dict(product_id=pid, image=pid+'.jpg', sha256=hashlib.sha256(pid.encode()).hexdigest()))
        self.manifest = dict(schema_version='1.0', basis='human_visual_review', groups=[dict(group_id='g1', members=self.members[:2])])

    def load(self):
        path = self.root / 'groups.json'
        path.write_text(json.dumps(self.manifest), encoding='utf-8')
        return ReviewedProductGroups.load(path, self.items, self.root)

    def test_best_image_retained_and_results_refilled_without_mutation(self):
        store = self.load()
        results = [dict(product_id=p, score=s, image=p+'.jpg') for p,s in [('b',.99),('a',.98),('c',.97),('d',.96)]]
        output = store.select(results,3)
        self.assertEqual([x['product_id'] for x in output],['b','c','d'])
        self.assertEqual(output[0]['score'],.99)
        self.assertEqual(len(output[0]['group_images']),2)
        self.assertNotIn('group_images',results[0])

    def test_unreviewed_similar_products_remain_separate(self):
        output = self.load().select([dict(product_id=p,score=.99) for p in ['c','d']],2)
        self.assertEqual([x['product_id'] for x in output],['c','d'])

    def test_overlap_rejected(self):
        self.manifest['groups'].append(dict(group_id='g2',members=self.members[1:3]))
        with self.assertRaisesRegex(ValueError,'overlapping'):self.load()

    def test_unknown_product_rejected(self):
        self.members[0]['product_id']='unknown'
        with self.assertRaisesRegex(ValueError,'Unknown'):self.load()

    def test_changed_image_rejected(self):
        (self.root/'a.jpg').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'bytes changed'):self.load()

    def test_category_mismatch_rejected(self):
        self.items['b.jpg']['category_key']='dress'
        with self.assertRaisesRegex(ValueError,'categories'):self.load()

    def test_changed_path_rejected(self):
        self.members[0]['image']='c.jpg'
        with self.assertRaisesRegex(ValueError,'path differs'):self.load()

    def test_duplicate_group_id_rejected(self):
        self.manifest['groups'].append(dict(group_id='g1',members=self.members[2:]))
        with self.assertRaisesRegex(ValueError,'duplicate group'):self.load()

    def test_empty_config_preserves_result_order(self):
        results=[dict(product_id=p,score=.5) for p in ['a','b']]
        self.assertEqual(ReviewedProductGroups().select(results,2),results)
