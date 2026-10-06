import copy,hashlib,json,math,unittest
from evaluation.relevance_metrics import ndcg,evaluate

class RelevanceMetricsTests(unittest.TestCase):
    def fixture(self):
        m={"queries":[{"query_id":"q","candidates":[{"product_id":"a"},{"product_id":"b"}],"rankings":{"baseline":["a","b"],"alternative":["b","a"]}}]}
        m["pack_id"]=hashlib.sha256(json.dumps(m,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        a={"pack_id":m["pack_id"],"judgments":[{"query_id":"q","product_id":"a","relevance":0},{"query_id":"q","product_id":"b","relevance":3}]}
        return m,a
    def test_ndcg_known_reversed_order(self):
        self.assertAlmostEqual(ndcg([0,3],2),1/math.log2(3))
        self.assertEqual(ndcg([3,0],2),1)
    def test_zero_relevance_has_zero_ndcg(self):
        self.assertEqual(ndcg([0,0],2),0)
    def test_complete_human_grades_compare_methods(self):
        m,a=self.fixture();r=evaluate(m,a,k=1)
        self.assertEqual(r["summary"]["baseline"]["precision_relevant"],0)
        self.assertEqual(r["summary"]["alternative"]["precision_relevant"],1)
        self.assertEqual(r["summary"]["alternative"]["ndcg_delta_vs_baseline"],1)
    def test_partial_labels_never_produce_metrics(self):
        m,a=self.fixture();a["judgments"].pop()
        with self.assertRaisesRegex(ValueError,"Incomplete"):evaluate(m,a,k=1)
    def test_duplicate_labels_rejected(self):
        m,a=self.fixture();a["judgments"].append(a["judgments"][0])
        with self.assertRaisesRegex(ValueError,"Duplicate judgment"):evaluate(m,a,k=1)
    def test_unknown_candidate_rejected(self):
        m,a=self.fixture();a["judgments"][0]["product_id"]="foreign"
        with self.assertRaisesRegex(ValueError,"Unknown"):evaluate(m,a,k=1)
    def test_modified_manifest_rejected(self):
        m,a=self.fixture();m["queries"][0]["rankings"]["baseline"].reverse()
        with self.assertRaisesRegex(ValueError,"mismatch"):evaluate(m,a,k=1)
    def test_boolean_is_not_relevance_grade(self):
        m,a=self.fixture();a["judgments"][0]["relevance"]=True
        with self.assertRaisesRegex(ValueError,"integer"):evaluate(m,a,k=1)
    def test_invalid_ranking_rejected(self):
        m,a=self.fixture();m["queries"][0]["rankings"]["alternative"]=["a","a"]
        original=dict(m);original.pop("pack_id");m["pack_id"]=hashlib.sha256(json.dumps(original,sort_keys=True,ensure_ascii=False).encode()).hexdigest();a["pack_id"]=m["pack_id"]
        with self.assertRaisesRegex(ValueError,"ranking"):evaluate(m,a,k=1)

if __name__=="__main__":unittest.main()
