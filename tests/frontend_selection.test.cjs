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
        FormData: class {append() {}},
        fetch: () => new Promise((resolve, reject) => pending.push({resolve, reject})),
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
