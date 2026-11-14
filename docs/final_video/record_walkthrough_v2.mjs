// Record only the real application. Run against an isolated demo instance.
// Usage: node record_walkthrough_v2.mjs --url http://127.0.0.1:8020 --out PATH
// Set LIBAAS_VIDEO_DEMO_PASSWORD for the isolated videoadmin account, never a real account.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const require=createRequire(import.meta.url);
const packagePath=process.env.LIBAAS_PLAYWRIGHT || 'C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1112-737-0_26.1112.737.0_x64__3k8sg7r9htsxt/dependencies/node/node_modules/playwright';
const {chromium}=require(packagePath);
const args=process.argv.slice(2);
const option=(flag,fallback)=>args.includes(flag)?args[args.indexOf(flag)+1]:fallback;
const folder=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(folder,'../..');
const out=path.resolve(option('--out',path.join(root,'evaluation/cache/video_quick_20261114/capture')));
const base=option('--url','http://127.0.0.1:8020');
const password=process.env.LIBAAS_VIDEO_DEMO_PASSWORD;
if(!password)throw new Error('Provide the isolated demo account password in LIBAAS_VIDEO_DEMO_PASSWORD');
await fs.mkdir(out,{recursive:true});
const logo='data:image/png;base64,'+(await fs.readFile(path.join(folder,'assets/university_logo.png'))).toString('base64');
const browser=await chromium.launch({headless:true,executablePath:process.env.LIBAAS_CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe'});
const context=await browser.newContext({viewport:{width:1440,height:900},recordVideo:{dir:out,size:{width:1440,height:900}},reducedMotion:'reduce'});
const auth=await context.request.post(base+'/api/auth/login',{data:{username:'videoadmin',password},headers:{Origin:base}});
if(!auth.ok())throw new Error('Isolated demo login failed: '+auth.status());
await context.addInitScript(({logo})=>{
 const install=()=>{
  if(document.querySelector('#video-guide'))return;
  const host=document.createElement('div');host.id='video-guide';
  host.style.cssText='position:fixed;inset:0;z-index:2147483647;pointer-events:none';
  const shadow=host.attachShadow({mode:'open'});
  shadow.innerHTML=`<style>*{box-sizing:border-box}.header{position:absolute;top:0;left:0;right:0;height:65px;background:#fff;display:flex;align-items:center;gap:16px;padding:5px 30px;border-bottom:2px solid #e4ebf3;color:#123a61;font:700 21px Arial;direction:ltr}.header img{height:55px;width:auto}.header small{font-weight:400;font-size:16px;margin-left:auto}.caption{position:absolute;bottom:0;left:0;right:0;height:76px;background:#10385e;display:flex;align-items:center;justify-content:center;text-align:center;padding:10px 35px;color:white;font:600 24px/1.35 Arial;direction:ltr}.cursor{position:absolute;width:18px;height:18px;border:2px solid white;border-radius:50%;background:#1688db;box-shadow:0 0 0 2px #123a6170;transform:translate(-50%,-50%);display:none}.click{animation:click .5s ease-out}@keyframes click{0%{box-shadow:0 0 0 0 #1688db90}100%{box-shadow:0 0 0 24px #1688db00}}</style><div class="header"><img alt="University logo"><span>LibaasLens</span><small>Application walkthrough · No audio</small></div><div class="caption">Search for fashion using a photo</div><div class="cursor"></div>`;
  shadow.querySelector('img').src=logo;
  document.documentElement.append(host);
  window.videoCaption=text=>{shadow.querySelector('.caption').textContent=text;};
  const cursor=shadow.querySelector('.cursor');
  document.addEventListener('mousemove',e=>{cursor.style.display='block';cursor.style.left=e.clientX+'px';cursor.style.top=e.clientY+'px';},true);
  document.addEventListener('mousedown',()=>{cursor.classList.remove('click');void cursor.offsetWidth;cursor.classList.add('click');},true);
 };
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',install);else install();
},{logo});
const page=await context.newPage();
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const events=[];const start=Date.now();
const pause=ms=>page.waitForTimeout(ms);
const caption=async(text)=>{events.push({seconds:(Date.now()-start)/1000,text});console.log(text);await page.evaluate(text=>window.videoCaption(text),text);};
const scroll=async(selector,top=110)=>{await page.locator(selector).evaluate((el,top)=>window.scrollTo({top:el.getBoundingClientRect().top+window.scrollY-top,behavior:'instant'}),top);await pause(250);};
const click=async(selector)=>{const box=await page.locator(selector).boundingBox();if(box){await page.mouse.move(box.x+box.width/2,box.y+box.height/2,{steps:15});await pause(280);}await page.locator(selector).click();};
const result=async()=>{await page.waitForFunction(()=>!document.querySelector('#search-btn').disabled,null,{timeout:120000});await page.locator('#results-grid .result-card').first().waitFor({timeout:120000});await scroll('#results-title');};
try {
 await page.goto(base,{waitUntil:'networkidle'});
 await pause(700);
 await caption('1. Upload a clothing photo');
 await scroll('#drop-zone',150);await pause(1000);
 const chooserPromise=page.waitForEvent('filechooser');await click('#browse-files-btn');
 await (await chooserPromise).setFiles(path.join(root,'docs/final_presentation/assets/composite_query.jpg'));
 await page.locator('#preview-image').waitFor();await scroll('#preview-image',110);await pause(1800);
 await caption('2. Choose Full image, then click Search');
 await click('#mode-full-btn');await scroll('#search-btn',650);await pause(900);await click('#search-btn');
 await result();await caption('Browse the visually similar products');await pause(3000);
 await caption('3. Choose SAM2 to focus on one garment');
 await scroll('#mode-ai-btn',650);await click('#mode-ai-btn');await scroll('#preview-image',110);await pause(1600);
 await caption('Click the garment. Add more points if needed.');
 const box=await page.locator('#preview-image').boundingBox();
 await page.mouse.move(box.x+box.width*.75,box.y+box.height*.5,{steps:25});await pause(650);await page.mouse.click(box.x+box.width*.75,box.y+box.height*.5);
 await page.waitForFunction(()=>!document.querySelector('#accept-selection-btn').disabled,null,{timeout:120000});await pause(1500);
 await caption('4. Review the cutout, then accept the selection');
 await scroll('#selection-result',400);await page.screenshot({path:path.join(out,'cutout.png')});await pause(1900);await click('#accept-selection-btn');await pause(700);
 await caption('5. Search using the selected garment');
 await scroll('#search-btn',650);await pause(700);await click('#search-btn');await result();await pause(3000);
 await page.screenshot({path:path.join(out,'selected_results.png')});
 await page.goto(base+'/demo-catalog.html',{waitUntil:'networkidle'});
 await caption('6. The administrator can add and edit products');await pause(1600);await click('#add-product');await pause(500);
 await page.locator('#product-name').pressSequentially('Floral dress - demo',{delay:35});
 await page.locator('#product-category').selectOption('dress');await page.locator('#product-price').fill('12000');
 await page.locator('#product-images').setInputFiles(path.join(root,'docs/final_presentation/assets/selected_garment.png'));
 await caption('Enter product details and photos, then save');await pause(2000);await click('#product-save');
 await page.locator('#product-dialog').waitFor({state:'hidden',timeout:120000});await scroll('#catalog-title');await pause(2200);
 const first=page.locator('#catalog-products .card').first();
 // The first card is the newest product added in this isolated recording.
 const edit=page.locator('#catalog-products button').filter({hasText:'تعديل'}).first();
 await edit.click();await caption('Edit the price or availability, then save changes');
 await page.locator('#product-price').fill('12500');await pause(1900);await click('#product-save');
 await page.locator('#product-dialog').waitFor({state:'hidden',timeout:120000});await pause(900);
 await page.goto(base,{waitUntil:'networkidle'});
 await caption('7. Choose Added products to search your own catalogue');
 await page.locator('#file-input').setInputFiles(path.join(root,'docs/final_presentation/assets/selected_garment.png'));
 await page.locator('#search-source').selectOption('products');await scroll('#search-source',420);await pause(2200);await click('#search-btn');await result();await pause(2300);
 await caption('Upload a photo, select your item, and explore similar products.');await pause(2200);
 await page.screenshot({path:path.join(out,'added_results.png')});
 const video=page.video();await context.close();await browser.close();
 const record={source:await video.path(),width:1440,height:900,events,page_errors:errors,scope:'Real isolated application. University logo and English guidance overlay only. No slides or audio. Editing pace is not a latency benchmark.'};
 await fs.writeFile(path.join(out,'capture.json'),JSON.stringify(record,null,2)+'\n');
 console.log(JSON.stringify(record,null,2));
 if(errors.length)process.exitCode=1;
} catch(e) {await page.screenshot({path:path.join(out,'capture_error.png')}).catch(()=>{});await context.close();await browser.close();throw e;}
