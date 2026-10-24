"""Screen uncertainty fallbacks on historical validation records, without inference.

This is a development replay, not a fresh accuracy benchmark or threshold tuning
on the test set. A screened winner must not be promoted on this evidence alone.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from evaluation.compare_safe_crop_catalog import paired_top1_statistics
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
POLICIES = [(0.0,0.0),(.15,.02),(.20,.03),(.25,.05),(.30,.08),(.40,.10)]


def summarize(records, confidence, margin):
    if not records: raise ValueError('Validation records are empty.')
    baseline = np.asarray([r['auto_correct'] for r in records], dtype=bool)
    fallback = [r['confidence'] < confidence or r['margin'] < margin for r in records]
    candidate = np.asarray([r['unrestricted_correct'] if use_all else r['auto_correct']
                            for r,use_all in zip(records,fallback)], dtype=bool)
    return {'minimum_confidence':confidence, 'minimum_margin':margin,
            'fallback_queries':sum(fallback), 'correct_queries':int(candidate.sum()),
            'category_top1':float(candidate.mean()),
            'vs_current_auto':paired_top1_statistics(baseline,candidate)}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'evaluation/results/category_routing_comparison.json')
    parser.add_argument('--output',type=Path,default=ROOT/'evaluation/results/uncertain_category_replay.json')
    args=parser.parse_args()
    source=json.loads(args.source.read_text(encoding='utf-8'))
    # Only validation records are accessed; the previously measured test set is not a tuning set.
    records=source['suites']['validation']['records']
    for relative,expected in source['artifacts'].items():
        if digest(ROOT/relative)!=expected: raise ValueError('Changed source artifact: '+relative)
    for row in records:
        if digest(ROOT/row['image'])!=row['sha256']: raise ValueError('Changed query: '+row['image'])
        if row['auto_correct']!=(row['auto_prediction']==row['truth']): raise ValueError('Inconsistent auto label.')
        if row['unrestricted_correct']!=(row['unrestricted_prediction']==row['truth']): raise ValueError('Inconsistent unrestricted label.')
    policies=[summarize(records,c,m) for c,m in POLICIES]
    report={'schema_version':'1.0','created_at_utc':datetime.now(timezone.utc).isoformat(),
            'scope':'historical_validation_replay_no_fresh_inference',
            'source_sha256':digest(args.source),'source_created_at_utc':source['created_at_utc'],
            'query_count':len(records),'verified_query_hashes':len(records),
            'artifacts':source['artifacts'],'test_records_used':False,
            'current_auto_correct':sum(r['auto_correct'] for r in records),
            'unrestricted_correct':sum(r['unrestricted_correct'] for r in records),
            'policies':policies,'decision':'retain_current_auto_routing',
            'production_routing_changed':False,
            'limitations':['These are previously observed category labels, not exact-product judgments.',
                           'Six development policies were screened; the best observed policy is exploratory.',
                           'A gain of one validation query does not establish robust improvement.',
                           'No fresh user photos, new held-out set, Top-5 or segmentation-quality measurement is claimed.',
                           'Centroid confidence is not a calibrated probability of a correct match.']}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for policy in policies:
        print(f"c={policy['minimum_confidence']:.2f} m={policy['minimum_margin']:.2f}: "
              f"{policy['correct_queries']}/{len(records)}, fallback={policy['fallback_queries']}")
    print('Decision: retain current routing; exploratory replay only.')
    return 0


if __name__=='__main__': raise SystemExit(main())
