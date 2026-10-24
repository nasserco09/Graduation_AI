(() => {
    const el=id=>document.getElementById(id), API='/api/demo-catalog/products';
    const errors={
        backup_invalid:'الملف غير سليم أو ليس نسخة احتياطية للكتالوج. اختر ملفًا صحيحًا.',
        backup_too_large:'حجم النسخة يتجاوز الحد المسموح 200MB.',
        backup_incompatible:'هذه النسخة تستخدم إعدادات بحث مختلفة ولا يمكن استرجاعها هنا.',
        restore_preview_expired:'انتهت معاينة النسخة. اختر الملف مجددًا وراجع المحتوى قبل الاسترجاع.',
        catalog_changed:'تغير الكتالوج بعد المعاينة. اختر الملف مجددًا لمراجعة الحالة الحالية.',
        recovery_not_found:'النسخة المحفوظة لم تعد موجودة. حدّث القائمة.'
    };
    let generation=0, preview=null, restoring=false, exporting=false;
    function show(id,text,error=false){el(id).textContent=text;el(id).classList.toggle('error',error);}
    async function errorFor(response){
        let body={};try{body=await response.json();}catch{}
        return new Error(errors[body.code]||'تعذرت العملية. راجع الاتصال وحدّث الصفحة قبل إعادة المحاولة.');
    }
    async function read(response){if(!response.ok)throw await errorFor(response);return response.json();}
    function node(tag,text=''){const result=document.createElement(tag);result.textContent=text;return result;}
    function date(value){const stamp=new Date(value);return Number.isNaN(stamp.getTime())?'تاريخ غير محدد':stamp.toLocaleString('ar-YE');}
    function safeRecoveryUrl(url){return typeof url==='string'&&/^\/api\/demo-catalog\/products\/recovery\/[A-Za-z0-9_-]+$/.test(url);}
    async function download(url){
        if(url!==API+'/backup'&&!safeRecoveryUrl(url))throw new Error('رابط النسخة غير صالح. حدّث القائمة.');
        const response=await AdminSession.request(url);
        if(!response.ok)throw await errorFor(response);
        const blob=await response.blob();if(!blob.size)throw new Error('ملف النسخة فارغ. حاول مجددًا.');
        const objectUrl=URL.createObjectURL(blob),link=node('a');
        link.href=objectUrl;link.download='fashion-catalog-'+new Date().toISOString().slice(0,10)+'.zip';
        document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(objectUrl),1000);
    }
    async function history(){
        const button=el('backup-history-refresh');button.disabled=true;
        try{
            const data=await read(await AdminSession.request(API+'/backups'));
            const list=el('backup-history-list');list.replaceChildren();
            if(!data.backups.length){const note=node('p','لا توجد نسخ استرجاع تلقائية بعد.');note.className='field-hint';list.append(note);}
            for(const item of data.backups){
                const row=node('div');row.className='backup-history-item';
                row.append(node('span',`${date(item.created_at)} · ${item.product_count} منتج · ${item.image_count} صورة`));
                const save=node('button','تنزيل النسخة');save.type='button';save.className='button secondary';save.disabled=!safeRecoveryUrl(item.download_url);
                save.addEventListener('click',async()=>{save.disabled=true;try{await download(item.download_url);show('backup-status','تم تجهيز تنزيل النسخة السابقة.');}catch(error){show('backup-status',error.message,true);}finally{save.disabled=false;}});
                row.append(save);list.append(row);
            }
        }catch(error){el('backup-history-list').replaceChildren(node('p','تعذر تحميل النسخ المحفوظة. استخدم تحديث النسخ لإعادة المحاولة.'));}
        finally{button.disabled=false;}
    }
    el('backup-export').addEventListener('click',async()=>{
        if(exporting||restoring)return;exporting=true;el('backup-export').disabled=true;show('backup-status','جارٍ تجهيز النسخة الاحتياطية…');
        try{await download(API+'/backup');show('backup-status','تم تجهيز تنزيل النسخة الاحتياطية. احتفظ بالملف في مكان مناسب.');}
        catch(error){show('backup-status',error.message,true);}
        finally{exporting=false;el('backup-export').disabled=false;}
    });
    function close(){if(restoring)return;generation++;preview=null;el('backup-file').value='';el('restore-dialog').close();}
    el('restore-cancel').addEventListener('click',close);
    el('restore-dialog').addEventListener('cancel',event=>{event.preventDefault();close();});
    el('backup-file').addEventListener('change',async()=>{
        if(restoring)return;
        const current=++generation,file=el('backup-file').files[0];preview=null;if(!file)return;
        show('backup-status','جارٍ فحص محتوى النسخة…');
        try{
            if(file.size>200*1024*1024)throw new Error(errors.backup_too_large);
            if(!file.size)throw new Error(errors.backup_invalid);
            const body=new FormData();body.append('backup',file);
            const data=await read(await AdminSession.request(API+'/restore/preview',{method:'POST',body}));
            if(current!==generation)return;preview=data;
            el('restore-summary').textContent=`النسخة المختارة: ${data.product_count} منتج و${data.image_count} صورة. تاريخها: ${date(data.created_at)}.`;
            el('restore-current').textContent=`الكتالوج الحالي: ${data.current_product_count} منتج و${data.current_image_count} صورة.`;
            show('restore-status','');show('backup-status','تم فحص النسخة. راجع التفاصيل قبل تأكيد الاسترجاع.');
            el('restore-dialog').showModal();el('restore-cancel').focus();
        }catch(error){if(current===generation){show('backup-status',error.message,true);el('backup-file').value='';}}
    });
    el('restore-confirm').addEventListener('click',async()=>{
        if(restoring||!preview)return;restoring=true;
        for(const id of ['restore-confirm','restore-cancel','backup-export','backup-file'])el(id).disabled=true;
        show('restore-status','جارٍ حفظ نسخة من الحالة الحالية واسترجاع الكتالوج…');
        try{
            await read(await AdminSession.request(API+'/restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:preview.token})}));
            restoring=false;close();window.dispatchEvent(new Event('catalog-restored'));
            show('backup-status','تم استرجاع الكتالوج. نسخة الحالة السابقة متاحة في النسخ المحفوظة أدناه.');await history();
        }catch(error){show('restore-status',error.message,true);}
        finally{restoring=false;for(const id of ['restore-confirm','restore-cancel','backup-export','backup-file'])el(id).disabled=false;}
    });
    el('backup-history-refresh').addEventListener('click',history);
    history();
})();
