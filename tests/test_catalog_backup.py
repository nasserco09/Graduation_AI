from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from unittest import TestCase
from unittest.mock import patch
import warnings
import zipfile

import numpy as np
from PIL import Image

from backend.catalog_backup import BackupError, CatalogBackups, PREVIEW_SECONDS
from backend.demo_catalog import CatalogConflict, DemoCatalog


def unpack(content):
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return {name:archive.read(name) for name in archive.namelist()}


def repack(files):
    stream=BytesIO()
    with zipfile.ZipFile(stream,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,content in files.items():archive.writestr(name,content)
    return stream.getvalue()


def edit_archive(content, edit):
    files=unpack(content);manifest=json.loads(files['manifest.json'])
    edit(manifest,files)
    files['manifest.json']=json.dumps(manifest,ensure_ascii=False).encode()
    return repack(files)


class CatalogBackupTests(TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.now=1_700_000_000
        self.store=DemoCatalog(self.root/'catalog.db',3,'test-encoder')
        self.backups=CatalogBackups(self.store,clock=lambda:self.now)
        self.red=Image.new('RGB',(12,12),'red');self.blue=Image.new('RGB',(12,12),'blue')
        encode=lambda image:[1,0,0] if image.getpixel((0,0))[0]>0 else [0,0,1]
        self.pid=self.store.add('سترة',[self.red,self.blue],encode,category='outwear',price='12000',available=False)['product_id']
        self.other=self.store.add('فستان',[self.red],encode,category='dress',price=None,currency='USD')['product_id']
        self.archive=self.backups.export()

    def assert_invalid_without_change(self,content,code='backup_invalid'):
        before=self.backups.snapshot()
        with self.assertRaises(BackupError) as caught:self.backups.preview(content,'owner')
        self.assertEqual(caught.exception.code,code)
        self.assertEqual(self.backups.snapshot(),before)

    def test_export_contains_only_declarative_catalog_content_and_is_consistent(self):
        (self.root/'admin_auth.db').write_bytes(b'a secret that must never leave the computer')
        files=unpack(self.backups.export());manifest=json.loads(files['manifest.json'])
        self.assertEqual(len(manifest['products']),2);self.assertEqual(len(manifest['images']),3)
        self.assertEqual(len(files),7)
        self.assertFalse(any('admin' in name or name.endswith('.db') for name in files))
        self.assertNotIn('secret',repr(manifest))
        self.assertEqual(self.backups.validate(self.archive).products[0][0],self.pid)

    def test_preview_does_not_modify_and_roundtrip_preserves_all_photos_vectors_and_fields(self):
        target=DemoCatalog(self.root/'target.db',3,'test-encoder')
        recovery=CatalogBackups(target,clock=lambda:self.now)
        original=self.backups.snapshot();before=recovery.snapshot()
        info=recovery.preview(self.archive,'owner')
        self.assertEqual((info['product_count'],info['image_count']),(2,3))
        self.assertEqual((info['current_product_count'],info['current_image_count']),(0,0))
        self.assertEqual(recovery.snapshot(),before)
        result=recovery.restore(info['token'],'owner');after=recovery.snapshot()
        self.assertTrue(result['restored']);self.assertEqual(after['images'],original['images'])
        self.assertEqual([r[:6] for r in after['products']],[r[:6] for r in original['products']])
        self.assertTrue(all(r[6]>original['products'][i][6] for i,r in enumerate(after['products'])))
        self.assertEqual(target.search([1,0,0])[0]['product_id'],self.other)
        backup_id=result['recovery_backup_url'].rsplit('/',1)[1]
        previous=recovery.validate(recovery.recovery_path(backup_id).read_bytes())
        self.assertEqual(previous.products,[]);self.assertEqual(previous.images,[])

    def test_stale_preview_cannot_replace_an_intervening_catalog_edit(self):
        info=self.backups.preview(self.archive,'owner')
        self.store.update(self.pid,'updated by another window',price='5')
        before=self.backups.snapshot()
        with self.assertRaises(BackupError) as caught:self.backups.restore(info['token'],'owner')
        self.assertEqual(caught.exception.code,'catalog_changed');self.assertEqual(self.backups.snapshot(),before)

    def test_legacy_equal_positions_export_roundtrips_logical_order_without_modifying_source(self):
        with self.store.connect() as db:
            db.execute('UPDATE images SET position=0 WHERE product_id=?',(self.pid,))
        before=self.backups.snapshot()
        source_product=next(p for p in self.store.list_products() if p['product_id']==self.pid)
        content=self.backups.export();validated=self.backups.validate(content)
        self.assertEqual(self.backups.snapshot(),before)
        self.assertEqual([row[4] for row in validated.images if row[1]==self.pid],[0,1])
        target=DemoCatalog(self.root/'legacy-target.db',3,'test-encoder')
        manager=CatalogBackups(target,clock=lambda:self.now)
        token=manager.preview(content,'owner')['token'];manager.restore(token,'owner')
        target_product=next(p for p in target.list_products() if p['product_id']==self.pid)
        self.assertEqual(target_product['images'],source_product['images'])
        self.assertEqual(target_product['images'][0],source_product['images'][0])
        self.assertEqual([row[:4] for row in manager.snapshot()['images']],
                         [row[:4] for row in before['images']])

    def test_restore_during_new_photo_encoding_invalidates_the_old_editor(self):
        token=self.backups.preview(self.archive,'owner')['token']
        def encode_after_restore(image):
            self.backups.restore(token,'owner')
            return [1,0,0]
        with self.assertRaises(CatalogConflict):
            self.store.save(self.pid,'must not overwrite restore',['new:0'],[self.red],encode_after_restore,expected_revision=1)
        product=next(p for p in self.store.list_products() if p['product_id']==self.pid)
        self.assertEqual(product['name'],'سترة');self.assertEqual(len(product['images']),2)

    def test_preview_expires_is_single_use_and_cannot_be_used_by_another_session(self):
        info=self.backups.preview(self.archive,'owner')
        with self.assertRaises(BackupError):self.backups.restore(info['token'],'other-session')
        self.backups.restore(info['token'],'owner')
        with self.assertRaises(BackupError):self.backups.restore(info['token'],'owner')
        info=self.backups.preview(self.archive,'owner');self.now+=PREVIEW_SECONDS+1
        before=self.backups.snapshot()
        with self.assertRaises(BackupError) as caught:self.backups.restore(info['token'],'owner')
        self.assertEqual(caught.exception.code,'restore_preview_expired');self.assertEqual(self.backups.snapshot(),before)

    def test_new_preview_invalidates_previous_upload_and_bounds_retained_memory(self):
        first=self.backups.preview(self.archive,'owner')
        second=self.backups.preview(self.archive,'owner')
        self.assertEqual(len(self.backups.previews),1)
        with self.assertRaises(BackupError):self.backups.restore(first['token'],'owner')
        self.backups.restore(second['token'],'owner')

    def test_slow_old_preview_cannot_evict_a_newer_completed_preview(self):
        entered=threading.Event();release=threading.Event()
        original_validate=self.backups.validate
        newer=edit_archive(self.archive,lambda manifest,files:manifest.update(created_at='2026-10-24T00:00:00+00:00'))
        def delayed_validate(content):
            if content==self.archive:
                entered.set()
                if not release.wait(timeout=5):raise TimeoutError('Test failed to release the old validation')
            return original_validate(content)
        with patch.object(self.backups,'validate',side_effect=delayed_validate):
            with ThreadPoolExecutor(max_workers=1) as pool:
                old=pool.submit(self.backups.preview,self.archive,'owner')
                try:
                    self.assertTrue(entered.wait(timeout=3))
                    current=self.backups.preview(newer,'owner')
                finally:
                    release.set()
                with self.assertRaises(BackupError) as caught:old.result(timeout=3)
        self.assertEqual(caught.exception.code,'restore_preview_expired')
        self.assertEqual(list(self.backups.previews),[current['token']])
        self.assertTrue(self.backups.restore(current['token'],'owner')['restored'])

    def test_database_failure_rolls_back_replacements_and_keeps_recovery_file(self):
        with self.store.connect() as db:
            db.execute("CREATE TRIGGER refuse_restore BEFORE INSERT ON products BEGIN SELECT RAISE(ABORT,'simulated insert failure'); END")
        info=self.backups.preview(self.archive,'owner');before=self.backups.snapshot()
        with self.assertRaises(sqlite3.IntegrityError):self.backups.restore(info['token'],'owner')
        self.assertEqual(self.backups.snapshot(),before)
        self.assertEqual(len(self.backups.list_recovery()),1)
        self.assertEqual(self.backups.validate(self.backups.recovery_path(self.backups.list_recovery()[0]['backup_id']).read_bytes()).images,before['images'])

    def test_failed_recovery_file_write_prevents_any_catalog_mutation(self):
        info=self.backups.preview(self.archive,'owner');before=self.backups.snapshot()
        with patch.object(self.backups,'_save_recovery',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.backups.restore(info['token'],'owner')
        self.assertEqual(self.backups.snapshot(),before)

    def test_empty_restore_and_reintroducing_a_product_cannot_resurrect_old_editor_revision(self):
        empty=CatalogBackups(DemoCatalog(self.root/'empty.db',3,'test-encoder'),clock=lambda:self.now).export()
        info=self.backups.preview(empty,'owner');self.backups.restore(info['token'],'owner')
        self.assertEqual(self.store.list_products(),[])
        info=self.backups.preview(self.archive,'owner');self.backups.restore(info['token'],'owner')
        previous_revision=self.store.list_products()[0]['revision']
        info=self.backups.preview(empty,'owner');self.backups.restore(info['token'],'owner')
        info=self.backups.preview(self.archive,'owner');self.backups.restore(info['token'],'owner')
        self.assertTrue(all(p['revision']>previous_revision for p in self.store.list_products()))
        product=next(p for p in self.store.list_products() if p['product_id']==self.pid)
        with self.assertRaises(CatalogConflict):
            self.store.save(self.pid,'old editor',[x['image_id'] for x in product['images']],[],lambda image:[1,0,0],expected_revision=previous_revision)

    def test_history_survives_manager_restart_and_files_are_not_automatically_deleted(self):
        for _ in range(2):
            info=self.backups.preview(self.archive,'owner');self.backups.restore(info['token'],'owner')
        reopened=CatalogBackups(self.store,clock=lambda:self.now)
        self.assertEqual(len(reopened.list_recovery()),2)
        self.assertEqual(len(list(reopened.backup_directory.glob('*.fashion-catalog.zip'))),2)
        with self.assertRaises(BackupError):reopened.recovery_path('../catalog.db')
        self.assertFalse(any(p.suffix=='.tmp' for p in reopened.backup_directory.iterdir()))

    def test_malformed_archives_and_paths_are_rejected_without_writing_files(self):
        self.assert_invalid_without_change(b'not a zip')
        self.assert_invalid_without_change(b'SQLite format 3\x00fake database')
        files=unpack(self.archive);files['../outside.txt']=b'not extracted'
        self.assert_invalid_without_change(repack(files));self.assertFalse((self.root.parent/'outside.txt').exists())
        files=unpack(self.archive);stream=BytesIO()
        with warnings.catch_warnings(),zipfile.ZipFile(stream,'w') as archive:
            warnings.simplefilter('ignore')
            for name,content in files.items():archive.writestr(name,content)
            archive.writestr('manifest.json',files['manifest.json'])
        self.assert_invalid_without_change(stream.getvalue())

    def test_archive_size_and_decompressed_size_limits_are_enforced(self):
        with patch('backend.catalog_backup.MAX_BACKUP_BYTES',len(self.archive)-1):
            self.assert_invalid_without_change(self.archive,'backup_too_large')
        files=unpack(self.archive);files['bomb']=b'0'*100_000
        content=repack(files)
        with patch('backend.catalog_backup.MAX_BACKUP_BYTES',32_000):
            self.assert_invalid_without_change(content,'backup_too_large')

    def test_wrong_encoder_or_version_is_rejected(self):
        self.assert_invalid_without_change(edit_archive(self.archive,lambda m,f:m['encoder'].update(dimension=4)),'backup_incompatible')
        self.assert_invalid_without_change(edit_archive(self.archive,lambda m,f:m.update(version=2)))

    def test_invalid_product_details_ids_links_and_image_order_are_rejected(self):
        mutations=[lambda m,f:m['products'][0].update(id='../unsafe'),
                   lambda m,f:m['products'].append(dict(m['products'][0])),
                   lambda m,f:m['products'][0].update(price='-1'),
                   lambda m,f:m['products'][0].update(available=1),
                   lambda m,f:m['products'][0].update(name=''),
                   lambda m,f:m['images'][0].update(product_id='missing'),
                   lambda m,f:m['images'][0].update(position=4),
                   lambda m,f:m['images'][1].update(position=0),
                   lambda m,f:m['images'][0].update(photo='../outside.jpg')]
        for mutation in mutations:
            with self.subTest(mutation=mutation):self.assert_invalid_without_change(edit_archive(self.archive,mutation))

    def test_photo_checksum_and_decoding_are_both_verified(self):
        def changed_photo(manifest,files):files[manifest['images'][0]['photo']]=b'corrupt JPEG'
        self.assert_invalid_without_change(edit_archive(self.archive,changed_photo))
        def invalid_photo(manifest,files):
            item=manifest['images'][0];files[item['photo']]=b'corrupt JPEG'
            item['photo_sha256']=hashlib.sha256(files[item['photo']]).hexdigest()
        self.assert_invalid_without_change(edit_archive(self.archive,invalid_photo))

    def test_vectors_require_finite_unit_norm_values_and_correct_dimensions(self):
        for values in [[float('nan'),0,0],[0,0,0],[2,0,0],[1,0]]:
            def change(manifest,files):
                item=manifest['images'][0];files[item['vector']]=np.array(values,dtype='<f4').tobytes()
                item['vector_sha256']=hashlib.sha256(files[item['vector']]).hexdigest()
            with self.subTest(values=values):self.assert_invalid_without_change(edit_archive(self.archive,change))

    def test_duplicate_manifest_keys_and_zip_symlinks_are_rejected(self):
        files=unpack(self.archive);files['manifest.json']=files['manifest.json'].replace(b'{',b'{"format":"duplicated",',1)
        self.assert_invalid_without_change(repack(files))
        files=unpack(self.archive);stream=BytesIO()
        with zipfile.ZipFile(stream,'w') as archive:
            for name,content in files.items():
                info=zipfile.ZipInfo(name)
                if name.startswith('images/'):info.external_attr=0o120777<<16
                archive.writestr(info,content)
        self.assert_invalid_without_change(stream.getvalue())
