from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from tools.runtime_bundle import application_modules
from tools.verify_runtime import safe_file, verify


class RuntimeBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self, entries):
        (self.root / 'runtime_manifest.json').write_text(json.dumps({
            'schema_version': 1, 'catalog_images': 3068,
            'application_release': 'v1.2.0-rc.9', 'files': entries,
        }), encoding='utf-8')

    def entry(self, name='ordinary.txt', content=b'original'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {'path': name, 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()}

    def test_rejects_paths_outside_bundle(self):
        for name in ('../outside', '/absolute', 'C:/secret', 'folder\\secret', 'folder//name'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_file(self.root, name)

    def test_detects_same_size_tampering(self):
        entry = self.entry(content=b'original')
        self.manifest([entry])
        (self.root / 'ordinary.txt').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            verify(self.root)

    def test_quick_check_still_rejects_changed_size(self):
        entry = self.entry()
        self.manifest([entry])
        (self.root / 'ordinary.txt').write_bytes(b'changed and longer')
        with self.assertRaisesRegex(ValueError, 'Missing or changed'):
            verify(self.root, quick=True)

    def test_personal_database_rejected_before_loading(self):
        self.manifest([self.entry('data/admin_auth.db')])
        with self.assertRaisesRegex(ValueError, 'Private or machine-specific'):
            verify(self.root)

    def test_personal_catalog_and_environment_rejected(self):
        for name in ('data/demo_store/catalog.db', '.venv/config.txt', '.cache/hf/file'):
            with self.subTest(name=name):
                self.manifest([self.entry(name)])
                with self.assertRaisesRegex(ValueError, 'Private or machine-specific'):
                    verify(self.root)

    def test_unused_model_rejected(self):
        self.manifest([self.entry('models/clip_vit_b32/model.safetensors')])
        with self.assertRaisesRegex(ValueError, 'Unused model'):
            verify(self.root)

    def test_duplicate_entry_rejected(self):
        entry = self.entry()
        self.manifest([entry, entry])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            verify(self.root)

    def test_import_graph_excludes_experiments(self):
        (self.root / 'backend').mkdir()
        (self.root / 'backend/__init__.py').write_text('')
        (self.root / 'app.py').write_text('from backend.main import app\n')
        (self.root / 'backend/main.py').write_text('from backend.search_engine import SearchEngine\n')
        (self.root / 'backend/search_engine.py').write_text('import json\n')
        (self.root / 'backend/catalog_isolation.py').write_text('raise RuntimeError("experiment")\n')
        found = application_modules(self.root)
        self.assertIn('backend/search_engine.py', found)
        self.assertIn('backend/__init__.py', found)
        self.assertNotIn('backend/catalog_isolation.py', found)


if __name__ == '__main__':
    unittest.main()
