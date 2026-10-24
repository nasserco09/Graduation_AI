import base64
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import requests

from evaluation import paired_identity_evaluation as paired


class PairedIdentityTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup);self.root=Path(folder.name)
        self.photo=self.root/'new.png';Image.new('RGB',(20,30),'red').save(self.photo)
        self.query={'confirmed_new_capture':True,'target_confirmed_before_search':True,
                    'selection':{'confirmed_before_search':True,'points':[[5,10]],'labels':[1]}}

    def test_selection_requires_pre_result_truth_and_valid_positive_points(self):
        paired.validate_selection(self.query,self.photo)
        cases=[{'confirmed_new_capture':False}, {'target_confirmed_before_search':False},
               {'selection':{'confirmed_before_search':False,'points':[[5,10]],'labels':[1]}},
               {'selection':{'confirmed_before_search':True,'points':[[20,10]],'labels':[1]}},
               {'selection':{'confirmed_before_search':True,'points':[[5,10]],'labels':[0]}},
               {'selection':{'confirmed_before_search':True,'points':[[float('nan'),10]],'labels':[1]}},
               {'selection':{'confirmed_before_search':True,'points':[[5,10]]*51,'labels':[1]*51}},
               {'selection':{'confirmed_before_search':True,'points':[[5,10]],'labels':[True]}}]
        for update in cases:
            with self.subTest(update=update),self.assertRaises(ValueError):
                paired.validate_selection({**self.query,**update},self.photo)

    def test_invalid_collection_stops_before_any_network_or_inference(self):
        with patch.object(paired,'validate_collection',side_effect=ValueError('invalid')),patch.object(paired.requests,'Session') as session:
            with self.assertRaises(ValueError):paired.run(self.root/'manifest.json',self.root/'results.json','http://127.0.0.1:8001')
            session.assert_not_called()

    def test_remote_destination_is_rejected_before_reading_user_photos(self):
        with patch.object(paired,'validate_collection') as preflight:
            with self.assertRaises(ValueError):paired.run(self.root/'manifest.json',self.root/'results.json','https://example.invalid')
            preflight.assert_not_called()

    def test_sam_failure_stays_in_denominator_and_manifest_is_sealed(self):
        manifest=self.root/'manifest.json';manifest.write_text('{"input":"sealed-before-search"}')
        (self.root/'data').mkdir();(self.root/'data/catalog_siglip2.faiss').write_bytes(b'unchanged index')
        queries=[{'image':self.photo,'relative_image':'new1.png','product_id':'A','sha256':'q1','search_category':'auto','selection':self.query['selection']},
                 {'image':self.photo,'relative_image':'new2.png','product_id':'B','sha256':'q2','search_category':'auto','selection':self.query['selection']}]
        image=base64.b64encode(self.photo.read_bytes()).decode()
        class Response:
            def __init__(self,body,failed=False):self.body=body;self.failed=failed
            def raise_for_status(self):
                if self.failed:raise requests.HTTPError('failed segment')
            def json(self):return self.body
        class Session:
            def __init__(self):self.segment_calls=0
            def get(self,*args,**kwargs):return Response({'indexed_images':2})
            def post(self,url,**kwargs):
                if url.endswith('/api/segment'):
                    self.segment_calls+=1
                    return Response({'cutout':image},failed=self.segment_calls==2)
                return Response({'results':[{'product_id':'A'},{'product_id':'C'},{'product_id':'A'}]})
        with patch.object(paired,'ROOT',self.root),patch.object(paired,'validate_collection',return_value=(queries,SimpleNamespace(items={'x':{},'y':{}}))),patch.object(paired.ReviewedProductGroups,'load',return_value=SimpleNamespace(by_product={})),patch.object(paired.requests,'Session',Session):
            report=paired.run(manifest,self.root/'results.json','http://127.0.0.1:8001')
        self.assertEqual(report['sam2_failure_count'],1)
        self.assertEqual(report['suites']['sam2']['metrics']['query_count'],2)
        self.assertEqual(report['suites']['sam2']['metrics']['reviewed_identity_top1'],.5)
        self.assertEqual(report['suites']['full']['queries'][0]['retrieved_identities'],['A','C'])
        self.assertEqual((self.root/'results.sealed_manifest.json').read_bytes(),manifest.read_bytes())

    def test_decoded_catalog_copy_is_rejected_even_if_file_encoding_differs(self):
        query=dict(self.query,sha256=paired.file_sha256(self.photo))
        manifest=self.root/'manifest.json';manifest.write_text(json.dumps({'scope':'fresh_identity_paired_evaluation','queries':[query]}))
        (self.root/'catalog').mkdir();Image.new('RGB',(20,30),'red').save(self.root/'catalog/reference.bmp')
        metadata=SimpleNamespace(items={'reference.bmp':{}})
        with patch.object(paired,'CATALOG_DIR',self.root/'catalog'),patch.object(paired,'CatalogMetadata',return_value=metadata),patch.object(paired,'load_manifest',return_value=[{'image':self.photo}]):
            with self.assertRaisesRegex(ValueError,'Decoded query pixels'):
                paired.validate_collection(manifest)
