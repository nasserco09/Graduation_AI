const get = id => document.getElementById(id);
const API = '/api/demo-catalog';
const CATEGORIES = {"dress": "فساتين", "hat": "قبعات", "longsleeve": "ملابس بأكمام طويلة", "outwear": "جاكيتات وملابس خارجية", "pants": "بناطيل", "shirt": "قمصان", "shoes": "أحذية", "shorts": "سراويل قصيرة", "skirt": "تنانير", "t-shirt": "تيشيرتات"};
const CURRENCIES = {YER:'ريال يمني',SAR:'ريال سعودي',USD:'دولار أمريكي'};
let editingProductId=null, editPreviousFocus=null, searchGeneration=0;
function closeEditDialog() { get('edit-dialog').hidden=true;document.body.style.overflow='';editPreviousFocus?.focus(); }
function productFields(prefix) {
    return {name:get(prefix+'-name').value.trim(),category:get(prefix+'-category').value,price:get(prefix+'-price').value.trim() || null,currency:get(prefix+'-currency').value,available:get(prefix+'-available').checked};
}
function clearSearchAfterEdit() { searchGeneration++;get('search-submit').disabled=false;get('search-results').replaceChildren();get('search-results-section').hidden=true;status('search-status','تم تحديث المنتجات؛ أعد البحث لعرض بياناتها الجديدة.'); }
function editProduct(product) {
    editingProductId=product.product_id;editPreviousFocus=document.activeElement;
    for(const key of ['name','category','price','currency'])get('edit-'+key).value=product[key] ?? (key==='currency'?'YER':'');
    get('edit-available').checked=product.available!==false;status('edit-status','');get('edit-dialog').hidden=false;document.body.style.overflow='hidden';get('edit-name').focus();
}
let addPreviewUrls = [], queryPreviewUrl = null;
function status(id, text, error=false) { get(id).textContent=text; get(id).classList.toggle('error',error); }
async function json(response) {
    const body=await response.json();
    if(!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'تعذر إكمال الطلب');
    return body;
}
function validFiles(files) {
    if(!files.length || files.length>5) throw new Error('اختر من صورة إلى خمس صور للمنتج');
    if(files.some(f=>f.size>8*1024*1024)) throw new Error('حجم كل صورة يجب ألا يزيد على 8MB');
}
function imageUrl(url) { return typeof url==='string' && url.startsWith(API+'/images/') ? url : ''; }
function card(product, searched=false) {
    const article=document.createElement('article');
    const image=document.createElement('img'); image.alt=product.name;
    image.src=imageUrl(searched ? product.image_url : product.images[0]?.url);
    article.appendChild(image);
    const title=document.createElement('h3'); title.textContent=product.name; article.appendChild(title);
    const detail=document.createElement('p');
    detail.textContent=searched ? `${Math.round(product.score*100)}% تشابه بصري · ${product.images.length} صور` : `${product.images.length} صور للمنتج`;
    article.appendChild(detail);
    const metadata=document.createElement('p');metadata.className='product-meta';
    metadata.textContent=`${CATEGORIES[product.category] || 'فئة غير محددة'} · ${product.price == null ? 'السعر غير محدد' : product.price+' '+CURRENCIES[product.currency]}`;
    article.appendChild(metadata);
    const availability=document.createElement('p');availability.textContent=product.available===false?'غير متوفر · لا يظهر في البحث':'متوفر';availability.className=product.available===false?'unavailable':'product-meta';article.appendChild(availability);
    if(!searched) {const edit=document.createElement('button');edit.type='button';edit.textContent='تعديل البيانات';edit.setAttribute('aria-label','تعديل بيانات '+product.name);edit.addEventListener('click',()=>editProduct(product));article.appendChild(edit);}
    if(product.images.length>1) {
        const gallery=document.createElement('div');gallery.className='gallery';
        product.images.forEach((photo,index)=>{
            const button=document.createElement('button');button.type='button';button.textContent=`صورة ${index+1}`;
            button.setAttribute('aria-label',`صورة ${index+1} للمنتج ${product.name}`);
            button.setAttribute('aria-pressed',String(imageUrl(photo.url)===image.getAttribute('src')));
            button.addEventListener('click',()=>{image.src=imageUrl(photo.url);for(const sibling of gallery.children)sibling.setAttribute('aria-pressed',String(sibling===button));});
            gallery.appendChild(button);
        });article.appendChild(gallery);
    }
    return article;
}
async function refreshCatalog() {
    try {
        const data=await json(await fetch(API+'/products'));
        get('catalog-products').replaceChildren(...data.products.map(p=>card(p)));
        get('product-count').textContent=`(${data.products.length})`;
        get('catalog-status').textContent=data.products.length ? '' : 'لم تضف أي منتج بعد. ابدأ بإضافة منتج من الأعلى.';
    }catch(error){get('catalog-status').textContent='تعذر تحميل المنتجات: '+error.message;}
}
get('product-images').addEventListener('change',()=>{
    addPreviewUrls.forEach(URL.revokeObjectURL);addPreviewUrls=[];get('add-preview').replaceChildren();
    const files=Array.from(get('product-images').files);
    try {validFiles(files);status('add-status','');for(const file of files){const url=URL.createObjectURL(file);addPreviewUrls.push(url);const img=document.createElement('img');img.src=url;img.alt='معاينة صورة المنتج';get('add-preview').appendChild(img);}}
    catch(error){status('add-status',error.message,true);}
});
get('query-image').addEventListener('change',()=>{
    if(queryPreviewUrl) URL.revokeObjectURL(queryPreviewUrl);
    const file=get('query-image').files[0];get('query-preview').hidden=!file;
    if(file){queryPreviewUrl=URL.createObjectURL(file);get('query-preview').src=queryPreviewUrl;}
});
get('add-form').addEventListener('submit',async event=>{
    event.preventDefault();get('add-submit').disabled=true;
    try {
        const files=Array.from(get('product-images').files);validFiles(files);
        const name=get('product-name').value.trim();if(!name)throw new Error('اكتب اسم المنتج');
        const body=new FormData();const details=productFields('product');for(const [key,value] of Object.entries(details))body.append(key,value==null?'':String(value));files.forEach(file=>body.append('images',file));
        status('add-status','جارٍ حفظ المنتج وتجهيز صوره للبحث…');
        const product=await json(await fetch(API+'/products',{method:'POST',body}));
        status('add-status',`تمت إضافة «${product.name}» بـ${product.image_count} صور، وأصبح جاهزًا للبحث.`);
        get('add-form').reset();addPreviewUrls.forEach(URL.revokeObjectURL);addPreviewUrls=[];get('add-preview').replaceChildren();await refreshCatalog();
    }catch(error){status('add-status','لم تتم الإضافة: '+error.message,true);}
    finally{get('add-submit').disabled=false;}
});
get('search-form').addEventListener('submit',async event=>{
    event.preventDefault();const generation=++searchGeneration;get('search-submit').disabled=true;
    get('search-results').replaceChildren();get('search-results-section').hidden=true;
    try {
        const files=Array.from(get('query-image').files);validFiles(files);
        const body=new FormData();body.append('image',files[0]);body.append('category',get('search-category').value);status('search-status','جارٍ البحث في المنتجات المضافة…');
        const data=await json(await fetch(API+'/search',{method:'POST',body}));
        if(generation!==searchGeneration)return;
        get('search-results').replaceChildren(...data.results.map(p=>card(p,true)));
        get('search-results-section').hidden=!data.results.length;
        status('search-status',data.results.length ? `ظهرت ${data.results.length} منتجات؛ كل منتج يظهر مرة واحدة.` : 'لا توجد منتجات متوفرة ضمن الفئة المختارة. راجع المنتجات وحالة توفرها.');
    }catch(error){if(generation===searchGeneration)status('search-status','تعذر البحث: '+error.message,true);}
    finally{if(generation===searchGeneration)get('search-submit').disabled=false;}
});
refreshCatalog();

get('edit-cancel').addEventListener('click',()=>closeEditDialog());
document.addEventListener('keydown',event=>{
    if(get('edit-dialog').hidden)return;
    if(event.key==='Escape'){event.preventDefault();if(!get('edit-save').disabled)closeEditDialog();}
    if(event.key==='Tab'){
        const fields=[...get('edit-form').querySelectorAll('input,select,button')].filter(el=>!el.disabled);
        const first=fields[0],last=fields[fields.length-1];
        if(event.shiftKey && document.activeElement===first){event.preventDefault();last.focus();}
        else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first.focus();}
    }
});
get('edit-form').addEventListener('submit',async event=>{
    event.preventDefault();get('edit-save').disabled=true;get('edit-cancel').disabled=true;
    try {
        status('edit-status','جارٍ حفظ التعديلات…');
        await json(await fetch(API+'/products/'+encodeURIComponent(editingProductId),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(productFields('edit'))}));
        closeEditDialog();await refreshCatalog();clearSearchAfterEdit();status('add-status','تم حفظ بيانات المنتج.');
    }catch(error){status('edit-status','لم يتم الحفظ: '+error.message,true);}
    finally{get('edit-save').disabled=false;get('edit-cancel').disabled=false;}
});
