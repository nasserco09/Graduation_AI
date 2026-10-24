import unittest
import numpy as np
from evaluation.reviewed_identity_pilot import identity_metrics, rank_query, split_gallery


class ReviewedIdentityPilotTests(unittest.TestCase):
    def test_all_queries_and_byte_and_pixel_aliases_are_removed_globally(self):
        paths=['q1','q2','same_bytes','same_pixels','target']
        byte={'q1':'a','q2':'b','same_bytes':'a','same_pixels':'c','target':'d'}
        pixel={'q1':'p','q2':'q','same_bytes':'x','same_pixels':'q','target':'r'}
        self.assertEqual(split_gallery(paths,['q1','q2'],byte,pixel),[4])

    def test_no_target_can_be_manufactured_from_a_missing_or_repeated_query(self):
        with self.assertRaises(ValueError):split_gallery(['a'],['missing'],{}, {})
        with self.assertRaises(ValueError):split_gallery(['a'],['a','a'],{'a':'a'},{'a':'a'})
        with self.assertRaises(ValueError):split_gallery(['a'],['a'],{'a':'a'},{'a':'a'})

    def test_metrics_count_identity_rank_and_truncate_mrr_at10(self):
        metrics=identity_metrics([{'target_rank_at10':1},{'target_rank_at10':3},{'target_rank_at10':None}])
        self.assertEqual(metrics['reviewed_identity_top1'],.333333)
        self.assertEqual(metrics['reviewed_identity_top5'],.666667)
        self.assertEqual(metrics['reviewed_identity_mrr_at10'],.444444)
        with self.assertRaises(ValueError):identity_metrics([])

    def test_ranking_deduplicates_reviewed_identity_before_top_k(self):
        vectors=np.asarray([[1,0],[.99,.01],[.9,.1]],dtype='float32')
        results,_,_=rank_query(np.asarray([1,0],dtype='float32'),vectors,['a','b','c'],
                               ['dress']*3,['same','same','other'],'all')
        self.assertEqual([r['identity'] for r in results],['same','other'])
