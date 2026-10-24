const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

function harness(overrideFetch) {
    const elements=new Map(),calls=[],revoked=[];
    const defaults={'catalog-availability':'all','catalog-sort':'newest','product-currency':'YER'};
    const document={activeElement:null,createElement:tag=>make(tag),getElementById:element};
    function make(tag,id='') {
        return {id,tagName:tag,value:defaults[id]||'',files:id==='query-image'?[{size:10,type:'image/png'}]:[],hidden:false,disabled:false,checked:true,children:[],dataset:{},handlers:{},attributes:{},classList:{toggle(){}},
            addEventListener(name,handler){this.handlers[name]=handler;},
            append(...children){this.children.push(...children);},appendChild(child){this.children.push(child);return child;},
            replaceChildren(...children){this.children=children;},setAttribute(key,value){this.attributes[key]=value;},getAttribute(key){return this.attributes[key]??(key==='src'?this.src:null);},
            focus(){document.activeElement=this;},reset(){},showModal(){this.open=true;},close(){this.open=false;},querySelectorAll(){return [];}};
    }
    function element(id){if(!elements.has(id))elements.set(id,make('div',id));return elements.get(id);}
    const defaultFetch=async()=>({ok:true,json:async()=>({products:[]})});
    const context=vm.createContext({window:{addEventListener(){}},document,FormData:class{constructor(){this.values=[];}append(...args){this.values.push(args);}},URL:{createObjectURL:()=> 'blob:preview',revokeObjectURL:url=>revoked.push(url)},fetch:(url,options)=>{calls.push({url,options});return (overrideFetch||defaultFetch)(url,options);}});
    context.AdminSession={request:context.fetch};
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/js/demo-catalog.js'),'utf8'),context);
    return {context,element,calls,revoked,run:code=>vm.runInContext(code,context),event:{preventDefault(){}}};
}
const sample={product_id:'p1',name:'فستان',category:'dress',price:'10.00',currency:'YER',available:true,revision:3,images:[{image_id:'i1',url:'/api/demo-catalog/images/i1'},{image_id:'i2',url:'/api/demo-catalog/images/i2'}]};

test('editing a product invalidates an in-flight search without unlocking a newer search',async()=>{
    const pending=[];
    const h=harness(url=>url.endsWith('/products')?Promise.resolve({ok:true,json:async()=>({products:[]})}):new Promise(resolve=>pending.push(resolve)));
    const first=h.element('search-form').handlers.submit(h.event);
    h.run('clearSearchAfterEdit()');
    const second=h.element('search-form').handlers.submit(h.event);
    pending[0]({ok:true,json:async()=>({results:[]})});await first;
    assert.equal(h.element('search-submit').disabled,true);
    assert.equal(h.element('search-status').textContent,'جارٍ البحث في المنتجات المضافة…');
    pending[1]({ok:true,json:async()=>({results:[]})});await second;
    assert.equal(h.element('search-submit').disabled,false);
    assert.match(h.element('search-status').textContent,/لا توجد منتجات متوفرة/);
});

test('Arabic prices normalize without silently accepting ambiguous thousands separators',()=>{
    const h=harness();assert.equal(h.run("normalizePrice('١٢٠٠٠٫٥٠')"),'12000.50');
    h.element('product-name').value='منتج';h.element('product-price').value='١٢٫٥';
    assert.equal(h.run('productFields().price'),'12.5');
    for(const value of ['-1','1e3','12,500','1.234']){h.element('product-price').value=value;assert.throws(()=>h.run('productFields()'));}
});

test('catalog filters name category and availability together without changing source order',()=>{
    const h=harness();const items=[sample,{...sample,product_id:'p2',name:'فستان آخر',category:'',available:false},{...sample,product_id:'p3',name:'جاكيت',category:'outwear'}];
    h.run('products='+JSON.stringify(items));
    assert.equal(h.run("filterProducts(products,'فستان','','all','newest').length"),2);
    assert.equal(h.run("filterProducts(products,'','uncategorized','unavailable','newest')[0].product_id"),'p2');
    assert.equal(h.run("filterProducts(products,'','outwear','available','newest')[0].product_id"),'p3');
    h.run("filterProducts(products,'','','all','name')");assert.equal(h.run('products[0].product_id'),'p1');
});

test('saving photo order sends revision and indexes only newly uploaded images',async()=>{
    const h=harness();await new Promise(resolve=>setImmediate(resolve));
    h.run('openEditor('+JSON.stringify(sample)+')');
    h.run("editorPhotos.unshift({key:'file:1',file:{size:10},url:'blob:new'})");
    await h.element('product-form').handlers.submit(h.event);
    const saved=h.calls.find(call=>call.options?.method==='PUT');
    assert.equal(saved.url,'/api/demo-catalog/products/p1/content');
    const pairs=saved.options.body.values;
    assert.equal(pairs.find(v=>v[0]==='revision')[1],'3');
    assert.equal(pairs.find(v=>v[0]==='image_order')[1],'["new:0","i1","i2"]');
    assert.equal(pairs.filter(v=>v[0]==='images').length,1);
    assert.equal(h.element('product-dialog').open,false);
    assert.deepEqual(h.revoked,['blob:new']);
});

test('delete cancel does not send DELETE and confirm includes the loaded revision',async()=>{
    const h=harness();h.run('openDelete('+JSON.stringify(sample)+')');
    h.element('delete-cancel').handlers.click();
    assert.equal(h.calls.filter(c=>c.options?.method==='DELETE').length,0);
    h.run('openDelete('+JSON.stringify(sample)+')');
    await h.element('delete-confirm').handlers.click();
    assert.equal(h.calls.find(c=>c.options?.method==='DELETE').url,'/api/demo-catalog/products/p1?revision=3');
    assert.equal(h.element('delete-dialog').open,false);
});

test('a failed save preserves the draft and re-enables retry without pretending success',async()=>{
    const h=harness(async(url,options)=>options?.method==='PUT'?{ok:false,status:409,json:async()=>({})}:{ok:true,json:async()=>({products:[]})});
    h.run('openEditor('+JSON.stringify(sample)+')');
    h.element('product-name').value='المسودة';
    await h.element('product-form').handlers.submit(h.event);
    assert.equal(h.element('product-dialog').open,true);
    assert.equal(h.element('product-name').value,'المسودة');
    assert.equal(h.element('product-save').disabled,false);
    assert.match(h.element('product-status').textContent,/نافذة أخرى/);
});

test('removing all photos is rejected before a network mutation',async()=>{
    const h=harness();h.run('openEditor('+JSON.stringify(sample)+'); editorPhotos=[];');
    await h.element('product-form').handlers.submit(h.event);
    assert.equal(h.calls.filter(c=>c.options?.method==='PUT').length,0);
    assert.match(h.element('product-status').textContent,/صورة واحدة على الأقل/);
});

test('a catalog refresh arriving out of order cannot restore stale deleted products',async()=>{
    const pending=[];const h=harness(()=>new Promise(resolve=>pending.push(resolve)));
    const later=h.run('refreshCatalog()');
    pending[1]({ok:true,json:async()=>({products:[]})});await later;
    pending[0]({ok:true,json:async()=>({products:[sample]})});await new Promise(resolve=>setImmediate(resolve));
    assert.equal(h.run('products.length'),0);
});
