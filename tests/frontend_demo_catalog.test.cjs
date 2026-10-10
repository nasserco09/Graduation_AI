const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

test('editing a product invalidates an in-flight search without unlocking a newer search',async()=>{
    const elements=new Map();
    function element(id){if(!elements.has(id))elements.set(id,{value:'',files:[{size:10}],hidden:false,disabled:false,handlers:{},classList:{toggle(){}},addEventListener(name,handler){this.handlers[name]=handler;},replaceChildren(){}});return elements.get(id);}
    const pending=[];
    const context=vm.createContext({document:{getElementById:element,addEventListener(){}},FormData:class{append(){}},URL,fetch:url=>url.endsWith('/products')?Promise.resolve({ok:true,json:async()=>({products:[]})}):new Promise(resolve=>pending.push(resolve))});
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/js/demo-catalog.js'),'utf8'),context);
    const event={preventDefault(){}};
    const first=element('search-form').handlers.submit(event);
    vm.runInContext('clearSearchAfterEdit()',context);
    const second=element('search-form').handlers.submit(event);
    pending[0]({ok:true,json:async()=>({results:[]})});await first;
    assert.equal(element('search-submit').disabled,true);
    assert.equal(element('search-status').textContent,'جارٍ البحث في المنتجات المضافة…');
    pending[1]({ok:true,json:async()=>({results:[]})});await second;
    assert.equal(element('search-submit').disabled,false);
    assert.match(element('search-status').textContent,/لا توجد منتجات متوفرة/);
});
