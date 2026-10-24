"""Prepare a local target/point collection page before any retrieval results.

No model runs here. Choose an existing catalog target and points on a NEW photo,
save the case JSON from the page, then register that file into the evaluation.
"""
import argparse
import base64
from io import BytesIO
import html
import json
from pathlib import Path

from PIL import Image, ImageOps
from backend.catalog_config import ROOT, CATALOG_DIR, CATALOG_METADATA_FILE
from backend.catalog_metadata import CatalogMetadata
from backend.category_routing import CATEGORY_LABELS
from backend.request_validation import validate_image_bytes
from evaluation.exact_product_evaluation import file_sha256

DEFAULT_COLLECTION=ROOT/'evaluation/cache/identity_collection'


def preview(path, size=None):
    with Image.open(path) as raw:
        image=ImageOps.exif_transpose(raw).convert('RGB')
        if size:image.thumbnail(size)
        stream=BytesIO();image.save(stream,format='JPEG',quality=92)
        return 'data:image/jpeg;base64,'+base64.b64encode(stream.getvalue()).decode('ascii')


def prepare(image, category, page, output):
    image=Path(image).expanduser().resolve()
    if not image.is_file():raise FileNotFoundError(image)
    if image.is_relative_to(CATALOG_DIR.resolve()):
        raise ValueError('Use a newly captured query photo outside the indexed catalog.')
    validate_image_bytes(image.read_bytes())
    metadata=CatalogMetadata(CATALOG_METADATA_FILE)
    items=[m for m in metadata.items.values() if not category or m['category_key']==category]
    items.sort(key=lambda m:m['image'])
    page_count=(len(items)+59)//60
    if not 1<=page<=page_count:raise ValueError(f'Page must be 1..{page_count}.')
    selected=items[(page-1)*60:page*60]
    cards=[]
    for item in selected:
        cards.append('<label class="card"><input type="radio" name="target" value="'+html.escape(item['product_id'])+'" data-category="'+html.escape(item['category_key'])+'"><img alt="'+html.escape(item['title_ar'])+'" src="'+preview(CATALOG_DIR/item['image'],(200,240))+'"><strong>'+html.escape(item['title_ar'])+'</strong><code>'+html.escape(item['product_id'])+'</code></label>')
    path_value=image.relative_to(ROOT).as_posix() if image.is_relative_to(ROOT) else str(image)
    with Image.open(image) as raw: width,height=ImageOps.exif_transpose(raw).size
    config={'image':path_value,'sha256':file_sha256(image),'width':width,'height':height,
            'catalog_metadata_sha256':file_sha256(CATALOG_METADATA_FILE)}
    page_html='''<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>جمع استعلام تقييم قبل البحث</title>
<style>body{font:15px Tahoma,Arial;line-height:1.8;margin:0;background:#f4f7fb;color:#1d304b}main{max-width:1280px;margin:auto;padding:24px}header,section{background:white;border:1px solid #dce5ee;border-radius:14px;padding:20px;margin-bottom:20px}h1{font-size:25px}h2{font-size:19px}.query{display:grid;grid-template-columns:minmax(240px,440px) 1fr;gap:24px}canvas{width:100%;height:auto;display:block;cursor:crosshair;border:1px solid #ccd5e0}.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px}.card{display:flex;flex-direction:column;border:1px solid #d7e0ec;padding:10px;border-radius:10px;cursor:pointer}.card:has(input:checked){outline:3px solid #2465aa}.card img{width:100%;height:220px;object-fit:contain}code{font-size:10px;overflow-wrap:anywhere;direction:ltr}button{font:inherit;padding:9px 16px;background:#245f9f;color:white;border:0;border-radius:8px;cursor:pointer;margin:4px}button[aria-pressed=true]{outline:3px solid #a9cbef}label.confirm{display:block;margin:15px 0}#notice{font-weight:bold;color:#235a91}footer{position:sticky;bottom:0;background:#edf4fc;padding:14px;border:1px solid #c2d5ec;border-radius:12px}@media(max-width:700px){.query{grid-template-columns:1fr}}</style>
<main><header><h1>نسجّل المنتج الصحيح والنقاط قبل رؤية النتائج</h1><p>الصورة الجديدة يجب أن تكون لقطة أخرى للمنتج نفسه؛ لا نسخة مصغرة أو قصاصة أو إعادة ضغط لصورة الكتالوج. هذه الصفحة لا تشغّل بحثًا ولا تعرض درجات.</p><p>صفحة الكتالوج __PAGE__ من __PAGES__؛ لتغيير المجموعة أعد أمر التحضير مع --page أو --category. لا تعتمد منتجًا لمجرد أنه شبيه.</p></header>
<section class="query"><div><h2>صورة الاستعلام الجديدة</h2><canvas id="query"></canvas></div><div><h2>تحديد القطعة للمقارنة مع SAM2</h2><p>ضع نقاطًا داخل أجزاء القطعة المطلوبة، ونقاط استبعاد على الخلفية أو القطع الأخرى عند الحاجة. يمكن وضع عدة نقاط. الأرقام تحفظ بإحداثيات الصورة الأصلية.</p><button id="positive" aria-pressed="true">نقطة داخل القطعة ＋</button><button id="negative" aria-pressed="false">نقطة استبعاد −</button><button id="reset">مسح النقاط</button><p id="point-count">النقاط: 0</p><p>سنقارن الصورة الكاملة وقناع SAM2 الناتج من هذه النقاط نفسها. لا توجد معاينة قناع في هذه الصفحة؛ تُسجّل أعطال التحديد ضمن نتائج التقييم ولا تُحذف من الحساب.</p></div></section>
<section><h2>اختر نفس المنتج الموجود فعلًا في الكتالوج</h2><div class="cards">__CARDS__</div></section>
<footer><label class="confirm"><input id="new-capture" type="checkbox"> أؤكد أن صورة الاستعلام لقطة مختلفة فعلًا، وليست تعديلًا لصورة الكتالوج.</label><label class="confirm"><input id="same-product" type="checkbox"> أؤكد أن المنتج المختار هو المنتج نفسه، وسجلت الاختيار والنقاط قبل نتائج البحث.</label><button id="save">حفظ حالة التقييم</button><span id="notice" role="status"></span></footer></main>
<script>const config=__CONFIG__;const photo=new Image();const canvas=document.querySelector('#query'),ctx=canvas.getContext('2d');let points=[],labels=[],label=1;photo.onload=()=>{canvas.width=config.width;canvas.height=config.height;draw()};photo.src=__QUERY__;
function draw(){ctx.drawImage(photo,0,0,canvas.width,canvas.height);for(let i=0;i<points.length;i++){const [x,y]=points[i];ctx.beginPath();ctx.arc(x,y,Math.max(canvas.width/70,5),0,Math.PI*2);ctx.fillStyle=labels[i]?'#13a166':'#dc3545';ctx.fill();ctx.strokeStyle='white';ctx.lineWidth=Math.max(canvas.width/200,2);ctx.stroke()}document.querySelector('#point-count').textContent='النقاط: '+points.length}
canvas.addEventListener('click',event=>{if(points.length>=50){document.querySelector('#notice').textContent='الحد الأقصى 50 نقطة.';return}const r=canvas.getBoundingClientRect();points.push([Math.min(canvas.width-1,Math.max(0,Math.round((event.clientX-r.left)*canvas.width/r.width))),Math.min(canvas.height-1,Math.max(0,Math.round((event.clientY-r.top)*canvas.height/r.height)))]);labels.push(label);draw()});
for(const [id,value] of [['positive',1],['negative',0]])document.querySelector('#'+id).onclick=()=>{label=value;document.querySelector('#positive').setAttribute('aria-pressed',String(value===1));document.querySelector('#negative').setAttribute('aria-pressed',String(value===0))};document.querySelector('#reset').onclick=()=>{points=[];labels=[];draw()};
document.querySelector('#save').onclick=()=>{const notice=document.querySelector('#notice'),target=document.querySelector('input[name=target]:checked');if(!target||!labels.includes(1)||!document.querySelector('#new-capture').checked||!document.querySelector('#same-product').checked){notice.textContent='اختر المنتج نفسه، وضع نقطة داخل القطعة، وأكّد الشرطين أولًا.';return}const payload={schema_version:'1.0',scope:'fresh_identity_pre_result_case',created_at_utc:new Date().toISOString(),catalog_metadata_sha256:config.catalog_metadata_sha256,query:{image:config.image,sha256:config.sha256,product_id:target.value,category:target.dataset.category,search_category:'auto',confirmed_new_capture:true,target_confirmed_before_search:true,selection:{points,labels,confirmed_before_search:true}}};const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));a.download='identity_case_'+config.sha256.slice(0,12)+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);notice.textContent='حُفظت الحالة؛ سجّل الملف بالأداة ثم شغّل المقارنة.'};</script></html>'''
    page_html=page_html.replace('__PAGE__',str(page)).replace('__PAGES__',str(page_count)).replace('__CARDS__',''.join(cards)).replace('__CONFIG__',json.dumps(config,ensure_ascii=True).replace('<','\\u003c')).replace('__QUERY__',json.dumps(preview(image)))
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(page_html,encoding='utf-8')
    return output


