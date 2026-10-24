const test=require('node:test'), assert=require('node:assert/strict');
const fs=require('node:fs'), path=require('node:path'), vm=require('node:vm');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const response=(status,body)=>({status,ok:status>=200&&status<300,json:async()=>body,blob:async()=>({size:10})});
const preview={token:'preview-token',product_count:2,image_count:3,current_product_count:4,current_image_count:5,created_at:'2026-10-24T12:00:00Z'};
function harness(handler=async url=>response(200,url.endsWith('/backups')?{backups:[]}:preview)){
    const elements=new Map(),calls=[],events=[],downloads=[],revoked=[];
    function make(tag,id=''){
        return {tagName:tag,id,value:'',files:[],disabled:false,children:[],handlers:{},classList:{toggle(){}},
            addEventListener(name,callback){this.handlers[name]=callback;},append(...children){this.children.push(...children);},
            replaceChildren(...children){this.children=children;},showModal(){this.open=true;},close(){this.open=false;},focus(){},
            click(){if(tag==='a')downloads.push({href:this.href,name:this.download});},remove(){}};
    }
    function el(id){if(!elements.has(id))elements.set(id,make('div',id));return elements.get(id);}
    const context=vm.createContext({document:{getElementById:el,createElement:tag=>make(tag),body:make('body')},
        window:{dispatchEvent:event=>events.push(event.type)},Event:class{constructor(type){this.type=type;}},
        URL:{createObjectURL:()=> 'blob:backup',revokeObjectURL:url=>revoked.push(url)},setTimeout:callback=>callback(),
        FormData:class{constructor(){this.values=[];}append(...value){this.values.push(value);}},
        AdminSession:{request:async(url,options)=>{calls.push({url,options});return handler(url,options);}}});
    vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/js/catalog-backup.js'),'utf8'),context);
    async function choose(file={size:1024,name:'catalog.zip'}){el('backup-file').files=[file];return el('backup-file').handlers.change();}
    return {el,calls,events,downloads,revoked,choose};
}
test('choosing an archive shows a preview without restoring; cancel leaves the catalog alone',async()=>{
    const h=harness();await tick();await h.choose();
    assert.equal(h.el('restore-dialog').open,true);assert.match(h.el('restore-summary').textContent,/2 منتج و3 صورة/);
    assert.equal(h.calls.filter(x=>x.url.endsWith('/restore')).length,0);
    h.el('restore-cancel').handlers.click();assert.equal(h.el('restore-dialog').open,false);
    await h.el('restore-confirm').handlers.click();assert.equal(h.calls.filter(x=>x.url.endsWith('/restore')).length,0);
});
test('a late preview cannot replace a newer selected archive',async()=>{
    const pending=[];const h=harness(async url=>url.endsWith('/backups')?response(200,{backups:[]}):new Promise(resolve=>pending.push(resolve)));
    const first=h.choose(),second=h.choose();
    pending[1](response(200,{...preview,token:'new',product_count:8}));await second;
    pending[0](response(200,{...preview,token:'old',product_count:1}));await first;
    assert.match(h.el('restore-summary').textContent,/8 منتج/);
});
test('a failed or stale restore preserves its dialog and does not refresh the product list as success',async()=>{
    const h=harness(async url=>url.endsWith('/backups')?response(200,{backups:[]}):url.endsWith('/restore')?response(409,{code:'catalog_changed'}):response(200,preview));
    await h.choose();await h.el('restore-confirm').handlers.click();
    assert.equal(h.el('restore-dialog').open,true);assert.equal(h.el('restore-confirm').disabled,false);
    assert.match(h.el('restore-status').textContent,/تغير الكتالوج/);assert.deepEqual(h.events,[]);
});
test('successful restore sends the preview token and refreshes catalog and recovery history',async()=>{
    const h=harness();await h.choose();await h.el('restore-confirm').handlers.click();
    const saved=h.calls.find(x=>x.url.endsWith('/restore'));
    assert.equal(saved.options.method,'POST');assert.equal(JSON.parse(saved.options.body).token,preview.token);
    assert.equal(h.el('restore-dialog').open,false);assert.deepEqual(h.events,['catalog-restored']);
    assert.equal(h.calls.filter(x=>x.url.endsWith('/backups')).length,2);
});
test('empty and oversized archives are rejected before upload',async()=>{
    const h=harness();await tick();const before=h.calls.length;
    await h.choose({size:0});assert.match(h.el('backup-status').textContent,/غير سليم/);
    await h.choose({size:201*1024*1024});assert.match(h.el('backup-status').textContent,/200MB/);
    assert.equal(h.calls.length,before);
});
test('export uses the authenticated download and releases the temporary URL',async()=>{
    const h=harness();await h.el('backup-export').handlers.click();
    assert.ok(h.calls.some(x=>x.url==='/api/demo-catalog/products/backup'));
    assert.equal(h.downloads.length,1);assert.equal(h.downloads[0].href,'blob:backup');
    assert.deepEqual(h.revoked,['blob:backup']);assert.equal(h.el('backup-export').disabled,false);
});
test('recovery download links outside the protected recovery endpoint remain disabled',async()=>{
    const h=harness(async()=>response(200,{backups:[{created_at:preview.created_at,product_count:1,image_count:1,download_url:'https://example.invalid/steal'}]}));
    await tick();const row=h.el('backup-history-list').children[0];assert.equal(row.children[1].disabled,true);
    assert.equal(h.calls.length,1);
});
