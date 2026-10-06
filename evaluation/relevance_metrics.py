"""Evaluate fully judged candidate pools; never infer human relevance labels."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path


def ndcg(grades, k):
    gains = lambda values: sum((2**g-1)/math.log2(i+2) for i,g in enumerate(values[:k]))
    ideal = gains(sorted(grades, reverse=True))
    return gains(grades)/ideal if ideal else 0.0


def evaluate(manifest, annotation, k=5):
    original = dict(manifest); pack_id = original.pop("pack_id")
    expected_hash = hashlib.sha256(json.dumps(original,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if pack_id != expected_hash or annotation.get("pack_id") != pack_id:
        raise ValueError("Review pack mismatch or manifest modified")
    if isinstance(k,bool) or not isinstance(k,int) or k < 1:
        raise ValueError("k must be a positive integer")
    expected = set(); queries = {}
    for query in manifest["queries"]:
        qid=query["query_id"]
        if qid in queries: raise ValueError("Duplicate query")
        ids=[c["product_id"] for c in query["candidates"]]
        if len(ids)!=len(set(ids)) or len(ids)<k: raise ValueError("Invalid candidate pool or k exceeds pool")
        for ranking in query["rankings"].values():
            if len(ranking)!=len(ids) or set(ranking)!=set(ids): raise ValueError("Invalid ranking candidate set")
        if "baseline" not in query["rankings"]: raise ValueError("Missing baseline")
        expected.update((qid,pid) for pid in ids); queries[qid]=query
    if not queries: raise ValueError("Empty review pack")
    grades={}
    for judgment in annotation.get("judgments",[]):
        key=(judgment["query_id"],judgment["product_id"]); grade=judgment["relevance"]
        if key not in expected: raise ValueError("Unknown query or candidate")
        if key in grades: raise ValueError("Duplicate judgment")
        if isinstance(grade,bool) or not isinstance(grade,int) or grade not in range(4): raise ValueError("Relevance must be integer 0..3")
        grades[key]=grade
    if set(grades)!=expected: raise ValueError("Incomplete judgments; no metrics were calculated")
    methods=set(next(iter(queries.values()))["rankings"])
    records=[]
    for qid,query in queries.items():
        if set(query["rankings"])!=methods: raise ValueError("Inconsistent ranking methods")
        for name,ranking in query["rankings"].items():
            values=[grades[(qid,pid)] for pid in ranking]
            records.append({"query_id":qid,"method":name,"ndcg":ndcg(values,k),
                            "precision_relevant":sum(g>=2 for g in values[:k])/k})
    summary={}
    for name in sorted(methods):
        rows=[r for r in records if r["method"]==name]
        summary[name]={metric:sum(r[metric] for r in rows)/len(rows) for metric in ["ndcg","precision_relevant"]}
    for name in summary:
        summary[name]["ndcg_delta_vs_baseline"]=summary[name]["ndcg"]-summary["baseline"]["ndcg"]
    return {"scope":"human_resemblance_development_pilot_only","pack_id":pack_id,"k":k,
            "query_count":len(queries),"relevant_grade_threshold":2,"summary":summary,"records":records,
            "limitations":["Not exact-product accuracy.","Only fully judged original candidate pools are compared.",
                           "Small development pilot; no independent test claim or significance established."]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--judgments",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--k",type=int,default=5)
    args=parser.parse_args()
    report=evaluate(json.loads(args.manifest.read_text(encoding="utf-8")),json.loads(args.judgments.read_text(encoding="utf-8")),args.k)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report["summary"],indent=2))


if __name__=="__main__":
    main()