def register(case_path,manifest_path):
    case=json.loads(Path(case_path).read_text(encoding='utf-8'))
    if case.get('schema_version')!='1.0' or case.get('scope')!='fresh_identity_pre_result_case':raise ValueError('Unsupported collection case.')
    if case.get('catalog_metadata_sha256')!=file_sha256(CATALOG_METADATA_FILE):raise ValueError('Catalog metadata changed since collection.')
    query=case['query'];image=(ROOT/query['image']).resolve()
    if file_sha256(image)!=query.get('sha256'):raise ValueError('Query photo changed since collection.')
    from evaluation.paired_identity_evaluation import validate_selection,validate_collection
    validate_selection(query,image)
    manifest_path=Path(manifest_path)
    manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.is_file() else {'schema_version':'1.0','scope':'fresh_identity_paired_evaluation','queries':[]}
    if manifest.get('scope')!='fresh_identity_paired_evaluation':raise ValueError('Use a separate paired collection manifest.')
    queries=manifest['queries']+[dict(query,collected_at_utc=case.get('created_at_utc'))]
    # Validate every collected case, including decoded-pixel leakage, before persisting.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        candidate=Path(tmp)/'manifest.json';candidate.write_text(json.dumps({'schema_version':'1.0','scope':'fresh_identity_paired_evaluation','queries':queries}),encoding='utf-8')
        validate_collection(candidate)
    manifest['queries']=queries
    manifest_path.parent.mkdir(parents=True,exist_ok=True)
    temporary=manifest_path.with_suffix('.tmp');temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temporary.replace(manifest_path)
    return len(queries)


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    page=commands.add_parser('prepare');page.add_argument('--image',required=True,type=Path);page.add_argument('--category',choices=CATEGORY_LABELS);page.add_argument('--page',type=int,default=1);page.add_argument('--output',type=Path,default=DEFAULT_COLLECTION/'collect.html')
    add=commands.add_parser('register');add.add_argument('case',type=Path);add.add_argument('--manifest',type=Path,default=DEFAULT_COLLECTION/'manifest.json')
    args=parser.parse_args()
    if args.command=='prepare':print(prepare(args.image,args.category,args.page,args.output))
    else:print(f"Registered queries: {register(args.case,args.manifest)}; no model inference was run.")


if __name__=='__main__':main()
