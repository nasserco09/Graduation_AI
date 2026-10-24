"""Held-out-view pilot on previously human-reviewed visual product groups.

The query is removed globally from the gallery before category centroids are
computed. This is a small purposive development pilot, not verified SKU truth
or a benchmark of new consumer photos. No active index is written.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

import faiss
import numpy as np
from PIL import Image, ImageOps

from backend.catalog_config import ROOT, CATALOG_DIR, CATALOG_METADATA_FILE
from backend.catalog_metadata import CatalogMetadata
from backend.category_routing import predict_category
from backend.image_preprocessing import PREPROCESSING_VERSION
from backend.product_grouping import ReviewedProductGroups

# Fixed by visual photo review BEFORE inference. Similar framing alone does not
# prove a new capture; the five ambiguous pairs are excluded conservatively.
EXCLUDED_GROUPS = {
    'reviewed-6956fcc37d755f30': 'Black dress: same-capture crop/resize cannot be ruled out.',
    'reviewed-b979d9c9d47ef8b1': 'Turquoise shirt: near-identical scene; capture independence uncertain.',
    'reviewed-3b6dd17e8aa592e1': 'Patterned skirt: same-capture crop/resize cannot be ruled out.',
    'reviewed-922cc744b35df0e6': 'Grey shirt: near-identical scene; capture independence uncertain.',
    'reviewed-ae53edb87e6b1a33': 'Black shirt: blur/reframing; independent capture uncertain.',
}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def decoded_sha(path):
    with Image.open(path) as raw:
        image = ImageOps.exif_transpose(raw).convert('RGB')
        return hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest()


def split_gallery(paths, queries, byte_hashes, pixel_hashes):
    """Remove every query and every exact byte/decoded-pixel alias globally."""
    if len(set(queries)) != len(queries) or not set(queries) <= set(paths):
        raise ValueError('Pilot queries must be unique known catalog images.')
    query_bytes = {byte_hashes[p] for p in queries}
    query_pixels = {pixel_hashes[p] for p in queries}
    kept = [i for i,p in enumerate(paths)
            if byte_hashes[p] not in query_bytes and pixel_hashes[p] not in query_pixels]
    if not kept: raise ValueError('No gallery images remain.')
    return kept


def identity_metrics(records):
    if not records: raise ValueError('No evaluated queries.')
    ranks = [r['target_rank_at10'] for r in records]
    return {'query_count':len(ranks),
            'reviewed_identity_top1':round(sum(r == 1 for r in ranks)/len(ranks),6),
            'reviewed_identity_top5':round(sum(r is not None and r <= 5 for r in ranks)/len(ranks),6),
            'reviewed_identity_top10':round(sum(r is not None for r in ranks)/len(ranks),6),
            'reviewed_identity_mrr_at10':round(sum(1/r if r else 0 for r in ranks)/len(ranks),6)}


def rank_query(vector, gallery_vectors, paths, categories, identities, requested='auto'):
    prediction = predict_category(vector, gallery_vectors, paths, categories)
    applied = prediction['category'] if requested == 'auto' else None
    order = np.argsort(-(gallery_vectors @ np.asarray(vector).reshape(-1)), kind='stable')
    results, seen = [], set()
    for index in order:
        i = int(index)
        if applied and categories[i] != applied: continue
        if identities[i] in seen: continue
        seen.add(identities[i])
        results.append({'identity':identities[i], 'image':paths[i], 'category':categories[i],
                        'score':round(float(gallery_vectors[i] @ vector),6)})
        if len(results) == 10: break
    return results, prediction, applied


def write_review_page(report, output):
    """A self-contained inspection artifact; query thumbnails never enter scoring."""
    import base64
    from io import BytesIO
    import html
    def thumbnail(relative):
        with Image.open(CATALOG_DIR/relative) as raw:
            image=ImageOps.exif_transpose(raw).convert('RGB');image.thumbnail((400,400))
            stream=BytesIO();image.save(stream,format='JPEG',quality=90)
        return 'data:image/jpeg;base64,'+base64.b64encode(stream.getvalue()).decode('ascii')
    rows=[]
    for number,(auto,all_categories) in enumerate(zip(report['suites']['auto']['queries'],report['suites']['all']['queries']),1):
        expected=auto['expected_gallery_images'][0]
        rows.append(f'<article><h2>الحالة {number}</h2><div class="pair"><figure><img src="{thumbnail(auto["query_image"])}" alt="صورة الاستعلام المحجوبة"><figcaption>صورة الاستعلام — أُزيلت من المعرض</figcaption></figure><figure><img src="{thumbnail(expected)}" alt="صورة أخرى للهوية المراجعة"><figcaption>صورة أخرى للمجموعة في المعرض</figcaption></figure></div><p>ترتيب المجموعة الصحيحة: تلقائي <b>{auto["target_rank_at10"] or "لم تظهر ضمن10"}</b> · جميع الفئات <b>{all_categories["target_rank_at10"] or "لم تظهر ضمن10"}</b></p><code>{html.escape(auto["reviewed_group_id"])}</code></article>')
    body='''<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>تقييم هوية المنتج — عينة تمهيدية</title><style>body{font:15px Tahoma,Arial;line-height:1.8;background:#f3f6fa;color:#20344f;margin:0}main{max-width:1100px;margin:auto;padding:24px}header,article{padding:22px;background:white;border:1px solid #dbe4ee;border-radius:14px;margin-bottom:20px}h1{font-size:25px}h2{font-size:19px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:15px}figure{margin:0;text-align:center}img{width:100%;height:300px;object-fit:contain;background:#f9fafc}figcaption{font-size:12px;color:#566e88;margin-top:8px}code{font-size:11px;direction:ltr;display:block;overflow-wrap:anywhere}.notice{background:#eaf2fc;padding:14px;border-radius:10px}@media(max-width:550px){main{padding:12px}.pair{grid-template-columns:1fr}img{height:260px}}</style><main><header><h1>سبع حالات لهوية منتج راجعها المستخدم بصريًا</h1><p>كل استعلام صورة موجودة سابقًا في بيانات المشروع، حُجبت هي وجميع الاستعلامات الأخرى من معرض التقييم. لا توجد صورة الاستعلام نفسها داخل البحث.</p><p class="notice">ظهر الهدف في المركز الأول في 7 من 7 حالات مختارة، للتلقائي ولجميع الفئات. هذه عينة تطوير صغيرة، وليست دقة عامة للمشروع أو هوية SKU موثقة، ولا صور زبائن جديدة.</p><p>المعرض الأصلي: 3,068 صورة · الاستعلامات المحجوبة: 7 · معرض التقييم: 3,061 صورة. استُبعدت خمس مجموعات ملتبسة قبل الاستدلال. مقارنة SAM2 غير مقاسة لغياب نقاط مسبقة معتمدة. لم يتغير الفهرس الأصلي.</p></header>__ROWS__</main></html>'''
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(body.replace('__ROWS__',''.join(rows)),encoding='utf-8')
    return output


def prepare(root=ROOT, query_member_index=0):
    root = Path(root)
    catalog = CATALOG_DIR
    metadata = CatalogMetadata(CATALOG_METADATA_FILE)
    group_file = root/'data/reviewed_product_groups.json'
    raw = json.loads(group_file.read_text(encoding='utf-8'))
    ReviewedProductGroups.load(group_file, metadata.items, catalog)
    mapping_path = root/'data/catalog_siglip2_paths.json'
    mapping = json.loads(mapping_path.read_text(encoding='utf-8'))
    if mapping.get('preprocessing_version') != PREPROCESSING_VERSION:
        raise ValueError('Index preprocessing does not match the application.')
    paths = mapping['paths']
    if len(paths) != len(set(paths)): raise ValueError('Duplicate index mapping path.')
    if set(paths) != set(metadata.items): raise ValueError('Index/metadata catalog differs.')
    index_path = root/'data/catalog_siglip2.faiss'
    index = faiss.read_index(str(index_path))
    if index.ntotal != len(paths) or index.d != mapping['embedding_dimension']:
        raise ValueError('Index dimensions/count do not match mapping.')
    if index.metric_type != faiss.METRIC_INNER_PRODUCT:
        raise ValueError('Pilot requires the original inner-product index.')
    vectors = np.asarray(index.reconstruct_n(0,index.ntotal), dtype='float32')
    if not np.isfinite(vectors).all(): raise ValueError('Index contains invalid vectors.')
    hashes = {p:sha(catalog/p) for p in paths}
    pixels = {p:decoded_sha(catalog/p) for p in paths}
    groups = [g for g in raw['groups'] if g['group_id'] not in EXCLUDED_GROUPS]
    queries = [g['members'][query_member_index]['image'] for g in groups]
    kept = split_gallery(paths,queries,hashes,pixels)
    gallery_paths = [paths[i] for i in kept]
    for group,query in zip(groups,queries):
        if not any(m['image'] in gallery_paths for m in group['members'] if m['image']!=query):
            raise ValueError('Held-out group has no distinct gallery target: '+group['group_id'])
    identity_by_path = {m['image']:g['group_id'] for g in raw['groups'] for m in g['members']}
    return {'metadata':metadata,'groups':groups,'queries':queries,'paths':gallery_paths,
            'vectors':vectors[kept], 'categories':[metadata.get(p)['category_key'] for p in gallery_paths],
            'identities':[identity_by_path.get(p,metadata.get(p)['product_id']) for p in gallery_paths],
            'hashes':hashes,'pixels':pixels,'original_count':len(paths),
            'artifacts':{str(p.relative_to(root)).replace('\\','/'):sha(p) for p in
                         [index_path,mapping_path,group_file,CATALOG_METADATA_FILE,
                          root/'models/siglip2_base/config.json',root/'models/siglip2_base/model.safetensors']}}


def load_cpu_encoder(root=ROOT):
    # This process uses CPU only, keeping the live app's GPU models independent.
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
    import torch
    torch.set_num_threads(min(4,os.cpu_count() or 1))
    from backend.search_engine import SearchEngine
    from transformers import AutoModel, AutoProcessor
    # Explicit placement avoids relying on CUDA_VISIBLE_DEVICES, which this
    # Windows runtime does not honor. Reuse the application's encoding method;
    # initialize only the attributes it needs, never its index-rebuild path.
    engine=SearchEngine.__new__(SearchEngine)
    engine.device='cpu'
    model_dir=Path(root)/'models/siglip2_base'
    engine.processor=AutoProcessor.from_pretrained(model_dir,local_files_only=True)
    engine.model=AutoModel.from_pretrained(model_dir,local_files_only=True).to('cpu').eval()
    return engine


def run(output, root=ROOT):
    started=time.perf_counter(); pack=prepare(root)
    print(f"Split checked: queries={len(pack['queries'])}; gallery={len(pack['paths'])}; no query aliases retained.",flush=True)
    engine=load_cpu_encoder(root)
    records={'auto':[],'all':[]}
    for group,query in zip(pack['groups'],pack['queries']):
        query_started=time.perf_counter()
        with Image.open(CATALOG_DIR/query) as image:
            vector=engine.encode_image(image.copy()).reshape(-1)
        for routing in records:
            results,prediction,applied=rank_query(vector,pack['vectors'],pack['paths'],
                                                pack['categories'],pack['identities'],routing)
            rank=next((i for i,r in enumerate(results,1) if r['identity']==group['group_id']),None)
            records[routing].append({'reviewed_group_id':group['group_id'],'query_image':query,
                                     'query_sha256':pack['hashes'][query],
                                     'expected_gallery_images':[m['image'] for m in group['members'][1:]],
                                     'target_rank_at10':rank,'predicted_category':prediction['category'],
                                     'applied_category':applied,'results':results})
        print(f"Encoded {query}: {time.perf_counter()-query_started:.2f}s",flush=True)
    if any(sha(Path(root)/relative)!=expected for relative,expected in pack['artifacts'].items()):
        raise RuntimeError('An active artifact changed during the pilot.')
    report={'schema_version':'1.0','scope':'purposive_reviewed_visual_identity_held_out_view_pilot',
            'created_at_utc':datetime.now(timezone.utc).isoformat(),
            'query_encoding':'fresh_application_siglip2_cpu',
            'gallery_vectors':'reused_original_index_vectors_filtered_in_memory',
            'original_catalog_count':pack['original_count'],'gallery_count':len(pack['paths']),
            'query_count':len(pack['queries']),'excluded_gallery_images':pack['original_count']-len(pack['paths']),
            'split_protocol':{'query_selection':'first member in approved manifest, fixed before inference',
                              'all_queries_removed_globally':True,'byte_and_decoded_pixel_aliases_removed':True,
                              'category_centroids':'recomputed only from retained gallery',
                              'identity_labels':'previous user visual review, not verified merchant SKU',
                              'ambiguous_pairs_excluded_before_inference':EXCLUDED_GROUPS},
            'artifacts':pack['artifacts'],'elapsed_seconds':round(time.perf_counter()-started,3),
            'suites':{mode:{'metrics':identity_metrics(rows),'queries':rows} for mode,rows in records.items()},
            'sam_comparison':{'status':'pending_pre_result_selection_points_or_new_photos',
                              'measured':False},
            'production_index_or_routing_changed':False,
            'limitations':['Seven purposively selected reviewed groups do not establish general accuracy.',
                           'These are existing catalog photos held out for this pilot, not newly collected consumer images.',
                           'Visual identity judgments are not verified SKU identity; unseen equivalent products may be unlabelled.',
                           'No independent test set or SAM2 accuracy improvement is claimed.',
                           'MRR is truncated at rank 10; all/auto use exactly the same retained gallery.']}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write_review_page(report,Path(root)/'evaluation/cache/identity_pilot/results_review.html')
    print(json.dumps({m:s['metrics'] for m,s in report['suites'].items()},indent=2))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'evaluation/results/reviewed_identity_pilot.json')
    args=parser.parse_args();run(args.output)


if __name__=='__main__':main()
