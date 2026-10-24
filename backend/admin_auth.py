"""Single-owner local administration with revocable opaque sessions."""
from contextlib import contextmanager
import hashlib
import hmac
import json
import ipaddress
from pathlib import Path
import posixpath
import re
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlencode

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

COOKIE = 'fashion_admin_session'
SESSION_SECONDS = 8 * 60 * 60
LOGIN_WINDOW = 60
LOGIN_LIMIT = 5
PRIVATE_PAGES = {'/demo-catalog.html', '/admin-account.html'}


class AuthError(Exception):
    def __init__(self, status, code):
        self.status, self.code = status, code


class AdminAuth:
    def __init__(self, database, *, clock=time.time, hasher=None):
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.hasher = hasher or PasswordHasher()
        self.lock = threading.RLock()
        self.dummy_hash = self.hasher.hash(secrets.token_urlsafe(32))
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS admin_account (
                    id INTEGER PRIMARY KEY CHECK(id=1), username TEXT NOT NULL,
                    password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    token_hash TEXT PRIMARY KEY, csrf_token TEXT NOT NULL,
                    expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS admin_login_failures (created_at REAL NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def configured(self):
        with self.lock, self.connect() as db:
            return db.execute('SELECT 1 FROM admin_account WHERE id=1').fetchone() is not None

    @staticmethod
    def validate_username(username):
        if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{2,39}', username):
            raise AuthError(400, 'invalid_username')
        return username.lower()

    @staticmethod
    def validate_password(password):
        if not isinstance(password, str) or not 15 <= len(password) <= 128:
            raise AuthError(400, 'invalid_password_length')
        try:
            password.encode('utf-8')
        except UnicodeError as error:
            raise AuthError(400, 'invalid_password') from error

    def _issue(self, db):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        now = self.clock()
        db.execute('DELETE FROM admin_sessions WHERE expires_at<=?', (now,))
        db.execute('INSERT INTO admin_sessions VALUES (?,?,?)',
                   (hashlib.sha256(token.encode()).hexdigest(), csrf, now + SESSION_SECONDS))
        return token

    def setup(self, username, password):
        username = self.validate_username(username)
        self.validate_password(password)
        password_hash = self.hasher.hash(password)
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM admin_account').fetchone():
                raise AuthError(409, 'already_configured')
            db.execute('INSERT INTO admin_account VALUES (1,?,?)', (username, password_hash))
            return self._issue(db)

    def _throttle(self, db):
        db.execute('DELETE FROM admin_login_failures WHERE created_at<=?', (self.clock()-LOGIN_WINDOW,))
        if db.execute('SELECT count(*) FROM admin_login_failures').fetchone()[0] >= LOGIN_LIMIT:
            raise AuthError(429, 'too_many_attempts')

    def _verify(self, db, username, password):
        self._throttle(db)
        account = db.execute('SELECT username,password_hash FROM admin_account WHERE id=1').fetchone()
        candidate = password if isinstance(password, str) and len(password) <= 128 else ''
        try:
            matched = self.hasher.verify(account['password_hash'] if account else self.dummy_hash, candidate)
        except (VerificationError, InvalidHashError, UnicodeError):
            matched = False
        valid_name = isinstance(username, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{2,39}', username)
        if not (matched and valid_name and account and hmac.compare_digest(account['username'].encode(), username.lower().encode())):
            db.execute('INSERT INTO admin_login_failures VALUES (?)', (self.clock(),))
            # Persist the attempt even though authentication raises below.
            db.commit()
            raise AuthError(401, 'invalid_credentials')
        return account

    def login(self, username, password):
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            account = self._verify(db, username, password)
            if self.hasher.check_needs_rehash(account['password_hash']):
                db.execute('UPDATE admin_account SET password_hash=? WHERE id=1', (self.hasher.hash(password),))
            db.execute('DELETE FROM admin_login_failures')
            return self._issue(db)

    def session(self, token):
        if not isinstance(token, str) or not 20 <= len(token) <= 128:
            return None
        with self.lock, self.connect() as db:
            row = db.execute('''SELECT s.csrf_token,s.expires_at,a.username
                                FROM admin_sessions s CROSS JOIN admin_account a
                                WHERE s.token_hash=? AND s.expires_at>? AND a.id=1''',
                             (hashlib.sha256(token.encode()).hexdigest(), self.clock())).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        with self.lock, self.connect() as db:
            db.execute('DELETE FROM admin_sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))

    def change_password(self, token, current_password, new_password):
        self.validate_password(new_password)
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('''SELECT a.username FROM admin_sessions s CROSS JOIN admin_account a
                                WHERE s.token_hash=? AND s.expires_at>? AND a.id=1''',
                             (hashlib.sha256(token.encode()).hexdigest(), self.clock())).fetchone()
            if not row:
                raise AuthError(401, 'login_required')
            try:
                self._verify(db, row['username'], current_password)
            except AuthError as error:
                if error.code == 'invalid_credentials':
                    raise AuthError(400, 'wrong_current_password') from error
                raise
            db.execute('UPDATE admin_account SET password_hash=? WHERE id=1', (self.hasher.hash(new_password),))
            db.execute('DELETE FROM admin_sessions')
            db.execute('DELETE FROM admin_login_failures')

    def reset_local(self, username, password):
        """Filesystem-owner recovery; never exposed through an HTTP endpoint."""
        username = self.validate_username(username); self.validate_password(password)
        password_hash = self.hasher.hash(password)
        with self.lock, self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO admin_account VALUES (1,?,?)', (username, password_hash))
            db.execute('DELETE FROM admin_sessions'); db.execute('DELETE FROM admin_login_failures')


def error_response(error):
    headers = {'Cache-Control': 'no-store'}
    if error.status == 429: headers['Retry-After'] = str(LOGIN_WINDOW)
    return JSONResponse({'detail': error.code, 'code': error.code}, status_code=error.status, headers=headers)


def same_origin(request):
    if request.headers.get('sec-fetch-site', 'none') not in {'same-origin', 'none'}:
        return False
    origin = request.headers.get('origin')
    return origin is None or origin == f'{request.url.scheme}://{request.url.netloc}'


async def credentials_body(request):
    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
        raise AuthError(415, 'json_required')
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 4096: raise AuthError(413, 'request_too_large')
    try:
        payload = json.loads(content)
    except (ValueError, UnicodeDecodeError):
        raise AuthError(400, 'invalid_request')
    if not isinstance(payload, dict): raise AuthError(400, 'invalid_request')
    return payload


def install_admin_security(app, database, frontend, *, auth=None):
    """Fail closed for all catalog-management routes, including future subroutes."""
    store = auth or AdminAuth(database)
    frontend = Path(frontend)
    app.state.admin_auth = store

    @app.exception_handler(AuthError)
    async def auth_error_handler(request, error):
        return error_response(error)

    @app.middleware('http')
    async def administration_guard(request, call_next):
        if request.url.hostname not in {'127.0.0.1', 'localhost', '::1'}:
            return error_response(AuthError(400, 'invalid_host'))
        path = posixpath.normpath('/'+request.url.path.replace('\\', '/').lstrip('/')).casefold().rstrip('/. ')
        protected = (path == '/api/demo-catalog/products' or path.startswith('/api/demo-catalog/products/')
                     or path == '/api/reindex' or path.startswith('/api/monitoring/')
                     or path in {'/api/auth/logout', '/api/auth/password'})
        private_page = path in PRIVATE_PAGES
        unsafe = request.method not in {'GET', 'HEAD', 'OPTIONS'}
        if unsafe and (protected or path.startswith('/api/auth/')) and not same_origin(request):
            return error_response(AuthError(403, 'invalid_origin'))
        actor = None
        if protected or private_page:
            actor = await run_in_threadpool(store.session, request.cookies.get(COOKIE))
            if not actor:
                if private_page and request.method in {'GET','HEAD'}:
                    return RedirectResponse('/admin-login.html?'+urlencode({'next':path}), status_code=303,
                                            headers={'Cache-Control':'no-store'})
                return error_response(AuthError(401, 'login_required'))
            if unsafe and not hmac.compare_digest(actor['csrf_token'].encode(), request.headers.get('x-csrf-token', '').encode()):
                return error_response(AuthError(403, 'invalid_csrf'))
        request.state.admin = actor
        response = await call_next(request)
        if protected or private_page or path.startswith('/api/auth/') or path == '/admin-login.html':
            response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        return response

    router = APIRouter(prefix='/api/auth', tags=['Local administrator'])
    def signed_in(request, token, status=200):
        response = JSONResponse({'authenticated':True}, status_code=status)
        response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                            secure=request.url.scheme=='https', samesite='strict', path='/')
        return response

    @router.get('/session')
    async def session_status(request: Request):
        actor = await run_in_threadpool(store.session, request.cookies.get(COOKIE))
        return {'configured':await run_in_threadpool(store.configured), 'authenticated':bool(actor),
                **({'username':actor['username'], 'role':'admin', 'csrf_token':actor['csrf_token']} if actor else {})}

    @router.post('/setup', status_code=201)
    async def setup(request: Request):
        try:
            if not request.client or not ipaddress.ip_address(request.client.host).is_loopback:
                raise AuthError(403, 'local_setup_only')
        except ValueError:
            raise AuthError(403, 'local_setup_only')
        payload = await credentials_body(request)
        if payload.get('password') != payload.get('confirm_password'):
            raise AuthError(400, 'password_mismatch')
        token = await run_in_threadpool(store.setup, payload.get('username'), payload.get('password'))
        return signed_in(request, token, 201)

    @router.post('/login')
    async def login(request: Request):
        payload = await credentials_body(request)
        token = await run_in_threadpool(store.login, payload.get('username'), payload.get('password'))
        return signed_in(request, token)

    @router.post('/logout')
    async def logout(request: Request):
        await run_in_threadpool(store.logout, request.cookies[COOKIE])
        response = JSONResponse({'authenticated':False}); response.delete_cookie(COOKIE, path='/')
        return response

    @router.post('/password')
    async def change_password(request: Request):
        payload = await credentials_body(request)
        if payload.get('new_password') != payload.get('confirm_password'):
            raise AuthError(400, 'password_mismatch')
        await run_in_threadpool(store.change_password, request.cookies[COOKIE],
                                payload.get('current_password'), payload.get('new_password'))
        response = JSONResponse({'password_changed':True, 'authenticated':False})
        response.delete_cookie(COOKIE, path='/'); return response

    app.include_router(router)

    @app.get('/admin-login.html', include_in_schema=False)
    def login_page():
        return FileResponse(frontend/'admin-login.html')

    @app.get('/admin-account.html', include_in_schema=False)
    def account_page():
        return FileResponse(frontend/'admin-account.html')
    return store
