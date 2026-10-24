import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from tools import collect_identity_queries as collect
from evaluation import paired_identity_evaluation as paired
from evaluation.exact_product_evaluation import load_manifest


class IdentityCollectionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.catalog=self.root/'catalog';self.catalog.mkdir()
        Image.new('RGB',(20,20),'blue').save(self.catalog/'reference.png')
        self.query=self.root/'new.png';Image.new('RGB',(20,20),'red').save(self.query)
        self.metadata_file=self.root/'catalog_metadata.json';self.metadata_file.write_text('{}')
        self.metadata=SimpleNamespace(items={'reference.png':{'product_id':'A','category_key':'dress'}})
        self.case=self.root/'case.json';self.manifest=self.root/'manifest.json'
        self.payload={'schema_version':'1.0','scope':'fresh_identity_pre_result_case','created_at_utc':'2026-10-24T00:00:00Z',
                      'catalog_metadata_sha256':collect.file_sha256(self.metadata_file),
                      'query':{'image':str(self.query),'sha256':collect.file_sha256(self.query),
                               'product_id':'A','category':'dress','search_category':'auto',
                               'confirmed_new_capture':True,'target_confirmed_before_search':True,
                               'selection':{'confirmed_before_search':True,'points':[[5,5]],'labels':[1]}}}
        patches=[patch.object(collect,'CATALOG_METADATA_FILE',self.metadata_file),
                 patch.object(paired,'CATALOG_DIR',self.catalog),
                 patch.object(paired,'CatalogMetadata',return_value=self.metadata),
                 patch.object(paired,'load_manifest',side_effect=lambda p,m:load_manifest(p,m,catalog_dir=self.catalog))]
        for item in patches:item.start();self.addCleanup(item.stop)

    def save_case(self):self.case.write_text(json.dumps(self.payload))

    def test_valid_collection_registers_once_and_duplicate_does_not_overwrite(self):
        self.save_case();self.assertEqual(collect.register(self.case,self.manifest),1)
        before=self.manifest.read_bytes()
        with self.assertRaisesRegex(ValueError,'duplicates'):collect.register(self.case,self.manifest)
        self.assertEqual(self.manifest.read_bytes(),before)

    def test_unknown_target_or_changed_query_is_rejected_before_manifest_write(self):
        self.payload['query']['product_id']='missing';self.save_case()
        with self.assertRaisesRegex(ValueError,'unknown product_id'):collect.register(self.case,self.manifest)
        self.assertFalse(self.manifest.exists())
        self.payload['query']['product_id']='A';self.payload['query']['sha256']='changed';self.save_case()
        with self.assertRaisesRegex(ValueError,'changed since collection'):collect.register(self.case,self.manifest)
        self.assertFalse(self.manifest.exists())

    def test_reencoded_same_pixels_are_not_accepted_as_new_capture(self):
        Image.new('RGB',(20,20),'blue').save(self.query,format='BMP')
        self.payload['query']['sha256']=collect.file_sha256(self.query);self.save_case()
        with self.assertRaisesRegex(ValueError,'Decoded query pixels'):collect.register(self.case,self.manifest)
        self.assertFalse(self.manifest.exists())
