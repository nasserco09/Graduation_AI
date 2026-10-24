"""Compare full/new-photo queries and pre-recorded SAM2 points through local API.

Collect labels/points first with tools.collect_identity_queries. All cases must
pass preflight before the first model call. Failed SAM2 cases remain failures
in the denominator; no optimistic dropping or point selection from results.
"""
import argparse
import base64
from datetime import datetime, timezone
from io import BytesIO
import json
import math
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageOps
import requests

from backend.catalog_config import ROOT,CATALOG_DIR,CATALOG_METADATA_FILE
from backend.catalog_metadata import CatalogMetadata
from backend.product_grouping import ReviewedProductGroups
from backend.request_validation import validate_image_bytes
from evaluation.exact_product_evaluation import load_manifest,file_sha256
from evaluation.reviewed_identity_pilot import decoded_sha,identity_metrics
from evaluation.compare_safe_crop_catalog import paired_top1_statistics
import numpy as np


def validate_selection(query,image_path):
    if query.get('confirmed_new_capture') is not True or query.get('target_confirmed_before_search') is not True:
        raise ValueError('A new-capture and pre-result target confirmation are required for every query.')
    selection=query.get('selection',{})
    if selection.get('confirmed_before_search') is not True:raise ValueError('Selection points must be confirmed before retrieval.')
    points,labels=selection.get('points'),selection.get('labels')
    validate_points(points,labels,image_path)


def validate_points(points,labels,image_path):
    if not isinstance(points,list) or not 1<=len(points)<=50 or not isinstance(labels,list) or len(labels)!=len(points) or 1 not in labels:
        raise ValueError('Each query needs 1-50 aligned SAM2 points with a positive point.')
    with Image.open(image_path) as raw:width,height=ImageOps.exif_transpose(raw).size
    for point,label in zip(points,labels):
        if (not isinstance(point,list) or len(point)!=2 or type(label) is not int or label not in (0,1)
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in point)
                or not (0<=point[0]<width and 0<=point[1]<height)):
            raise ValueError('Invalid SAM2 point/label or coordinates outside oriented query photo.')


def validate_collection(manifest_path):
    source=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    if source.get('scope')!='fresh_identity_paired_evaluation':raise ValueError('Use a fresh paired collection manifest, not the reviewed-view pilot.')
    metadata=CatalogMetadata(CATALOG_METADATA_FILE)
    validated=load_manifest(Path(manifest_path),metadata)
    catalog_pixels={decoded_sha(CATALOG_DIR/p) for p in metadata.items}
    seen_pixels=set()
    for original,validated_query in zip(source['queries'],validated):
        image=validated_query['image'];validate_selection(original,image)
        validate_image_bytes(image.read_bytes())
        if file_sha256(image)!=original.get('sha256'):raise ValueError('Collected query bytes changed.')
        pixels=decoded_sha(image)
        if pixels in catalog_pixels:raise ValueError('Decoded query pixels duplicate a catalog photo.')
        if pixels in seen_pixels:raise ValueError('Two queries contain the same decoded photo.')
        seen_pixels.add(pixels)
        validated_query['selection']=original['selection']
    return validated,metadata


