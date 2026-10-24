from io import BytesIO
from pathlib import Path
import hashlib
import json
import tempfile
import threading
from types import SimpleNamespace
import unittest

from argon2 import PasswordHasher
from fastapi import FastAPI
from fastapi.testclient import TestClient
import numpy as np
from PIL import Image

from backend.admin_auth import AdminAuth, COOKIE, SESSION_SECONDS, install_admin_security
from backend.demo_catalog import DemoCatalog
from backend.demo_catalog_api import create_demo_catalog_router
from backend.image_preprocessing import PREPROCESSING_VERSION

PASSWORD = 'Test-only secret phrase 2026!'
NEW_PASSWORD = 'Another test-only phrase 2026!'


class AdminAuthorizationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.now = 1000
        for page in ['admin-login.html','admin-account.html','demo-catalog.html']:
            (self.root/page).write_text('<html>test page</html>')
        self.auth = AdminAuth(self.root/'auth.db', clock=lambda:self.now,
                              hasher=PasswordHasher(time_cost=1,memory_cost=8192,parallelism=1))
        self.store = DemoCatalog(self.root/'catalog.db',3,'SigLIP2:'+PREPROCESSING_VERSION)
        self.pid = self.store.add('existing',[Image.new('RGB',(10,10),'red')],lambda image:[1,0,0])['product_id']
        engine = SimpleNamespace(index=SimpleNamespace(d=3),_index_lock=threading.RLock(),encode_image=lambda image:np.array([[1,0,0]],dtype=np.float32))
        self.app = FastAPI(); self.app.include_router(create_demo_catalog_router(engine,self.root/'catalog.db'))
        install_admin_security(self.app,self.root/'auth.db',self.root,auth=self.auth)
        self.builds = 0
        @self.app.get('/demo-catalog.html')
        def page(): return {'page':'catalog'}
        @self.app.post('/api/reindex')
        def rebuild():
            self.builds += 1; return {'rebuilt':True}
        @self.app.get('/api/health')
        def health(): return {'status':'ok'}
        @self.app.get('/api/monitoring/summary')
        def monitoring(): return {'searches':0}
        self.client = self.make_client()
        stream=BytesIO();Image.new('RGB',(10,10),'red').save(stream,format='PNG');self.photo=stream.getvalue()

    def make_client(self, scheme='http'):
        client=TestClient(self.app,base_url=scheme+'://127.0.0.1',client=('127.0.0.1',50000))
        self.addCleanup(client.close);return client

    def setup_admin(self, client=None):
        client=client or self.client
        response=client.post('/api/auth/setup',json={'username':'admin','password':PASSWORD,'confirm_password':PASSWORD})
        self.assertEqual(response.status_code,201,response.text)
        return client.get('/api/auth/session').json()['csrf_token']

    def test_initial_session_has_no_account_or_csrf_and_setup_is_single_use(self):
        self.assertEqual(self.client.get('/api/auth/session').json(),{'configured':False,'authenticated':False})
        self.setup_admin()
        self.assertEqual(self.client.post('/api/auth/setup',json={'username':'other','password':PASSWORD,'confirm_password':PASSWORD}).status_code,409)

    def test_admin_password_and_session_are_not_stored_in_plaintext(self):
        self.setup_admin();token=self.client.cookies.get(COOKIE)
        with self.auth.connect() as db:
            password_hash=db.execute('SELECT password_hash FROM admin_account').fetchone()[0]
            tokens=[r[0] for r in db.execute('SELECT token_hash FROM admin_sessions')]
        self.assertTrue(password_hash.startswith('$argon2id$'));self.assertNotEqual(password_hash,PASSWORD)
        self.assertNotIn(token,tokens);self.assertIn(hashlib.sha256(token.encode()).hexdigest(),tokens)

    def test_unauthenticated_admin_endpoints_are_closed_before_mutations(self):
        paths=[('GET','/api/demo-catalog/products'),('POST','/api/demo-catalog/products'),
               ('PUT','/api/demo-catalog/products/'+self.pid),('PUT','/api/demo-catalog/products/'+self.pid+'/content'),
               ('DELETE','/api/demo-catalog/products/'+self.pid+'?revision=1'),
               ('POST','/api/reindex'),('GET','/api/monitoring/summary')]
        for method,path in paths:
            with self.subTest(path=path):self.assertEqual(self.client.request(method,path).status_code,401)
        self.assertEqual(len(self.store.list_products()),1);self.assertEqual(self.builds,0)

    def test_visitors_can_search_view_images_and_check_health_without_login(self):
        image_url=self.store.list_products()[0]['images'][0]['url']
        self.assertEqual(self.client.get(image_url).status_code,200)
        self.assertEqual(self.client.get('/api/health').status_code,200)
        response=self.client.post('/api/demo-catalog/search',files={'image':('q.png',self.photo,'image/png')})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['results'][0]['product_id'],self.pid)

    def test_private_pages_redirect_to_login_and_disallow_cached_responses(self):
        response=self.client.get('/demo-catalog.html',follow_redirects=False)
        self.assertEqual(response.status_code,303);self.assertIn('/admin-login.html?',response.headers['location'])
        self.setup_admin()
        response=self.client.get('/demo-catalog.html')
        self.assertEqual(response.status_code,200);self.assertEqual(response.headers['cache-control'],'no-store')

    def test_authenticated_mutations_require_session_bound_csrf(self):
        csrf=self.setup_admin()
        self.assertEqual(self.client.post('/api/reindex').status_code,403)
        self.assertEqual(self.client.post('/api/reindex',headers={'X-CSRF-Token':'wrong'}).status_code,403)
        self.assertEqual(self.builds,0)
        self.assertEqual(self.client.post('/api/reindex',headers={'X-CSRF-Token':csrf}).status_code,200)
        self.assertEqual(self.builds,1)

    def test_admin_can_create_update_and_delete_with_csrf(self):
        csrf=self.setup_admin();headers={'X-CSRF-Token':csrf}
        response=self.client.post('/api/demo-catalog/products',headers=headers,data={'name':'created'},files={'images':('p.png',self.photo,'image/png')})
        self.assertEqual(response.status_code,201);pid=response.json()['product_id']
        self.assertEqual(self.client.put('/api/demo-catalog/products/'+pid,headers=headers,json={'name':'updated','price':'20'}).status_code,200)
        self.assertEqual(self.client.delete('/api/demo-catalog/products/'+pid+'?revision=2',headers=headers).status_code,200)
        self.assertEqual(len(self.store.list_products()),1)

    def test_cross_origin_requests_cannot_setup_login_or_mutate(self):
        evil={'Origin':'https://example.invalid','Sec-Fetch-Site':'cross-site'}
        self.assertEqual(self.client.post('/api/auth/setup',headers=evil,json={'username':'admin','password':PASSWORD,'confirm_password':PASSWORD}).status_code,403)
        self.assertFalse(self.auth.configured())
        csrf=self.setup_admin()
        self.assertEqual(self.client.post('/api/reindex',headers={**evil,'X-CSRF-Token':csrf}).status_code,403)
        self.assertEqual(self.client.post('/api/auth/login',headers=evil,json={'username':'admin','password':PASSWORD}).status_code,403)
        self.assertEqual(self.builds,0)

    def test_invalid_host_is_rejected_even_when_resolved_to_local_server(self):
        self.assertEqual(self.client.get('/api/auth/session',headers={'Host':'rebinding.invalid'}).status_code,400)

    def test_first_setup_is_rejected_for_non_loopback_clients(self):
        remote=TestClient(self.app,base_url='http://127.0.0.1',client=('192.0.2.12',50000))
        self.addCleanup(remote.close)
        self.assertEqual(remote.post('/api/auth/setup',json={'username':'admin','password':PASSWORD,'confirm_password':PASSWORD}).status_code,403)
        self.assertFalse(self.auth.configured())

    def test_alternate_path_spellings_do_not_bypass_the_guard(self):
        for path in ['/api/demo-catalog/products/','//api/demo-catalog/products','/api/demo-catalog//products','/api/demo-catalog/products%2Ffuture']:
            # A leading // is a network-path reference in HTTP clients; use an absolute local URL.
            response=self.client.get('http://127.0.0.1'+path,follow_redirects=False)
            with self.subTest(path=path):self.assertEqual(response.status_code,401)

    def test_csrf_from_another_session_cannot_authorize_a_write(self):
        first_csrf=self.setup_admin();second=self.make_client()
        second.post('/api/auth/login',json={'username':'admin','password':PASSWORD})
        self.assertEqual(second.post('/api/reindex',headers={'X-CSRF-Token':first_csrf}).status_code,403)
        self.assertEqual(self.builds,0)

    def test_auth_rejects_form_posts_oversized_json_and_invalid_passwords(self):
        self.assertEqual(self.client.post('/api/auth/login',data={'username':'admin','password':PASSWORD}).status_code,415)
        self.assertEqual(self.client.post('/api/auth/setup',json={'username':'admin','password':'x'*5000,'confirm_password':'x'*5000}).status_code,413)
        for username,password,confirm in [('admin','short','short'),('bad name',PASSWORD,PASSWORD),('admin',PASSWORD,'different')]:
            response=self.client.post('/api/auth/setup',json={'username':username,'password':password,'confirm_password':confirm})
            self.assertEqual(response.status_code,400);self.assertNotIn(password,response.text)

    def test_failed_logins_have_generic_errors_and_a_global_rate_limit(self):
        self.setup_admin();self.client.cookies.clear()
        for i in range(5):
            response=self.client.post('/api/auth/login',json={'username':'unknown'+str(i),'password':'incorrect'})
            self.assertEqual(response.status_code,401);self.assertEqual(response.json()['code'],'invalid_credentials')
        response=self.client.post('/api/auth/login',json={'username':'admin','password':PASSWORD})
        self.assertEqual(response.status_code,429);self.assertEqual(response.headers['Retry-After'],'60')
        self.now+=61
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'ADMIN','password':PASSWORD}).status_code,200)

    def test_logout_revokes_the_current_cookie_on_the_server(self):
        csrf=self.setup_admin();token=self.client.cookies.get(COOKIE)
        self.assertEqual(self.client.post('/api/auth/logout',headers={'X-CSRF-Token':csrf}).status_code,200)
        self.assertIsNone(self.auth.session(token))
        self.client.cookies.set(COOKIE,token)
        self.assertEqual(self.client.get('/api/demo-catalog/products').status_code,401)

    def test_expired_sessions_cannot_read_admin_data_or_mutate(self):
        csrf=self.setup_admin();self.now+=SESSION_SECONDS+1
        self.assertFalse(self.client.get('/api/auth/session').json()['authenticated'])
        self.assertEqual(self.client.get('/api/demo-catalog/products').status_code,401)
        self.assertEqual(self.client.post('/api/reindex',headers={'X-CSRF-Token':csrf}).status_code,401)

    def test_password_change_checks_current_password_and_revokes_all_sessions(self):
        csrf=self.setup_admin();second=self.make_client()
        second.post('/api/auth/login',json={'username':'admin','password':PASSWORD})
        data={'current_password':'wrong','new_password':NEW_PASSWORD,'confirm_password':NEW_PASSWORD}
        self.assertEqual(self.client.post('/api/auth/password',headers={'X-CSRF-Token':csrf},json=data).status_code,400)
        self.assertTrue(self.client.get('/api/auth/session').json()['authenticated'])
        data['current_password']=PASSWORD
        self.assertEqual(self.client.post('/api/auth/password',headers={'X-CSRF-Token':csrf},json=data).status_code,200)
        self.assertFalse(second.get('/api/auth/session').json()['authenticated'])
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'admin','password':PASSWORD}).status_code,401)
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'admin','password':NEW_PASSWORD}).status_code,200)

    def test_session_cookies_are_httponly_strict_and_secure_on_https(self):
        secure=self.make_client('https')
        response=secure.post('/api/auth/setup',json={'username':'admin','password':PASSWORD,'confirm_password':PASSWORD})
        cookie=response.headers['set-cookie'].lower()
        for attribute in ['httponly','samesite=strict','secure','path=/','max-age=28800']:
            self.assertIn(attribute,cookie)

    def test_server_session_survives_store_restart_and_local_recovery_revokes_it(self):
        self.setup_admin();token=self.client.cookies.get(COOKIE)
        reopened=AdminAuth(self.auth.database,clock=lambda:self.now,hasher=self.auth.hasher)
        self.assertIsNotNone(reopened.session(token))
        reopened.reset_local('admin',NEW_PASSWORD)
        self.assertIsNone(self.auth.session(token))

    def test_non_ascii_or_malformed_credentials_are_rejected_without_server_error(self):
        self.setup_admin()
        for username,password in [('اسم',PASSWORD),('admin','\ud800'),(None,None)]:
            payload=json.dumps({'username':username,'password':password},ensure_ascii=True)
            self.assertEqual(self.client.post('/api/auth/login',content=payload,headers={'Content-Type':'application/json'}).status_code,401)
