"""Probe user-confirmed positives. Unjudged results are not negatives."""
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
from backend.catalog_config import ROOT,CATALOG_DIR


def checksum(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_confirmation(manifest,confirmation):
    original=dict(manifest);pack=original.pop('pack_id')
    if hashlib.sha256(json.dumps(original,sort_keys=True,ensure_ascii=False).encode()).hexdigest()!=pack:
        raise ValueError('Manifest was modified')
    if confirmation.get('pack_id')!=pack:raise ValueError('Confirmation pack mismatch')
    if confirmation.get('scope')!='known_positive_confirmation_before_review_retrieval':raise ValueError('Invalid confirmation scope')
    selected=confirmation.get('selected_positive_ids',[])
    if not isinstance(selected,list) or not selected or len(selected)!=len(set(selected)):raise ValueError('Empty or duplicate positive IDs')
    proposed={row['product_id']:row for row in manifest['proposed_candidates']}
    if not set(selected)<=set(proposed):raise ValueError('Unknown positive ID')
    return selected,proposed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    folder=ROOT/'evaluation/cache/relevance_review'
    parser.add_argument('--manifest',type=Path,default=folder/'coverage_manifest.json')
    parser.add_argument('--confirmation',type=Path,default=folder/'coverage_confirmation.json')
    parser.add_argument('--output',type=Path,default=folder/'known_positive_probe.json')
    parser.add_argument('--url',default='http://127.0.0.1:8001')
    args=parser.parse_args()
    if urlparse(args.url).hostname not in {'127.0.0.1','localhost','::1'}:parser.error('Only local servers are supported')
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    confirmation=json.loads(args.confirmation.read_text(encoding='utf-8'))
    selected,proposed=validate_confirmation(manifest,confirmation)
    query=(ROOT/manifest['query']).resolve()
    if not query.is_relative_to((ROOT/'datasets/clothing_small/validation').resolve()) or checksum(query)!=manifest['query_sha256']:raise ValueError('Query differs from approved review')
    for pid in selected:
        path=(CATALOG_DIR/proposed[pid]['image']).resolve()
        if not path.is_relative_to(CATALOG_DIR.resolve()) or checksum(path)!=proposed[pid]['sha256']:raise ValueError('Approved catalog image changed')
    session=requests.Session();session.trust_env=False
    suites={}
    for category in ['auto','all']:
        with query.open('rb') as handle:
            response=session.post(args.url.rstrip('/')+'/api/search',params={'top_k':50},
                                  data={'category':category,'search_mode':'full'},files={'image':(query.name,handle,'image/jpeg')},timeout=90)
        response.raise_for_status();body=response.json()
        if body.get('query',{}).get('sha256')!=manifest['query_sha256']:raise ValueError('Server query hash mismatch')
        results=body['results'];ranks={row['product_id']:i for i,row in enumerate(results,1)}
        positives=[{'product_id':pid,'title':proposed[pid]['title'],'rank_in_returned_top50':ranks.get(pid)} for pid in selected]
        suites[category]={'routing':body.get('query',{}).get('category_routing'),'returned_count':len(results),
                          'positives':positives,'known_positive_hits':{str(k):sum(ranks.get(pid,51)<=k for pid in selected) for k in [1,5,10,20,50]},
                          'results':results}
        print(category,[(p['title'],p['rank_in_returned_top50']) for p in positives],flush=True)
    report={'scope':'single_query_known_positive_development_probe','created_at_utc':datetime.now(timezone.utc).isoformat(),
            'query':manifest['query'],'query_sha256':manifest['query_sha256'],'confirmation_sha256':checksum(args.confirmation),
            'confirmation_provenance':confirmation.get('provenance','user_confirmation_file'),
            'approved_positive_count':len(selected),'suites':suites,'production_behavior_changed':False,
            'limitations':['Purposive single development query; not independent accuracy evidence.',
                           'Only the API top 50 are observed. Missing positives may rank below 50.',
                           'Unselected and other retrieved candidates are unjudged, not negatives.',
                           'No global recall or precision is inferred from a partial positive list.']}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(args.output.resolve())


if __name__=='__main__':main()