def run(manifest_path,output,url):
    if urlparse(url).hostname not in {'localhost','127.0.0.1','::1'}:raise ValueError('Only the local application is supported.')
    queries,metadata=validate_collection(manifest_path)
    manifest_hash=file_sha256(manifest_path)
    index_path=ROOT/'data/catalog_siglip2.faiss';index_hash=file_sha256(index_path)
    groups=ReviewedProductGroups.load(ROOT/'data/reviewed_product_groups.json',metadata.items,CATALOG_DIR)
    session=requests.Session();session.trust_env=False;url=url.rstrip('/')
    health=session.get(url+'/api/health',timeout=10);health.raise_for_status()
    if health.json().get('indexed_images')!=len(metadata.items):raise ValueError('Server gallery size differs from validated catalog.')
    records={'full':[],'sam2':[]}
    def search(content,mime,mode,category):
        response=session.post(url+'/api/search?top_k=50',files={'image':('query',content,mime)},data={'search_mode':mode,'category':category},timeout=120)
        response.raise_for_status();body=response.json()
        if not body.get('results'):raise ValueError('Search returned no results.')
        return body
    def result(query,body):
        expected=groups.by_product.get(query['product_id'],query['product_id']);identities=[]
        for row in body['results']:
            identity=groups.by_product.get(row['product_id'],row['product_id'])
            if identity not in identities:identities.append(identity)
            if len(identities)==10:break
        return {'query_image':query['relative_image'],'query_sha256':query['sha256'],
                'expected_product_id':query['product_id'],'expected_reviewed_identity':expected,
                'target_rank_at10':next((i for i,p in enumerate(identities,1) if p==expected),None),
                'retrieved_identities':identities,'routing':body.get('query',{}).get('category_routing')}
    # Save the input used before inference; contains no model results.
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    seal=output.with_suffix('.sealed_manifest.json')
    seal.write_bytes(Path(manifest_path).read_bytes())
    for query in queries:
        content=query['image'].read_bytes()
        with Image.open(BytesIO(content)) as raw:mime=Image.MIME[raw.format]
        full=search(content,mime,'full',query['search_category']);records['full'].append(result(query,full))
        try:
            selection=query['selection']
            segment=session.post(url+'/api/segment',files={'image':('query',content,mime)},data={'points':json.dumps(selection['points']),'labels':json.dumps(selection['labels'])},timeout=120)
            segment.raise_for_status();body=segment.json()
            cutout=base64.b64decode(body['cutout'],validate=True)
            with Image.open(BytesIO(cutout)) as image:image.verify()
            selected=search(cutout,'image/png','ai',query['search_category'])
            row=result(query,selected);row['sam_score']=body.get('score');row['sam_bbox']=body.get('bbox')
            records['sam2'].append(row)
        except (requests.RequestException,ValueError,KeyError) as error:
            records['sam2'].append({'query_image':query['relative_image'],'query_sha256':query['sha256'],'expected_product_id':query['product_id'],'target_rank_at10':None,'selection_failed':True,'error_type':type(error).__name__})
        print('Evaluated '+query['relative_image'],flush=True)
    if file_sha256(index_path)!=index_hash or file_sha256(manifest_path)!=manifest_hash:raise RuntimeError('Index or collection manifest changed during evaluation.')
    report={'schema_version':'1.0','scope':'fresh_photos_user_labelled_paired_identity_evaluation',
            'created_at_utc':datetime.now(timezone.utc).isoformat(),'manifest_sha256':manifest_hash,
            'original_index_sha256':index_hash,'query_count':len(queries),
            'suites':{mode:{'metrics':identity_metrics(rows),'queries':rows} for mode,rows in records.items()},
            'sam2_vs_full_top1':paired_top1_statistics(np.asarray([r['target_rank_at10']==1 for r in records['full']]),np.asarray([r['target_rank_at10']==1 for r in records['sam2']])),
            'sam2_failure_count':sum(r.get('selection_failed',False) for r in records['sam2']),
            'limitations':['Human-labelled product identity may lack merchant SKU verification.',
                           'New-capture attestation requires human review; automatic byte/pixel checks do not detect all edited copies.',
                           'SAM2 points were chosen before results; masks are not manually approved by this runner.',
                           'Purposeful collection is a development evaluation unless an independent sampling plan is used.',
                           'Successful API searches append normal local telemetry; raw query photos are not stored by this runner.']}
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=ROOT/'evaluation/cache/identity_collection/manifest.json')
    parser.add_argument('--output',type=Path,default=ROOT/'evaluation/cache/identity_collection/paired_results.json')
    parser.add_argument('--url',default='http://127.0.0.1:8001');args=parser.parse_args()
    report=run(args.manifest,args.output,args.url)
    print(json.dumps({m:s['metrics'] for m,s in report['suites'].items()},indent=2))


if __name__=='__main__':main()
