const get = id => document.getElementById(id);
const API = '/api/demo-catalog';
const CATEGORIES = {dress:'فساتين',hat:'قبعات',longsleeve:'ملابس بأكمام طويلة',outwear:'جاكيتات وملابس خارجية',pants:'بناطيل',shirt:'قمصان',shoes:'أحذية',shorts:'سراويل قصيرة',skirt:'تنانير','t-shirt':'تيشيرتات'};
const CURRENCIES = {YER:'ريال يمني',SAR:'ريال سعودي',USD:'دولار أمريكي'};
let products = [], catalogGeneration = 0, searchGeneration = 0;
let editingProduct = null, deletingProduct = null, editorPhotos = [], fileSequence = 0;
let editorBusy = false, deleteBusy = false, queryPreviewUrl = null;

function status(id, text, error=false) {
    const el=get(id); el.textContent=text; el.classList.toggle('error',error);
}
function imageUrl(url) { return typeof url==='string' && url.startsWith(API+'/images/') ? url : ''; }
function normalizePrice(value) {
    return value.trim().replace(/[٠-٩]/g,d=>String(d.charCodeAt(0)-1632)).replace(/[۰-۹]/g,d=>String(d.charCodeAt(0)-1776)).replace(/٫/g,'.');
}
function productFields() {
    const price=normalizePrice(get('product-price').value);
    if(price && !/^[0-9]{1,9}(?:\.[0-9]{1,2})?$/.test(price)) throw new Error('أدخل سعرًا موجبًا أو صفرًا، حتى منزلتين عشريتين ودون فواصل آلاف.');
    const name=get('product-name').value.trim();
    if(!name) throw new Error('اكتب اسم المنتج.');
    return {name, category:get('product-category').value, price, currency:get('product-currency').value, available:get('product-available').checked};
}
async function json(response) {
    let body;
    try { body=await response.json(); } catch { throw new Error('تعذر قراءة رد الخادم. أعد المحاولة.'); }
    if(!response.ok) {
        if(response.status===409) throw new Error('تغير هذا المنتج في نافذة أخرى. أغلق النافذة وحدّث القائمة قبل المحاولة مجددًا.');
        if(response.status===404) throw new Error('لم يعد هذا المنتج أو إحدى صوره موجودًا. حدّث القائمة.');
        const detail=typeof body.detail==='string' ? body.detail : '';
        if(/Price/.test(detail)) throw new Error('السعر غير صالح. استخدم حتى منزلتين عشريتين.');
        if(/configuration changed/.test(detail)) throw new Error('إعدادات كتالوج البحث غير متوافقة.');
        if(/image|Image|Upload|pixel|empty/i.test(detail)) throw new Error('تحقق من الصور: من صورة إلى 5 صور سليمة، حتى 8MB لكل صورة، وبحد أقصى 25 مليون بكسل.');
        if(/name|category|currency|Availability/.test(detail)) throw new Error('راجع اسم المنتج والفئة والسعر والعملة.');
        throw new Error('تعذر حفظ العملية. راجع البيانات أو الاتصال بالخادم وأعد المحاولة.');
    }
    return body;
}
function validFiles(files) {
    if(!files.length || files.length>5) throw new Error('اختر من صورة إلى خمس صور للمنتج.');
    if(files.some(f=>!f.size || f.size>8*1024*1024)) throw new Error('اختر صورًا غير فارغة، حتى 8MB لكل صورة.');
    const types=['image/jpeg','image/png','image/webp','image/bmp'];
    if(files.some(f=>f.type && !types.includes(f.type))) throw new Error('اختر صور PNG أو JPG أو WebP أو BMP.');
}
function node(tag, className='', text='') {
    const el=document.createElement(tag); if(className)el.className=className; if(text)el.textContent=text; return el;
}
function button(text, className, action, label) {
    const el=node('button',className,text); el.type='button'; if(label)el.setAttribute('aria-label',label); el.addEventListener('click',action); return el;
}
function card(product, searched=false) {
    const article=node('article','product-card'); article.dataset.productId=product.product_id;
    const photo=node('div','product-photo'), image=node('img');
    image.alt=product.name; image.loading='lazy'; image.src=imageUrl(searched?product.image_url:product.images[0]?.url);
    photo.append(image,node('span','availability-badge'+(product.available===false?' unavailable':''),product.available===false?'غير متوفر':'متوفر للبحث'));
    const body=node('div','card-body');
    body.append(node('p','product-category',CATEGORIES[product.category]||'بدون فئة'),node('h3','',product.name));
    const price=node('p','product-price'+(product.price==null?' no-price':''));
    if(product.price==null)price.textContent='السعر غير محدد';
    else {price.textContent=Number(product.price).toLocaleString('ar-YE',{maximumFractionDigits:2});price.append(node('span','currency',CURRENCIES[product.currency]||product.currency));}
    body.append(price,node('p','photo-counter',searched?`${Math.round(product.score*100)}% تشابه بصري · ${product.images.length} صور`:`${product.images.length} صور للمنتج`));
    if(product.images.length>1) {
        const gallery=node('div','gallery');
        product.images.forEach((item,index)=>{
            const el=button(`صورة ${index+1}`,'',()=>{image.src=imageUrl(item.url);for(const child of gallery.children)child.setAttribute('aria-pressed',String(child===el));},`صورة ${index+1} للمنتج ${product.name}`);
            el.setAttribute('aria-pressed',String(imageUrl(item.url)===image.getAttribute('src')));gallery.append(el);
        });body.append(gallery);
    }
    if(!searched) {
        const actions=node('div','card-actions');
        actions.append(button('تعديل المنتج','edit-button',()=>openEditor(product),'تعديل '+product.name),button('حذف','delete-button',()=>openDelete(product),'حذف '+product.name));body.append(actions);
    }
    article.append(photo,body);return article;
}
function filterProducts(items, query, category, availability, sort) {
    const term=query.trim().toLocaleLowerCase('ar');
    const result=items.filter(p=>(!term||p.name.toLocaleLowerCase('ar').includes(term)) && (!category||(category==='uncategorized'?!p.category:p.category===category)) && (availability==='all'||(availability==='available')===p.available));
    if(sort==='name')result.sort((a,b)=>a.name.localeCompare(b.name,'ar'));
    return result;
}
function renderCatalog() {
    const shown=filterProducts(products,get('catalog-query').value,get('catalog-category').value,get('catalog-availability').value,get('catalog-sort').value);
    get('product-count').textContent=`${shown.length} من ${products.length} منتج`;
    get('stat-total').textContent=products.length;
    get('stat-available').textContent=products.filter(p=>p.available).length;
    get('stat-unavailable').textContent=products.filter(p=>!p.available).length;
    get('stat-images').textContent=products.reduce((sum,p)=>sum+p.images.length,0);
    get('catalog-products').replaceChildren(...shown.map(p=>card(p)));
    if(!shown.length) {
        const empty=node('div','empty-state');
        empty.append(node('h3','',products.length?'لا توجد منتجات تطابق الفلاتر':'ابدأ بأول منتج في كتالوجك'),node('p','',products.length?'جرّب اسمًا آخر أو أزل الفلاتر لعرض جميع المنتجات.':'أضف اسم المنتج وصوره، وسيصبح جاهزًا للبحث البصري.'));
        empty.append(button(products.length?'مسح الفلاتر':'إضافة منتج','',()=>products.length?resetFilters():openEditor()));get('catalog-products').append(empty);
    }
}
async function refreshCatalog(message='') {
    const generation=++catalogGeneration;get('refresh-catalog').disabled=true;
    status('catalog-status','جارٍ تحميل المنتجات…');
    try {
        const data=await json(await AdminSession.request(API+'/products',{cache:'no-store'}));
        if(generation!==catalogGeneration)return false;
        products=data.products;renderCatalog();status('catalog-status',message);return true;
    } catch(error) {if(generation===catalogGeneration)status('catalog-status','تعذر تحميل المنتجات. '+error.message,true);return false;}
    finally {if(generation===catalogGeneration)get('refresh-catalog').disabled=false;}
}
function resetFilters() {
    get('catalog-query').value='';get('catalog-category').value='';get('catalog-availability').value='all';get('catalog-sort').value='newest';renderCatalog();
}
function clearSearchAfterEdit() {
    searchGeneration++;get('search-submit').disabled=false;get('search-results').replaceChildren();get('search-results-section').hidden=true;status('search-status','تم تحديث المنتجات؛ أعد البحث لعرض بياناتها الجديدة.');
}
function releasePhotos() { for(const photo of editorPhotos)if(photo.file)URL.revokeObjectURL(photo.url);editorPhotos=[]; }
function closeEditor() {if(editorBusy)return;get('product-dialog').close();releasePhotos();}
function openEditor(product=null) {
    editingProduct=product;releasePhotos();get('product-form').reset();status('product-status','');
    get('product-title').textContent=product?'تعديل المنتج':'إضافة منتج جديد';get('product-save').textContent=product?'حفظ التعديلات':'إضافة المنتج';
    for(const key of ['name','category','price','currency'])get('product-'+key).value=product?.[key]??(key==='currency'?'YER':'');
    get('product-available').checked=product?.available!==false;
    editorPhotos=(product?.images||[]).map(item=>({key:item.image_id,url:imageUrl(item.url)}));renderEditorPhotos();
    get('product-dialog').showModal();get('product-name').focus();
}
function renderEditorPhotos() {
    get('photo-count').textContent=`${editorPhotos.length} / 5`;get('editor-images').replaceChildren();
    editorPhotos.forEach((photo,index)=>{
        const figure=node('figure','editor-photo'),img=node('img');img.src=photo.url;img.alt=`صورة المنتج ${index+1}`;
        const caption=node('figcaption');
        if(index===0)caption.append(node('span','cover-label','الصورة الرئيسية'));
        else caption.append(button('اجعلها الرئيسية','',()=>{editorPhotos.splice(index,1);editorPhotos.unshift(photo);renderEditorPhotos();},`اجعل صورة ${index+1} الرئيسية`));
        caption.append(button('إزالة','remove-photo',()=>{if(photo.file)URL.revokeObjectURL(photo.url);editorPhotos.splice(index,1);renderEditorPhotos();},`إزالة صورة ${index+1}`));
        figure.append(img,caption);get('editor-images').append(figure);
    });
}
function setEditorBusy(busy) {
    editorBusy=busy;for(const el of get('product-dialog').querySelectorAll('input,select,button'))el.disabled=busy;
}
function openDelete(product) {deletingProduct=product;get('delete-name').textContent=product.name;status('delete-status','');get('delete-dialog').showModal();get('delete-cancel').focus();}
function closeDelete() {if(!deleteBusy)get('delete-dialog').close();}
function setDeleteBusy(busy) {deleteBusy=busy;get('delete-confirm').disabled=busy;get('delete-cancel').disabled=busy;}
function appendFields(body,details) {for(const [key,value] of Object.entries(details))body.append(key,String(value));}
function buildImagePayload(body) {
    let index=0;const order=[];
    for(const photo of editorPhotos) {
        if(photo.file){order.push('new:'+index++);body.append('images',photo.file);}
        else order.push(photo.key);
    }
    body.append('image_order',JSON.stringify(order));
}
for(const id of ['catalog-category','product-category','search-category']) {
    for(const [value,label] of Object.entries(CATEGORIES)){const option=node('option','',label);option.value=value;get(id).append(option);}
}
get('add-product').addEventListener('click',()=>openEditor());
get('refresh-catalog').addEventListener('click',()=>refreshCatalog());
get('reset-filters').addEventListener('click',resetFilters);
for(const id of ['catalog-query','catalog-category','catalog-availability','catalog-sort'])get(id).addEventListener(id==='catalog-query'?'input':'change',renderCatalog);
get('product-close').addEventListener('click',closeEditor);get('product-cancel').addEventListener('click',closeEditor);
get('product-dialog').addEventListener('cancel',event=>{event.preventDefault();closeEditor();});
get('delete-cancel').addEventListener('click',closeDelete);
get('delete-dialog').addEventListener('cancel',event=>{event.preventDefault();closeDelete();});
get('product-images').addEventListener('change',()=>{
    const files=Array.from(get('product-images').files);
    try {
        if(!files.length)return;validFiles(files);
        if(editorPhotos.length+files.length>5)throw new Error('الحد الأقصى خمس صور. أزل صورة قبل إضافة المزيد.');
        for(const file of files)editorPhotos.push({key:'file:'+fileSequence++,url:URL.createObjectURL(file),file});renderEditorPhotos();status('product-status','');
    }catch(error){status('product-status',error.message,true);}
    finally{get('product-images').value='';}
});
get('product-form').addEventListener('submit',async event=>{
    event.preventDefault();if(editorBusy)return;
    try {
        const details=productFields();if(!editorPhotos.length)throw new Error('أضف صورة واحدة على الأقل للمنتج.');
        const body=new FormData();appendFields(body,details);let url=API+'/products',method='POST';
        if(editingProduct) {
            url+='/'+encodeURIComponent(editingProduct.product_id)+'/content';method='PUT';body.append('revision',String(editingProduct.revision));buildImagePayload(body);
        } else for(const photo of editorPhotos)body.append('images',photo.file);
        setEditorBusy(true);status('product-status','جارٍ حفظ المنتج وتجهيز الصور الجديدة للبحث…');
        await json(await AdminSession.request(url,{method,body}));
        const message=editingProduct?'تم حفظ بيانات المنتج وصوره.':'تمت إضافة المنتج وأصبح جاهزًا للبحث إذا كان متوفرًا.';
        clearSearchAfterEdit();setEditorBusy(false);closeEditor();await refreshCatalog(message);get('add-product').focus();
    }catch(error){status('product-status',error.message,true);}
    finally{setEditorBusy(false);}
});
get('delete-confirm').addEventListener('click',async()=>{
    if(deleteBusy||!deletingProduct)return;
    setDeleteBusy(true);status('delete-status','جارٍ حذف المنتج…');
    try {
        await json(await AdminSession.request(API+'/products/'+encodeURIComponent(deletingProduct.product_id)+'?revision='+encodeURIComponent(deletingProduct.revision),{method:'DELETE'}));
        clearSearchAfterEdit();setDeleteBusy(false);closeDelete();deletingProduct=null;await refreshCatalog('تم حذف المنتج وصوره من الكتالوج.');get('add-product').focus();
    }catch(error){status('delete-status',error.message,true);}
    finally{setDeleteBusy(false);}
});
get('query-image').addEventListener('change',()=>{
    if(queryPreviewUrl)URL.revokeObjectURL(queryPreviewUrl);
    const file=get('query-image').files[0];get('query-preview').hidden=!file;
    if(file){queryPreviewUrl=URL.createObjectURL(file);get('query-preview').src=queryPreviewUrl;}
});
get('search-form').addEventListener('submit',async event=>{
    event.preventDefault();const generation=++searchGeneration;get('search-submit').disabled=true;
    get('search-results').replaceChildren();get('search-results-section').hidden=true;
    try {
        const files=Array.from(get('query-image').files);validFiles(files);
        const body=new FormData();body.append('image',files[0]);body.append('category',get('search-category').value);status('search-status','جارٍ البحث في المنتجات المضافة…');
        const data=await json(await fetch(API+'/search',{method:'POST',body}));
        if(generation!==searchGeneration)return;
        get('search-results').replaceChildren(...data.results.map(p=>card(p,true)));get('search-results-section').hidden=!data.results.length;
        status('search-status',data.results.length?`ظهرت ${data.results.length} منتجات؛ كل منتج يظهر مرة واحدة.`:'لا توجد منتجات متوفرة ضمن الفئة المختارة. راجع المنتجات وحالة توفرها.');
    }catch(error){if(generation===searchGeneration)status('search-status','تعذر البحث: '+error.message,true);}
    finally{if(generation===searchGeneration)get('search-submit').disabled=false;}
});
refreshCatalog();
