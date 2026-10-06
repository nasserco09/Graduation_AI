"""Prepare manually proposed catalog positives before running retrieval.
No model or API request is made by this tool. Unselected items are unjudged.
"""
import argparse,base64,hashlib,html,json,random
from pathlib import Path
from PIL import Image,ImageOps
from io import BytesIO
from backend.catalog_config import ROOT,CATALOG_DIR


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def photo(path):
    with Image.open(path) as original:
        image=ImageOps.exif_transpose(original).convert("RGB")
        image.thumbnail((500,500));stream=BytesIO();image.save(stream,format="JPEG",quality=90)
    return "data:image/jpeg;base64,"+base64.b64encode(stream.getvalue()).decode()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=['pants','vest'],default='pants')
    args=parser.parse_args()
    is_vest=args.case=='vest'
    category='outwear' if is_vest else 'pants'
    reviewed_count=96 if is_vest else 200
    prefix='coverage_vest' if is_vest else 'coverage'
    output=ROOT/'evaluation/cache/relevance_review';output.mkdir(parents=True,exist_ok=True)
    query=ROOT/('datasets/clothing_small/validation/outwear/0c7412e7-81eb-40b7-be64-ce9782103529.jpg' if is_vest else 'datasets/clothing_small/validation/pants/0257eb81-f3d3-4704-8299-8b6ab20f1ed4.jpg')
    metadata=json.loads((ROOT/'data/catalog_metadata_train.json').read_text(encoding='utf-8'))
    pants=[i for i in metadata['items'] if i['category_key']==category]
    proposed=[4,32,36,56,75] if is_vest else [112,178,170,98,76,131]
    candidates=[];cards=[]
    for number in proposed:
        item=pants[number-1];path=CATALOG_DIR/item['image']
        candidates.append({'product_id':item['product_id'],'image':item['image'],'title':item['title_ar'],'sha256':sha(path)})
        cards.append(f'<article><img src="{photo(path)}" alt="{html.escape(item["title_ar"])}"><h3>{html.escape(item["title_ar"])}</h3><label><input type="checkbox" value="{html.escape(item["product_id"])}"> أعتبره بديلًا مشابهًا مناسبًا</label></article>')
    random.Random(206).shuffle(cards)
    manifest={'schema_version':'1.0','scope':'development_known_positive_probe','query':query.relative_to(ROOT).as_posix(),'query_sha256':sha(query),
              'selection_method':f'assistant_visual_review_first_{reviewed_count}_catalog_{category}_then_human_confirmation',
              ('catalog_outwear_count' if is_vest else 'catalog_pants_count'):len(pants),'proposed_candidates':candidates,
              'retrieval_run_for_this_review':False,'unselected_means':'unjudged_not_negative',
              'limitations':['Purposive development sample, not an unbiased test benchmark.','Proposed candidates are not an exhaustive list of catalog positives.','Human confirmation must precede this review retrieval.']}
    pack=hashlib.sha256(json.dumps(manifest,sort_keys=True,ensure_ascii=False).encode()).hexdigest();manifest['pack_id']=pack
    output.joinpath(prefix+'_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    page="""<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>تأكيد بدائل الكتالوج قبل البحث</title><style>body{font:16px Tahoma,Arial;line-height:1.8;background:#f3f4f8;color:#182039;margin:0;padding:22px}main{max-width:1180px;margin:auto}header,section{background:white;border-radius:16px;padding:22px;margin-bottom:20px}.layout{display:grid;grid-template-columns:280px minmax(0,1fr);gap:20px;align-items:start}.reference{position:sticky;top:16px}.reference img{width:100%;max-height:400px;object-fit:contain}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:16px}article{border:1px solid #d4daea;border-radius:12px;padding:12px}article img{width:100%;height:280px;object-fit:contain}input{width:22px;height:22px;vertical-align:middle}button{padding:12px 20px;background:#5142cc;color:white;border:0;border-radius:8px;font:inherit;cursor:pointer}footer{position:sticky;bottom:0;background:#182039;color:white;border-radius:12px;padding:15px;display:flex;gap:20px;align-items:center;flex-wrap:wrap}@media(max-width:760px){.layout{grid-template-columns:1fr}.reference{position:static}}</style><main><header><h1>نتأكد من وجود شبيه قبل البحث</h1><p>هذه صورة بنطلون كارجو من بيانات المشروع. أمامك ست قطع موجودة فعليًا في الكتالوج، اختر التي تعتبرها بدائل مشابهة مقبولة في اللون والقصة والتفاصيل.</p><p>الاختيارات اقتراحات بالمراجعة البصرية، وليست نتائج بحث. لا توجد درجات نموذج هنا. عدم اختيار قطعة يعني أنها غير معتمدة لهذه التجربة، وليس حكمًا تلقائيًا عليها.</p></header><section class="layout"><div class="reference"><h2>القطعة المطلوبة</h2><img src="__QUERY__" alt="بنطلون كارجو للاستعلام"><p>اختر بديلًا واحدًا على الأقل إن وجدت المناسب. إذا لم تجد أيًا منها مناسبًا، أخبرني لنراجع بدائل أخرى قبل البحث.</p></div><div class="cards">__CARDS__</div></section><footer><span id="count"></span><button id="save">حفظ البدائل المعتمدة JSON</button><span id="notice"></span></footer></main><script>const packId=__PACK__;const items=[...document.querySelectorAll('input[type=checkbox]')];const key='coverage-'+packId;let saved=[];try{saved=JSON.parse(localStorage.getItem(key)||'[]')}catch{}for(const item of items){item.checked=saved.includes(item.value);item.addEventListener('change',update)}function update(){const selected=items.filter(i=>i.checked).map(i=>i.value);document.querySelector('#count').textContent=`بدائل معتمدة: ${selected.length} من ${items.length}`;try{localStorage.setItem(key,JSON.stringify(selected))}catch{}}update();document.querySelector('#save').addEventListener('click',()=>{const positives=items.filter(i=>i.checked).map(i=>i.value);if(!positives.length){document.querySelector('#notice').textContent='لم تعتمد أي بديل؛ لا تبدأ تجربة البحث بعد';return}const payload={schema_version:'1.0',pack_id:packId,scope:'known_positive_confirmation_before_review_retrieval',selected_positive_ids:positives,unselected_means:'unjudged_not_negative'};const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));a.download='coverage_confirmation.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);document.querySelector('#notice').textContent='تم حفظ البدائل؛ نختبر استرجاعها بعد مراجعة الملف'});</script></html>"""
    if is_vest:
        page=page.replace('هذه صورة بنطلون كارجو من بيانات المشروع. أمامك ست قطع', 'هذه صورة سترة مبطنة بلا أكمام من بيانات المشروع. أمامك خمس قطع')
        page=page.replace('بنطلون كارجو للاستعلام', 'سترة مبطنة للاستعلام').replace('coverage_confirmation.json','coverage_vest_confirmation.json')
    page=page.replace('__QUERY__',photo(query)).replace('__CARDS__',''.join(cards)).replace('__PACK__',json.dumps(pack))
    output.joinpath(prefix+'.html').write_text(page,encoding='utf-8')
    print(output.resolve()/(prefix+'.html'))

if __name__=='__main__':main()
