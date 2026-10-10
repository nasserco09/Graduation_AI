// State/async regression tests execute the actual frontend source. No browser
// is driven here; these do not replace visual canvas/gesture verification.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function app() {
    const pending = [];
    const context = vm.createContext({
        document: {readyState: 'loading', getElementById: () => null,
                   querySelectorAll: () => [], addEventListener() {}},
        console: {log() {}, error() {}}, URL, Set,
        FormData: class {constructor(){this.entries=[];} append(...entry){this.entries.push(entry);}},
        fetch: (url, options) => new Promise((resolve, reject) => pending.push({resolve, reject, url, options})),
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../frontend/js/app.js'), 'utf8'), context);
    vm.runInContext(`
        showToast = () => {};
        renderAIPoints = () => {};
        DOM.previewImage = {naturalWidth:100, naturalHeight:100,
            getBoundingClientRect:()=>({left:0,top:0,width:100,height:100})};
        DOM.acceptSelectionBtn = {disabled:true};
        DOM.resetSelectionBtn = {disabled:true};
        DOM.searchBtn = {disabled:true, querySelector:()=>null};
        DOM.segmentationMask = {src:'',hidden:true,classList:{remove(){},add(){}}};
        state.selectedFile = {name:'query.jpg'};
        state.searchMode = 'ai';
    `, context);
    return {context, pending, run: source => vm.runInContext(source, context),
            point: () => vm.runInContext('runAISelection({clientX:50,clientY:50,preventDefault(){},stopPropagation(){}})', context)};
}
function success(request) {
    request.resolve({ok:true,json:async()=>({overlay:'MASK',cutout:'CUTOUT',score:0.9})});
}

function keyboardApp() {
    const a = app();
    a.run(`
        for (const key of Object.keys(DOM)) DOM[key] = null;
        DOM.searchBtn = {disabled:false, addEventListener(){}};
        var searchCalls = 0;
        var keyHandler;
        var prevented = false;
        handleSearch = () => {searchCalls++;};
        document.addEventListener = (type, callback) => {if(type === 'keydown') keyHandler = callback;};
        var window = {addEventListener(){}};
        setupEventListeners();
    `);
    return a;
}

test('Enter on an interactive control does not also trigger global search', () => {
    const a = keyboardApp();
    a.run(`keyHandler({key:'Enter',target:{closest:()=>({})},preventDefault(){prevented=true;}})`);
    assert.equal(a.run('searchCalls'), 0);
});

test('Enter on the page starts one search and prevents default activation', () => {
    const a = keyboardApp();
    a.run(`keyHandler({key:'Enter',target:{closest:()=>null},preventDefault(){prevented=true;}})`);
    assert.equal(a.run('searchCalls'), 1);
    assert.equal(a.run('prevented'), true);
});

test('holding Enter does not repeat searches', () => {
    const a = keyboardApp();
    a.run(`keyHandler({key:'Enter',repeat:true,target:{closest:()=>null},preventDefault(){}})`);
    assert.equal(a.run('searchCalls'), 0);
});

test('Enter respects disabled search and an open modal', () => {
    const a = keyboardApp();
    a.run(`DOM.searchBtn.disabled=true;
        keyHandler({key:'Enter',target:{closest:()=>null},preventDefault(){}});
        DOM.searchBtn.disabled=false;DOM.aboutModal={hidden:false};
        keyHandler({key:'Enter',target:{closest:()=>null},preventDefault(){}});`);
    assert.equal(a.run('searchCalls'), 0);
});

test('switching from accepted SAM2 to manual mode changes the preview badge', () => {
    const a = app();
    a.run(`var badgeText={textContent:'تم اعتماد القطعة'};
        DOM.previewBadge={classList:{toggle(){}},querySelector:()=>badgeText};
        state.aiAccepted=true;setSearchMode('rect');`);
    assert.equal(a.run('badgeText.textContent'), 'التحديد اليدوي');
});

test('failed refinement preserves the previous accepted selection', async () => {
    const a = app();
    a.run(`state.aiPoints=[{x:20,y:20,label:1}];state.aiMaskDataUrl='old-mask';
           state.aiCutoutDataUrl='old-cutout';state.aiAccepted=true;DOM.acceptSelectionBtn.disabled=false;`);
    const request = a.point();
    a.pending[0].reject(new Error('network failure'));
    await request;
    assert.equal(a.run('state.aiPoints.length'), 1);
    assert.equal(a.run('state.aiCutoutDataUrl'), 'old-cutout');
    assert.equal(a.run('state.aiAccepted'), true);
    assert.equal(a.run('DOM.acceptSelectionBtn.disabled'), false);
    assert.equal(a.run('DOM.searchBtn.disabled'), false);
});

test('reset ignores a late successful segmentation response', async () => {
    const a = app();
    const request = a.point();
    a.run('resetAISelection()');
    success(a.pending[0]);
    await request;
    assert.equal(a.run('state.aiMaskDataUrl'), null);
    assert.equal(a.run('state.aiCutoutDataUrl'), null);
    assert.equal(a.run('DOM.segmentationMask.hidden'), true);
    assert.equal(a.run('DOM.acceptSelectionBtn.disabled'), true);
});

test('old request failure cannot remove a new point or clear its busy state', async () => {
    const a = app();
    const oldRequest = a.point();
    a.run('resetAISelection()');
    const newRequest = a.point();
    a.pending[0].reject(new Error('old failure'));
    await oldRequest;
    assert.equal(a.run('state.aiPoints.length'), 1);
    assert.equal(a.run('state.aiBusy'), true);
    success(a.pending[1]);
    await newRequest;
    assert.equal(a.run('state.aiCutoutDataUrl'), 'data:image/png;base64,CUTOUT');
    assert.equal(a.run('state.aiBusy'), false);
});

test('successful segmentation enables acceptance, but search waits for acceptance', async () => {
    const a = app();
    const request = a.point();
    success(a.pending[0]);
    await request;
    assert.equal(a.run('DOM.acceptSelectionBtn.disabled'), false);
    assert.equal(a.run('DOM.searchBtn.disabled'), true);
    a.run('acceptAISelection()');
    assert.equal(a.run('DOM.searchBtn.disabled'), false);
});

test('failed first segmentation leaves search and acceptance disabled', async () => {
    const a = app();
    const request = a.point();
    a.pending[0].resolve({ok:true,json:async()=>({overlay:'MASK'})});
    await request;
    assert.equal(a.run('state.aiPoints.length'), 0);
    assert.equal(a.run('state.aiCutoutDataUrl'), null);
    assert.equal(a.run('state.aiBusy'), false);
    assert.equal(a.run('DOM.acceptSelectionBtn.disabled'), true);
    assert.equal(a.run('DOM.searchBtn.disabled'), true);
});

test('failed refinement retains an unaccepted selection for later acceptance', async () => {
    const a = app();
    a.run(`state.aiPoints=[{x:20,y:20,label:1}];state.aiMaskDataUrl='old-mask';
           state.aiCutoutDataUrl='old-cutout';state.aiAccepted=false;`);
    const request = a.point();
    a.pending[0].reject(new Error('network failure'));
    await request;
    assert.equal(a.run('state.aiAccepted'), false);
    assert.equal(a.run('DOM.acceptSelectionBtn.disabled'), false);
    assert.equal(a.run('DOM.searchBtn.disabled'), true);
    a.run('acceptAISelection()');
    assert.equal(a.run('DOM.searchBtn.disabled'), false);
});


test('configured grouping is requested and group images survive response normalization', async () => {
    const a = app();
    a.run("DOM.groupProducts = {disabled:false, checked:true};");
    const promise = a.run("searchImage({},8)");
    assert.equal(a.pending[0].url, '/api/search?top_k=8&group_products=true');
    a.pending[0].resolve({ok:true,json:async()=>({results:[{product_id:'a',url:'/catalog/a.jpg',score:.9,group_images:[{url:'/catalog/a.jpg'},{url:'/catalog/b.jpg'}]}]})});
    const data = await promise;
    assert.equal(data.results[0].group_images.length,2);
});

test('unchecked or unavailable grouping keeps the original search request', async () => {
    for (const values of [{disabled:false,checked:false},{disabled:true,checked:true}]) {
        const a = app();
        a.run(`DOM.groupProducts = ${JSON.stringify(values)};`);
        const promise = a.run('searchImage({},8)');
        assert.equal(a.pending[0].url,'/api/search?top_k=8');
        a.pending[0].resolve({ok:true,json:async()=>({results:[]})});
        await promise;
    }
});

test('grouping control is offered only when server reports reviewed groups', async () => {
    for (const count of [0,12]) {
        const a = app();
        a.run('DOM.groupProducts={disabled:true,checked:false}; DOM.groupingOption={hidden:true};');
        const promise = a.run('loadGroupingCapability()');
        a.pending[0].resolve({ok:true,json:async()=>({reviewed_product_groups:count})});
        await promise;
        assert.equal(a.run('DOM.groupProducts.checked'),count>0);
        assert.equal(a.run('DOM.groupingOption.hidden'),count===0);
    }
});


test('added products use their own endpoint with all-category mapping and no reviewed grouping', async () => {
    const a = app();
    a.run(`DOM.searchSource={value:'products'}; DOM.groupProducts={disabled:false,checked:true};`);
    const response = a.run("searchImage({},8,'sam2-cutout.png','ai','auto')");
    assert.equal(a.pending[0].url, '/api/demo-catalog/search?top_k=8');
    assert.equal(a.pending[0].options.body.entries.find(entry=>entry[0]==='category')[1], '');
    assert.equal(a.pending[0].options.body.entries.find(entry=>entry[0]==='image')[2], 'sam2-cutout.png');
    a.pending[0].resolve({ok:true,json:async()=>({scope:'isolated_local_demo_catalog',results:[{name:'My vest',product_id:'p1',image_url:'/api/demo-catalog/images/a',score:.9,images:[{image_id:'a',url:'/a'},{image_id:'b',url:'/b'}]}]})});
    const data=await response;
    assert.equal(data.results[0].title,'My vest');
    assert.equal(data.results[0].catalog_source,'products');
    assert.equal(data.results[0].group_images[1].product_id,'p1');
});

test('switching source invalidates old results, keeps the accepted selection and restores original category', () => {
    const a=app();
    a.run(`DOM.searchSource={value:'products'};
        DOM.categoryModeSelect={value:'dress',querySelector:()=>null};
        DOM.groupProducts={disabled:false,checked:true};DOM.groupingOption={hidden:false};
        DOM.resultsSection={hidden:false};DOM.feedbackPanel={hidden:false};
        state.groupingAvailable=true;state.currentSearchId='old';state.aiAccepted=true;state.aiCutoutDataUrl='CUTOUT';
        handleSearchSourceChange();`);
    assert.equal(a.run('DOM.resultsSection.hidden'),true);
    assert.equal(a.run('state.currentSearchId'),null);
    assert.equal(a.run('DOM.categoryModeSelect.value'),'all');
    assert.equal(a.run('DOM.groupProducts.disabled'),true);
    assert.equal(a.run('state.aiCutoutDataUrl'),'CUTOUT');
    assert.equal(a.run('state.aiAccepted'),true);
    a.run(`DOM.searchSource.value='original';handleSearchSourceChange();`);
    assert.equal(a.run('DOM.categoryModeSelect.value'),'dress');
    assert.equal(a.run('DOM.groupProducts.disabled'),false);
});

test('late search from a previous source cannot render or hide a newer search overlay', async () => {
    const a=app();
    a.run(`DOM.searchSource={value:'original'};state.searchMode='full';
        DOM.loadingOverlay={hidden:true};var rendered=0;
        updateProgress=()=>{};showQueryPreview=async()=>{};renderResults=()=>{rendered++};
        var pendingSearch=[];searchImage=()=>new Promise(resolve=>pendingSearch.push(resolve));`);
    const first=a.run('handleSearch()');await Promise.resolve();await Promise.resolve();
    a.run(`DOM.searchSource.value='products';handleSearchSourceChange();`);
    const second=a.run('handleSearch()');await Promise.resolve();await Promise.resolve();
    a.run(`pendingSearch[0]({results:[]});`);await first;
    assert.equal(a.run('rendered'),0);
    assert.equal(a.run('DOM.loadingOverlay.hidden'),false);
    // Supersede the second request too; it must settle without rendering.
    a.run(`state.sourceGeneration++;pendingSearch[1]({results:[]});`);await second;
    assert.equal(a.run('rendered'),0);
});
