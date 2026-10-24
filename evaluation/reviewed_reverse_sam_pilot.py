"""Reverse-view, assistant-point SAM2 pilot on seven reviewed product groups.

Points are sealed before these reverse retrieval results. They are assistant
visual selections, not user-approved masks or new physical product captures.
"""
import argparse
import base64
from datetime import datetime,timezone
from io import BytesIO
import json
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image,ImageOps
import numpy as np
import requests

from backend.catalog_config import ROOT,CATALOG_DIR
from evaluation.reviewed_identity_pilot import prepare,sha,load_cpu_encoder,rank_query,identity_metrics
from evaluation.paired_identity_evaluation import validate_points
from evaluation.compare_safe_crop_catalog import paired_top1_statistics


def validate_point_plan(protocol,plan,protocol_sha):
    if (plan.get('schema_version')!='1.0' or plan.get('protocol_sha256')!=protocol_sha
            or plan.get('selection_author')!='assistant_visual_review'
            or plan.get('selected_before_reverse_results') is not True):
        raise ValueError('Require the matching protocol and explicit pre-result assistant-point declaration.')
    rows=plan.get('queries')
    if not isinstance(rows,list) or len(rows)!=len(protocol['queries']):raise ValueError('Points required for every reverse query.')
    by_number={r.get('number'):r for r in rows}
    if len(by_number)!=len(rows) or set(by_number)!={q['number'] for q in protocol['queries']}:
        raise ValueError('Missing or duplicate reverse query number.')
    for query in protocol['queries']:
        row=by_number[query['number']]
        path=CATALOG_DIR/query['query_image']
        if sha(path)!=query['query_sha256']:raise ValueError('Reverse query bytes changed.')
        validate_points(row.get('points'),row.get('labels'),path)
    return by_number


def write_review_page(report,output):
    from io import BytesIO
    from html import escape
    def photo(path):
        with Image.open(path) as raw:
            image=ImageOps.exif_transpose(raw).convert('RGBA')
            background=Image.new('RGBA',image.size,'white');background.alpha_composite(image)
            image=background.convert('RGB');image.thumbnail((350,400))
            stream=BytesIO();image.save(stream,format='JPEG',quality=90)
        return 'data:image/jpeg;base64,'+base64.b64encode(stream.getvalue()).decode('ascii')
    rows=[];folder=ROOT/'evaluation/cache/identity_pilot/reverse_cutouts'
    for full,selected in zip(report['suites']['full']['queries'],report['suites']['sam2']['queries']):
        figures=[]
        for caption,path in [('استعلام الصورة الكاملة',CATALOG_DIR/full['query_image']),
                             ('قناع SAM2 معروض على الاستعلام',folder/f"{full['number']}_overlay.png"),
                             ('القصاصة التي رُمّزت فعليًا',folder/f"{full['number']}.png"),
                             ('صورة الهدف في المعرض',CATALOG_DIR/full['expected_gallery_images'][0])]:
            if path.is_file():figures.append(f'<figure><img src="{photo(path)}" alt="{escape(caption)}"><figcaption>{escape(caption)}</figcaption></figure>')
        rows.append(f'<article><h2>الحالة {full["number"]}</h2><div class="views">'+''.join(figures)+f'</div><p>ترتيب الهدف: الصورة الكاملة <b>{full["target_rank_at10"] or "خارج10"}</b> · SAM2 <b>{selected["target_rank_at10"] or "خارج10"}</b></p><code>{escape(full["reviewed_group_id"])}</code></article>')
    page='''<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>مقارنة الصورة الكاملة وSAM2 — تمهيدية</title><style>body{font:15px Tahoma,Arial;line-height:1.8;background:#f3f6fb;color:#20334e;margin:0}main{max-width:1300px;margin:auto;padding:24px}header,article{background:white;border:1px solid #d9e3ef;border-radius:14px;padding:22px;margin-bottom:20px}h1{font-size:24px}h2{font-size:18px}.views{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}figure{margin:0}img{width:100%;height:260px;object-fit:contain;background:#fafbfd}figcaption{font-size:11px;color:#60728a;text-align:center}code{font-size:10px;direction:ltr;display:block;overflow-wrap:anywhere}.notice{background:#edf4fc;padding:14px;border-radius:10px}@media(max-width:850px){.views{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:500px){main{padding:12px}.views{grid-template-columns:1fr}}</style><main><header><h1>مقارنة تمهيدية: الصورة الكاملة وSAM2</h1><p class="notice">ظهر الهدف في المركز الأول في 7 من 7 حالات بالطريقتين؛ هذه النتيجة لا تثبت تحسن SAM2 على هذه العينة، ولا تعني دقة عامة 100% للمشروع.</p><p>صور الاتجاه العكسي للمجموعات السبع المراجعة بصريًا. اختار المساعد النقاط بصريًا قبل نتائج الاتجاه العكسي، ولم يعدّلها بعد النتائج. الأقنعة ليست أقنعة وافق عليها المستخدم. الصور موجودة سابقًا في الكتالوج، وحُجبت الاستعلامات السبعة كلها من المعرض؛ بقيت 3,061 صورة وأعيدت مراكز الفئات من المعرض فقط. ليست صور زبائن جديدة أو هوية SKU موثقة.</p></header>__ROWS__</main></html>'''
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(page.replace('__ROWS__',''.join(rows)),encoding='utf-8');return output


