import copy,hashlib,json,unittest
from evaluation.probe_known_positives import validate_confirmation

class KnownPositiveConfirmationTests(unittest.TestCase):
    def fixture(self):
        m={'proposed_candidates':[{'product_id':'a'},{'product_id':'b'}]}
        m['pack_id']=hashlib.sha256(json.dumps(m,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        a={'pack_id':m['pack_id'],'scope':'known_positive_confirmation_before_review_retrieval','selected_positive_ids':['a']}
        return m,a
    def test_user_confirmed_positive_preserved(self):
        m,a=self.fixture();selected,proposed=validate_confirmation(m,a)
        self.assertEqual(selected,['a']);self.assertIn('b',proposed)
    def test_no_positive_cannot_trigger_probe(self):
        m,a=self.fixture();a['selected_positive_ids']=[]
        with self.assertRaisesRegex(ValueError,'Empty'):validate_confirmation(m,a)
    def test_unknown_positive_cannot_trigger_probe(self):
        m,a=self.fixture();a['selected_positive_ids']=['foreign']
        with self.assertRaisesRegex(ValueError,'Unknown'):validate_confirmation(m,a)
    def test_duplicate_positive_rejected(self):
        m,a=self.fixture();a['selected_positive_ids']=['a','a']
        with self.assertRaisesRegex(ValueError,'duplicate'):validate_confirmation(m,a)
    def test_stale_confirmation_rejected(self):
        m,a=self.fixture();a['pack_id']='other-pack'
        with self.assertRaisesRegex(ValueError,'mismatch'):validate_confirmation(m,a)
    def test_modified_manifest_rejected(self):
        m,a=self.fixture();m['proposed_candidates'].append({'product_id':'c'})
        with self.assertRaisesRegex(ValueError,'modified'):validate_confirmation(m,a)

if __name__=='__main__':unittest.main()
