from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from evaluation import reviewed_reverse_sam_pilot as reverse


class ReversePointProtocolTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);self.root=Path(folder.name)
        self.path=self.root/'q.png';Image.new('RGB',(20,30),'red').save(self.path)
        self.protocol={'queries':[{'number':1,'query_image':'q.png','query_sha256':reverse.sha(self.path)}]}
        self.plan={'schema_version':'1.0','protocol_sha256':'protocol-sha',
                   'selection_author':'assistant_visual_review','selected_before_reverse_results':True,
                   'queries':[{'number':1,'points':[[5,10]],'labels':[1]}]}

    def test_author_and_pre_result_declaration_cannot_be_silently_changed(self):
        with patch.object(reverse,'CATALOG_DIR',self.root):
            self.assertEqual(reverse.validate_point_plan(self.protocol,self.plan,'protocol-sha')[1]['labels'],[1])
            for update in [{'selection_author':'human_approved_mask'},
                           {'selected_before_reverse_results':False},
                           {'protocol_sha256':'different-protocol'}]:
                with self.subTest(update=update),self.assertRaises(ValueError):
                    reverse.validate_point_plan(self.protocol,{**self.plan,**update},'protocol-sha')

    def test_all_cases_need_unique_numbers_and_valid_points(self):
        with patch.object(reverse,'CATALOG_DIR',self.root):
            for rows in [[],[{'number':2,'points':[[5,10]],'labels':[1]}],
                         [{'number':1,'points':[[20,10]],'labels':[1]}]]:
                with self.subTest(rows=rows),self.assertRaises(ValueError):
                    reverse.validate_point_plan(self.protocol,{**self.plan,'queries':rows},'protocol-sha')

    def test_changed_query_is_rejected_before_segmentation(self):
        Image.new('RGB',(20,30),'blue').save(self.path)
        with patch.object(reverse,'CATALOG_DIR',self.root),self.assertRaisesRegex(ValueError,'bytes changed'):
            reverse.validate_point_plan(self.protocol,self.plan,'protocol-sha')
