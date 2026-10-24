const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const response=(status,body)=>({status,ok:status>=200&&status<300,json:async()=>body});
function harness(file,overrideFetch, pathname='/demo-catalog.html',search='') {
    const calls=[],redirects=[],elements=new Map();
    const location={origin:'http://127.0.0.1:8001',pathname,search,replace:url=>redirects.push(url)};
    function element(id){
        if(!elements.has(id))elements.set(id,{value:'',disabled:false,hidden:false,handlers:{},textContent:'',classList:{add(){},toggle(){}},addEventListener(name,handler){this.handlers[name]=handler;},replaceChildren(){this.cleared=true;}});
        return elements.get(id);
    }
    // Only actual page elements should exist for optional selectors.
    const ids=file==='admin-session.js'?['admin-username','admin-logout','catalog-products','catalog-status']:
        pathname==='/admin-account.html'?['password-form','password-submit','current-password','new-password','new-password-confirm','account-status']:
        ['auth-form','auth-title','auth-description','auth-submit','confirm-field','username-help','password-help','auth-confirm','auth-password','auth-username','auth-status','auth-retry'];
    ids.forEach(element);
    const context=vm.createContext({location,Headers,URL,URLSearchParams,document:{getElementById:id=>elements.get(id)||null,querySelectorAll:()=>[]},window:{addEventListener(){}},fetch:(url,options)=>{calls.push({url,options});return overrideFetch(url,options);}});
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/js',file),'utf8'),context);
    return {calls,redirects,element,context,event:{preventDefault(){}}};
}
const actor={configured:true,authenticated:true,username:'admin',csrf_token:'session-bound-token'};
test('private-page requests wait for authentication, attach CSRF only to mutations and never send credentials off origin',async()=>{
    const h=harness('admin-session.js',async url=>response(200,url.endsWith('/session')?actor:{}));
    const api=h.context.window.AdminSession;await api.ready;
    await api.request('/api/demo-catalog/products');
    await api.request('/api/reindex',{method:'POST'});
    assert.equal(h.calls[1].options.headers.has('X-CSRF-Token'),false);
    assert.equal(h.calls[2].options.headers.get('X-CSRF-Token'),actor.csrf_token);
    assert.equal(h.calls[2].options.credentials,'same-origin');
    assert.equal(h.calls[2].options.cache,'no-store');
    await assert.rejects(api.request('https://example.invalid/api/reindex',{method:'POST'}));
    assert.equal(h.calls.length,3);
});
test('a guest is redirected before inventory is requested',async()=>{
    const h=harness('admin-session.js',async()=>response(200,{configured:true,authenticated:false}));
    await assert.rejects(h.context.window.AdminSession.request('/api/demo-catalog/products'));
    assert.equal(h.calls.length,1);assert.match(h.redirects[0],/next=%2Fdemo-catalog.html/);
    assert.equal(h.element('catalog-products').cleared,true);
});
test('an expired server session clears private results and redirects without retrying a mutation',async()=>{
    const h=harness('admin-session.js',async url=>url.endsWith('/session')?response(200,actor):response(401,{}));
    await assert.rejects(h.context.window.AdminSession.request('/api/reindex',{method:'POST'}));
    assert.equal(h.calls.length,2);assert.equal(h.redirects.length,1);assert.equal(h.element('catalog-products').cleared,true);
});
test('logout must succeed on the server before the browser reports it',async()=>{
    let succeed=false;
    const h=harness('admin-session.js',async url=>url.endsWith('/session')?response(200,actor):response(succeed?200:500,{}));
    await assert.rejects(h.context.window.AdminSession.logout());assert.equal(h.redirects.length,0);
    succeed=true;await h.context.window.AdminSession.logout();
    assert.equal(h.redirects[0],'/admin-login.html?logged_out=1');
});
test('login uses an allowlisted destination even when next contains an external URL',async()=>{
    const h=harness('admin-auth.js',async()=>response(200,actor),'/admin-login.html','?next=https%3A%2F%2Fexample.invalid');
    await tick();assert.equal(h.redirects[0],'/demo-catalog.html');
});
test('first-run setup requires confirmation, posts to setup, and clears passwords after success',async()=>{
    const h=harness('admin-auth.js',async url=>response(url.endsWith('/session')?200:201,url.endsWith('/session')?{configured:false,authenticated:false}:{}),'/admin-login.html');
    await tick();assert.equal(h.element('auth-confirm').required,true);assert.equal(h.element('auth-password').minLength,15);
    h.element('auth-password').value='a long test password';h.element('auth-confirm').value='wrong';
    await h.element('auth-form').handlers.submit(h.event);assert.equal(h.calls.length,1);
    h.element('auth-confirm').value='a long test password';
    await h.element('auth-form').handlers.submit(h.event);
    assert.equal(h.calls[1].url,'/api/auth/setup');assert.equal(h.element('auth-password').value,'');
    assert.equal(h.element('auth-confirm').value,'');assert.equal(h.redirects[0],'/demo-catalog.html');
});
test('failed login remains on the form with a generic error and permits retry',async()=>{
    const h=harness('admin-auth.js',async url=>url.endsWith('/session')?response(200,{configured:true,authenticated:false}):response(401,{code:'invalid_credentials'}),'/admin-login.html');
    await tick();h.element('auth-username').value='admin';h.element('auth-password').value='wrong';
    await h.element('auth-form').handlers.submit(h.event);
    assert.equal(h.redirects.length,0);assert.equal(h.element('auth-submit').disabled,false);
    assert.match(h.element('auth-status').textContent,/اسم المستخدم أو كلمة المرور/);
});
test('password confirmation is checked before sending a change request',async()=>{
    const h=harness('admin-auth.js',async()=>response(500,{}),'/admin-account.html');
    let requests=0;h.context.AdminSession={request:async()=>{requests++;return response(200,{});}};
    h.element('new-password').value='a new test password';h.element('new-password-confirm').value='different';
    await h.element('password-form').handlers.submit(h.event);
    assert.equal(requests,0);assert.equal(h.redirects.length,0);
    assert.match(h.element('account-status').textContent,/لا يطابق/);
});
test('a wrong current password does not announce a successful change or redirect',async()=>{
    const h=harness('admin-auth.js',async()=>response(500,{}),'/admin-account.html');
    h.context.AdminSession={request:async()=>response(400,{code:'wrong_current_password'})};
    h.element('new-password').value=h.element('new-password-confirm').value='a new test password';
    await h.element('password-form').handlers.submit(h.event);
    assert.equal(h.redirects.length,0);assert.equal(h.element('password-submit').disabled,false);
    assert.match(h.element('account-status').textContent,/الحالية غير صحيحة/);
});
test('a successful password change clears the fields and sends the user to a fresh login',async()=>{
    const h=harness('admin-auth.js',async()=>response(500,{}),'/admin-account.html');
    let sent;h.context.AdminSession={request:async(url,options)=>{sent={url,options};return response(200,{password_changed:true,authenticated:false});}};
    h.element('current-password').value='old test password';
    h.element('new-password').value=h.element('new-password-confirm').value='a new test password';
    await h.element('password-form').handlers.submit(h.event);
    assert.equal(sent.url,'/api/auth/password');
    assert.equal(JSON.parse(sent.options.body).current_password,'old test password');
    for(const id of ['current-password','new-password','new-password-confirm'])assert.equal(h.element(id).value,'');
    assert.equal(h.redirects[0],'/admin-login.html?password_changed=1');
});