def run(protocol_path,points_path,output,url):
    if urlparse(url).hostname not in {'127.0.0.1','localhost','::1'}:raise ValueError('Only the local SAM2 server is supported.')
    protocol_path=Path(protocol_path);points_path=Path(points_path);output=Path(output)
    protocol=json.loads(protocol_path.read_text(encoding='utf-8'));plan=json.loads(points_path.read_text(encoding='utf-8'))
    if protocol.get('scope')!='reviewed_reverse_assistant_point_pilot':raise ValueError('Unexpected reverse protocol.')
    protocol_hash=sha(protocol_path);points_hash=sha(points_path)
    by_number=validate_point_plan(protocol,plan,protocol_hash)
    pack=prepare(query_member_index=1)
    if pack['artifacts']!=protocol['artifacts'] or len(pack['paths'])!=protocol['gallery_count']:
        raise ValueError('Catalog/model artifacts or gallery changed since the point plan.')
    if [q['query_image'] for q in protocol['queries']]!=pack['queries']:
        raise ValueError('Reverse split differs from the sealed protocol.')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.with_suffix('.sealed_points.json').write_bytes(points_path.read_bytes())
    session=requests.Session();session.trust_env=False;url=url.rstrip('/')
    ready=session.get(url+'/api/health',timeout=10);ready.raise_for_status()
    if not ready.json().get('index_ready'):raise ValueError('SAM2 application is not ready.')
    encoder=load_cpu_encoder();records={'full':[],'sam2':[]}
    cutout_dir=ROOT/'evaluation/cache/identity_pilot/reverse_cutouts';cutout_dir.mkdir(parents=True,exist_ok=True)
    def result(query,vector):
        results,prediction,applied=rank_query(vector,pack['vectors'],pack['paths'],pack['categories'],pack['identities'],'auto')
        return {'number':query['number'],'reviewed_group_id':query['reviewed_group_id'],
                'query_image':query['query_image'],'query_sha256':query['query_sha256'],
                'expected_gallery_images':query['expected_gallery_images'],
                'target_rank_at10':next((i for i,r in enumerate(results,1) if r['identity']==query['reviewed_group_id']),None),
                'predicted_category':prediction['category'],'applied_category':applied,'results':results}
    for query in protocol['queries']:
        path=CATALOG_DIR/query['query_image'];raw=path.read_bytes()
        with Image.open(path) as image:
            mime=Image.MIME[image.format];vector=encoder.encode_image(image.copy()).reshape(-1)
        records['full'].append(result(query,vector))
        selection=by_number[query['number']]
        try:
            response=session.post(url+'/api/segment',files={'image':('reverse-query',raw,mime)},
                                  data={'points':json.dumps(selection['points']),'labels':json.dumps(selection['labels'])},timeout=120)
            response.raise_for_status();segment=response.json()
            cutout=base64.b64decode(segment['cutout'],validate=True)
            with Image.open(BytesIO(cutout)) as image:
                image.load();vector=encoder.encode_image(image.copy()).reshape(-1)
            (cutout_dir/f"{query['number']}.png").write_bytes(cutout)
            if segment.get('overlay'):
                (cutout_dir/f"{query['number']}_overlay.png").write_bytes(base64.b64decode(segment['overlay'],validate=True))
            row=result(query,vector);row.update(sam_score=segment.get('score'),sam_bbox=segment.get('bbox'),points=selection['points'],labels=selection['labels'])
        except (requests.RequestException,ValueError,KeyError,OSError) as error:
            row={'number':query['number'],'reviewed_group_id':query['reviewed_group_id'],
                 'query_image':query['query_image'],'query_sha256':query['query_sha256'],
                 'target_rank_at10':None,'selection_failed':True,'error_type':type(error).__name__,
                 'points':selection['points'],'labels':selection['labels']}
        records['sam2'].append(row)
        print(f"Reverse case {query['number']}: full rank={records['full'][-1]['target_rank_at10']}; SAM2 rank={row['target_rank_at10']}",flush=True)
    if sha(protocol_path)!=protocol_hash or sha(points_path)!=points_hash:
        raise RuntimeError('The pre-result protocol or points changed during execution.')
    if any(sha(ROOT/relative)!=expected for relative,expected in protocol['artifacts'].items()):
        raise RuntimeError('An original catalog/model artifact changed during execution.')
    report={'schema_version':'1.0','scope':'reviewed_reverse_view_assistant_point_sam2_pilot',
            'created_at_utc':datetime.now(timezone.utc).isoformat(),'protocol_sha256':protocol_hash,
            'points_sha256':points_hash,'selection_author':'assistant_visual_review',
            'points_selected_before_reverse_results':True,'points_refined_after_results':False,
            'query_count':len(protocol['queries']),'gallery_count':len(pack['paths']),
            'gallery_protocol':'all seven reverse queries and byte/pixel aliases removed globally; centroids recomputed from retained gallery only',
            'query_encoding':'fresh application SigLIP2 CPU, both full and SAM2 cutouts',
            'sam2':'live local application /api/segment with sealed points',
            'routing':'auto for both modes, same gallery',
            'artifacts':protocol['artifacts'],
            'suites':{mode:{'metrics':identity_metrics(rows),'queries':rows} for mode,rows in records.items()},
            'sam2_vs_full_top1':paired_top1_statistics(np.asarray([r['target_rank_at10']==1 for r in records['full']]),np.asarray([r['target_rank_at10']==1 for r in records['sam2']])),
            'sam2_failure_count':sum(r.get('selection_failed',False) for r in records['sam2']),
            'production_index_or_routing_changed':False,
            'limitations':['Seven purposive visual-identity groups; not general accuracy or merchant SKU verification.',
                           'Reverse views reuse the same reviewed product groups as the forward pilot; not an independent test set.',
                           'These are existing catalog captures held out within the pilot, not newly collected consumer photos.',
                           'Points were chosen visually by the assistant before reverse results, not by the user; masks were not human approved.',
                           'No point refinement after results or failed-case dropping; a failure stays in the SAM2 denominator.',
                           'MRR is truncated at rank 10; this does not replace the older category-only experiment.']}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write_review_page(report,ROOT/'evaluation/cache/identity_pilot/reverse_sam_results_review.html')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol',type=Path,default=ROOT/'evaluation/results/reviewed_identity_reverse_protocol.json')
    parser.add_argument('--points',type=Path,default=ROOT/'evaluation/cache/identity_pilot/reverse_points.json')
    parser.add_argument('--output',type=Path,default=ROOT/'evaluation/results/reviewed_reverse_sam_pilot.json')
    parser.add_argument('--url',default='http://127.0.0.1:8001');args=parser.parse_args()
    report=run(args.protocol,args.points,args.output,args.url)
    print(json.dumps({m:s['metrics'] for m,s in report['suites'].items()},indent=2))


if __name__=='__main__':main()
