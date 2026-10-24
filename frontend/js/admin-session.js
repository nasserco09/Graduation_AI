/* Administration credentials stay in an HttpOnly cookie; CSRF stays in memory. */
(() => {
    const privatePages = new Set(['/demo-catalog.html', '/admin-account.html']);
    let actor = null;
    function loginUrl() {
        const next = privatePages.has(location.pathname) ? location.pathname : '/demo-catalog.html';
        return '/admin-login.html?next=' + encodeURIComponent(next);
    }
    function expire() {
        actor = null;
        document.getElementById('catalog-products')?.replaceChildren();
        for (const dialog of document.querySelectorAll('dialog[open]')) dialog.close();
        location.replace(loginUrl());
    }
    async function check() {
        const response = await fetch('/api/auth/session', {cache:'no-store', credentials:'same-origin'});
        if (!response.ok) throw new Error('تعذر التحقق من جلسة الإدارة. أعد تحميل الصفحة.');
        actor = await response.json();
        if (!actor.authenticated) { expire(); throw new Error('انتهت جلسة الإدارة. سجّل الدخول مجددًا.'); }
        const username = document.getElementById('admin-username');
        if (username) username.textContent = actor.username;
        return actor;
    }
    const ready = check();
    // A network failure is displayed by the calling page; avoid an unhandled rejection.
    ready.catch(error => {
        const output = document.getElementById('account-status') || document.getElementById('catalog-status');
        if (output) { output.textContent=error.message; output.classList.add('error'); }
    });
    async function request(url, options={}) {
        await ready;
        const target = new URL(url, location.origin);
        if (target.origin !== location.origin) throw new Error('طلب الإدارة يجب أن يكون داخل الموقع نفسه.');
        if (!actor) throw new Error('سجّل الدخول إلى الإدارة مجددًا.');
        const headers = new Headers(options.headers);
        if (!['GET','HEAD','OPTIONS'].includes((options.method || 'GET').toUpperCase())) headers.set('X-CSRF-Token', actor.csrf_token);
        const response = await fetch(target.pathname+target.search, {...options, headers, credentials:'same-origin', cache:'no-store'});
        if (response.status === 401) { expire(); throw new Error('انتهت جلسة الإدارة. سجّل الدخول مجددًا.'); }
        if (response.status === 403) throw new Error('تعذر التحقق من صلاحية العملية. أعد تحميل الصفحة ثم حاول مجددًا.');
        return response;
    }
    async function logout() {
        const response = await request('/api/auth/logout', {method:'POST'});
        if (!response.ok) throw new Error('تعذر تسجيل الخروج. حاول مجددًا.');
        actor = null;
        location.replace('/admin-login.html?logged_out=1');
    }
    document.getElementById('admin-logout')?.addEventListener('click', async event => {
        const button=event.currentTarget; button.disabled=true;
        try { await logout(); }
        catch(error) {
            const output=document.getElementById('account-status') || document.getElementById('catalog-status');
            if(output) {output.textContent=error.message;output.classList.add('error');}
            button.disabled=false;
        }
    });
    window.addEventListener('pageshow', event => { if(event.persisted) check().catch(()=>{}); });
    window.AdminSession = {ready, request, logout};
})();
