(() => {
    const el = id => document.getElementById(id);
    const messages = {
        invalid_credentials:'اسم المستخدم أو كلمة المرور غير صحيحة.',
        too_many_attempts:'محاولات كثيرة. انتظر دقيقة ثم حاول مجددًا.',
        already_configured:'أُعدّ حساب الإدارة بالفعل. أعد تحميل الصفحة لتسجيل الدخول.',
        invalid_username:'استخدم اسمًا من 3 إلى 40 حرفًا إنجليزيًا أو رقمًا، يبدأ بحرف.',
        invalid_password_length:'كلمة المرور يجب أن تكون من 15 إلى 128 حرفًا.',
        password_mismatch:'تأكيد كلمة المرور لا يطابق كلمة المرور.',
        wrong_current_password:'كلمة المرور الحالية غير صحيحة.',
        local_setup_only:'إعداد الحساب متاح من الجهاز الذي يشغّل التطبيق فقط.',
        invalid_origin:'افتح صفحة الإدارة من عنوان التطبيق نفسه ثم حاول مجددًا.',
        login_required:'انتهت جلسة الإدارة. سجّل الدخول مجددًا.'
    };
    function show(id, text, error=false) {el(id).textContent=text;el(id).classList.toggle('error',error);}
    async function read(response) {
        let body;
        try {body=await response.json();} catch {throw new Error('تعذر قراءة رد الخادم. أعد المحاولة.');}
        if(!response.ok) throw new Error(messages[body.code] || 'تعذرت العملية. أعد المحاولة.');
        return body;
    }
    function destination() {
        const next=new URLSearchParams(location.search).get('next');
        return ['/demo-catalog.html','/admin-account.html'].includes(next) ? next : '/demo-catalog.html';
    }
    const form=el('auth-form');
    if(form) {
        let setup=false;
        async function load() {
            form.hidden=true;el('auth-retry').hidden=true;show('auth-status','');
            try {
                const session=await read(await fetch('/api/auth/session',{cache:'no-store',credentials:'same-origin'}));
                if(session.authenticated) {location.replace(destination());return;}
                setup=!session.configured;
                el('auth-title').textContent=setup?'إعداد حساب الإدارة':'دخول الإدارة';
                el('auth-description').textContent=setup?'أنشئ حساب الأدمن لهذا الجهاز. يُستخدم لإضافة المنتجات وتعديلها وحذفها.':'سجّل الدخول لإدارة منتجاتك وصورها.';
                el('auth-submit').textContent=setup?'إنشاء حساب الإدارة':'دخول الإدارة';
                for(const id of ['confirm-field','username-help','password-help'])el(id).hidden=!setup;
                el('auth-confirm').required=setup;
                el('auth-password').minLength=setup?15:1;
                el('auth-password').autocomplete=setup?'new-password':'current-password';
                if(setup&&!el('auth-username').value)el('auth-username').value='admin';
                form.hidden=false;
                if(new URLSearchParams(location.search).has('password_changed'))show('auth-status','تم تغيير كلمة المرور. سجّل الدخول بالكلمة الجديدة.');
                else if(new URLSearchParams(location.search).has('logged_out'))show('auth-status','تم تسجيل الخروج.');
            }catch(error){show('auth-status',error.message||'تعذر الاتصال بالخادم.',true);el('auth-retry').hidden=false;}
        }
        el('auth-retry').addEventListener('click',load);
        form.addEventListener('submit',async event=>{
            event.preventDefault();if(el('auth-submit').disabled)return;
            const password=el('auth-password').value;
            if(setup&&password!==el('auth-confirm').value){show('auth-status',messages.password_mismatch,true);return;}
            el('auth-submit').disabled=true;show('auth-status','جارٍ التحقق…');
            try {
                await read(await fetch('/api/auth/'+(setup?'setup':'login'),{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:el('auth-username').value,password,...(setup?{confirm_password:el('auth-confirm').value}:{})})}));
                el('auth-password').value='';el('auth-confirm').value='';location.replace(destination());
            }catch(error){show('auth-status',error.message||'تعذر الاتصال بالخادم.',true);}
            finally{el('auth-submit').disabled=false;}
        });
        load();
    }
    el('password-form')?.addEventListener('submit',async event=>{
        event.preventDefault();if(el('password-submit').disabled)return;
        if(el('new-password').value!==el('new-password-confirm').value){show('account-status',messages.password_mismatch,true);return;}
        el('password-submit').disabled=true;show('account-status','جارٍ تغيير كلمة المرور…');
        try {
            await read(await AdminSession.request('/api/auth/password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:el('current-password').value,new_password:el('new-password').value,confirm_password:el('new-password-confirm').value})}));
            for(const id of ['current-password','new-password','new-password-confirm'])el(id).value='';
            location.replace('/admin-login.html?password_changed=1');
        }catch(error){show('account-status',error.message||'تعذر الاتصال بالخادم.',true);}
        finally{el('password-submit').disabled=false;}
    });
})();
