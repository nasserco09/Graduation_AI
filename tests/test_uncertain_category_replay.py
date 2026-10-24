import unittest
from evaluation.replay_uncertain_category import summarize


class UncertaintyReplayTests(unittest.TestCase):
    def test_fallback_can_help_and_harm_and_threshold_boundary_is_inclusive(self):
        records=[{'auto_correct':False,'unrestricted_correct':True,'confidence':.10,'margin':.01},
                 {'auto_correct':True,'unrestricted_correct':False,'confidence':.10,'margin':.01},
                 {'auto_correct':True,'unrestricted_correct':False,'confidence':.20,'margin':.03}]
        candidate=summarize(records,.20,.03)
        self.assertEqual(candidate['fallback_queries'],2)
        self.assertEqual(candidate['correct_queries'],2)
        self.assertEqual(candidate['vs_current_auto']['improved_queries'],1)
        self.assertEqual(candidate['vs_current_auto']['worsened_queries'],1)

    def test_zero_threshold_preserves_current_policy_and_empty_evidence_fails(self):
        record={'auto_correct':True,'unrestricted_correct':False,'confidence':.10,'margin':0}
        self.assertEqual(summarize([record],0,0)['correct_queries'],1)
        self.assertEqual(summarize([record],0,0)['fallback_queries'],0)
        with self.assertRaises(ValueError): summarize([],0,0)
