from io import BytesIO
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
from unittest import TestCase

from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
from PIL import Image

from backend.admin_auth import AdminAuth, install_admin_security
from backend.demo_catalog_api import create_demo_catalog_router


class CatalogBackupAPITests(TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        engine=SimpleNamespace(index=SimpleNamespace(d=3),_index_lock=threading.RLock(),encode_image=lambda image:np.array([[1,0,0]],dtype=np.float32))
        app=FastAPI();app.include_router(create_demo_catalog_router(engine,self.root/'catalog.db'))
        auth=AdminAuth(self.root/'auth.db',hasher=PasswordHasher(time_cost=1,memory_cost=8192,parallelism=1))
        install_admin_security(app,self.root/'auth.db',self.root,auth=auth)
        self.app=app;self.client=self.make_client()
        self.client.post('/api/auth/setup',json={'username':'admin','password':'QAtest12','confirm_password':'QAtest12'})
        self.csrf=self.client.get('/api/auth/session').json()['csrf_token'];self.headers={'X-CSRF-Token':self.csrf}
        stream=BytesIO();Image.new('RGB',(12,12),'red').save(stream,format='PNG');self.photo=stream.getvalue()
        self.add('original')

    def make_client(self):
        client=TestClient(self.app,base_url='http://127.0.0.1',client=('127.0.0.1',50000));self.addCleanup(client.close);return client

    def add(self,name):
        response=self.client.post('/api/demo-catalog/products',headers=self.headers,data={'name':name},files={'images':('photo.png',self.photo,'image/png')})
        self.assertEqual(response.status_code,201);return response.json()['product_id']

    def preview(self,content=None):
        content=content or self.client.get('/api/demo-catalog/products/backup').content
        return self.client.post('/api/demo-catalog/products/restore/preview',headers=self.headers,files={'backup':('catalog.zip',content,'application/zip')})

    def test_export_preview_restore_and_persistent_recovery_download(self):
        exported=self.client.get('/api/demo-catalog/products/backup')
        self.assertEqual(exported.status_code,200);self.assertIn('attachment;',exported.headers['content-disposition'])
        self.add('added after backup')
        preview=self.preview(exported.content);self.assertEqual(preview.status_code,200)
        info=preview.json();self.assertEqual(info['product_count'],1);self.assertEqual(info['current_product_count'],2)
        restored=self.client.post('/api/demo-catalog/products/restore',headers=self.headers,json={'token':info['token']})
        self.assertEqual(restored.status_code,200);self.assertEqual(restored.json()['product_count'],1)
        self.assertEqual(len(self.client.get('/api/demo-catalog/products').json()['products']),1)
        recovery=self.client.get(restored.json()['recovery_backup_url']);self.assertEqual(recovery.status_code,200)
        history=self.client.get('/api/demo-catalog/products/backups').json()['backups']
        self.assertEqual(len(history),1);self.assertEqual(history[0]['product_count'],2)
        self.assertEqual(history[0]['download_url'],restored.json()['recovery_backup_url'])
        self.assertEqual(self.preview(recovery.content).json()['product_count'],2)

    def test_guest_and_missing_csrf_cannot_export_preview_restore_or_download(self):
        guest=self.make_client()
        for path in ['/products/backup','/products/backups','/products/recovery/'+'a'*32]:
            self.assertEqual(guest.get('/api/demo-catalog'+path).status_code,401)
        for path in ['/products/restore/preview','/products/restore']:
            self.assertEqual(guest.post('/api/demo-catalog'+path).status_code,401)
            self.assertEqual(self.client.post('/api/demo-catalog'+path).status_code,403)

    def test_preview_token_is_bound_to_the_session_that_uploaded_it(self):
        token=self.preview().json()['token'];second=self.make_client()
        self.assertEqual(second.post('/api/auth/login',json={'username':'admin','password':'QAtest12'}).status_code,200)
        csrf=second.get('/api/auth/session').json()['csrf_token']
        response=second.post('/api/demo-catalog/products/restore',headers={'X-CSRF-Token':csrf},json={'token':token})
        self.assertEqual(response.status_code,409);self.assertEqual(response.json()['code'],'restore_preview_expired')

    def test_invalid_upload_and_stale_preview_return_stable_codes_without_changing_data(self):
        before=self.client.get('/api/demo-catalog/products').json()
        response=self.preview(b'SQLite format 3\x00not accepted')
        self.assertEqual(response.status_code,400);self.assertEqual(response.json()['code'],'backup_invalid')
        self.assertEqual(self.client.get('/api/demo-catalog/products').json(),before)
        token=self.preview().json()['token'];self.add('intervening change')
        response=self.client.post('/api/demo-catalog/products/restore',headers=self.headers,json={'token':token})
        self.assertEqual(response.status_code,409);self.assertEqual(response.json()['code'],'catalog_changed')
        self.assertEqual(len(self.client.get('/api/demo-catalog/products').json()['products']),2)
