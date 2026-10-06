"""Build a blind, local similarity-review pilot from validation only."""
from __future__ import annotations
import argparse, base64, hashlib, html, json, random
from pathlib import Path
from urllib.parse import urlparse
import requests
from backend.catalog_config import ROOT, CATALOG_DIR


def digest(data):
    return hashlib.sha256(data).hexdigest()


def picture(path):
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode()


def build(url, output):
    if urlparse(url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Only local APIs are supported")
    from evaluation.explore_appearance_reranking import appearance
    output.mkdir(parents=True, exist_ok=True)
    session = requests.Session(); session.trust_env = False
    queries = []; sections = []
    weights = [("baseline", 0, 0), ("color_10", .1, 0), ("color_10_texture_10", .1, .1)]
    for number, category in enumerate(["dress", "pants", "outwear"], 1):
        files = sorted((ROOT / "datasets/clothing_small/validation" / category).glob("*.jpg"))
        if not files:
            raise ValueError("Missing validation category: " + category)
        path = files[0]; data = path.read_bytes(); qid = f"dev_{number:02d}_{category}"
        response = session.post(url.rstrip("/") + "/api/search", params={"top_k": 12},
                                data={"category": "auto", "search_mode": "full"},
                                files={"image": (path.name, data, "image/jpeg")}, timeout=90)
        response.raise_for_status(); payload = response.json()
        qc, qt, _ = appearance(path); candidates = []; cards = []
        for rank, item in enumerate(payload["results"], 1):
            catalog_path = (CATALOG_DIR / item["image"]).resolve()
            if not catalog_path.is_relative_to(CATALOG_DIR.resolve()):
                raise ValueError("Candidate escaped catalog")
            color, texture, _ = appearance(catalog_path)
            candidate = {"product_id": item["product_id"], "image": item["image"],
                         "sha256": digest(catalog_path.read_bytes()), "title": item["title"],
                         "baseline_rank": rank, "semantic": float(item["score"]),
                         "color": float(qc @ color), "texture_proxy": float(qt @ texture)}
            candidates.append(candidate)
            key = qid + "::" + item["product_id"]
            cards.append(f'<article><img src="{picture(catalog_path)}" alt="قطعة مرشحة"><p>{html.escape(item["title"])}</p>'
                         f'<select data-key="{html.escape(key)}" aria-label="درجة تشابه {html.escape(item["title"])}">'
                         '<option value="">اختر تقييمك</option><option value="0">0 — غير مشابه</option>'
                         '<option value="1">1 — شبه ضعيف</option><option value="2">2 — مشابه مناسب</option>'
                         '<option value="3">3 — مشابه جدًا</option></select></article>')
        if len(candidates) != 12:
            raise ValueError("Expected twelve candidates per query")
        random.Random(1701 + number).shuffle(cards)
        rankings = {}
        for name, wc, wt in weights:
            ranking = sorted(candidates, key=lambda c: (1-wc-wt)*c["semantic"] + wc*c["color"] + wt*c["texture_proxy"], reverse=True)
            rankings[name] = [c["product_id"] for c in ranking]
        queries.append({"query_id": qid, "source": path.relative_to(ROOT).as_posix(),
                        "sha256": digest(data), "category": category,
                        "candidates": candidates, "rankings": rankings,
                        "routing": payload.get("query", {}).get("category_routing")})
        sections.append(f'<section><h2>الصورة {number} من 3</h2><img class="query" src="{picture(path)}" alt="صورة الاستعلام {number}">'
                        '<p>قيّم الشبه العام مع القطعة في هذه الصورة، بما يشمل اللون والنقشة والقصة.</p>'
                        '<div class="cards">' + ''.join(cards) + '</div></section>')
    protocol = {"schema_version": "1.0", "split": "development_validation_pilot",
                "weights": [{"name": n, "color": c, "texture_proxy": t} for n,c,t in weights],
                "query_count": len(queries), "candidate_pool": "original_top_12_auto_category",
                "queries": queries,
                "limitations": ["Pilot only, not independent test evidence.", "Ratings measure resemblance, not product identity.",
                                 "Only the original twelve candidates can be reordered.", "Catalog backgrounds affect appearance features."]}
    pack_id = digest(json.dumps(protocol, sort_keys=True, ensure_ascii=False).encode())
    protocol["pack_id"] = pack_id
    output.joinpath("manifest.json").write_text(json.dumps(protocol, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    page = """<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>تقييم تشابه الملابس — تطوير</title>
<style>body{font-family:Tahoma,Arial;background:#f3f4f8;color:#182039;margin:0;padding:24px;line-height:1.8}main{max-width:1100px;margin:auto}header,section{background:white;border-radius:16px;padding:24px;margin-bottom:24px}.query{max-height:330px;max-width:100%;object-fit:contain}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:16px}article{padding:12px;border:1px solid #d7dce8;border-radius:12px}article img{width:100%;height:230px;object-fit:contain}select,input,button{font-size:16px;padding:10px;border-radius:8px;border:1px solid #a1a9bd}select{width:100%}button{background:#5142cc;color:white;cursor:pointer}aside{position:sticky;bottom:0;background:#182039;color:white;padding:15px;border-radius:12px;display:flex;gap:20px;align-items:center;flex-wrap:wrap}</style>
<main><header><h1>تقييم تشابه الملابس</h1><p>ثلاث صور تطوير، و12 قطعة لكل صورة. ترتيب البطاقات عشوائي؛ درجات النموذج وترتيبه مخفيان. لا تبحث عن نفس المنتج؛ قيّم الشبه الذي تراه.</p><p>0 غير مشابه · 1 شبه ضعيف · 2 مشابه مناسب · 3 مشابه جدًا. استخدم المعنى نفسه مع كل الصور.</p><label>اسم مختصر للمقيّم (اختياري) <input id="rater" maxlength="60" placeholder="مثلاً: المقيّم الأول"></label><p>هذه الصفحة محلية ولا ترسل التقييمات. زر الحفظ ينزّل JSON على جهازك. التقييم غير المكتمل لا يستخدم لقياس التحسن.</p></header>__SECTIONS__<aside><span id="progress"></span><button id="export">حفظ التقييمات JSON</button><span id="notice"></span></aside></main>
<script>const packId=__PACK_ID__;const selections=[...document.querySelectorAll('select[data-key]')];const storageKey='relevance-'+packId;let saved={};try{saved=JSON.parse(localStorage.getItem(storageKey)||'{}')}catch{};for(const s of selections){if(['0','1','2','3'].includes(String(saved[s.dataset.key])))s.value=String(saved[s.dataset.key]);s.addEventListener('change',()=>{saved[s.dataset.key]=s.value;try{localStorage.setItem(storageKey,JSON.stringify(saved))}catch{}update()})}function update(){document.querySelector('#progress').textContent=`التقييمات المكتملة: ${selections.filter(s=>s.value!=='').length} / ${selections.length}`}update();document.querySelector('#export').addEventListener('click',()=>{const judgments=selections.filter(s=>s.value!=='').map(s=>{const[q,p]=s.dataset.key.split('::');return{query_id:q,product_id:p,relevance:Number(s.value)}});const result={schema_version:'1.0',pack_id:packId,rater:document.querySelector('#rater').value.trim(),complete:judgments.length===selections.length,judgments};const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));a.download='relevance_judgments.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);document.querySelector('#notice').textContent=result.complete?'تم حفظ التقييم الكامل':'تم حفظ تقييم جزئي؛ أكمل الباقي قبل القياس'});</script></html>"""
    page = page.replace("__SECTIONS__", ''.join(sections)).replace("__PACK_ID__", json.dumps(pack_id))
    output.joinpath("index.html").write_text(page, encoding="utf-8")
    print("Review:", output.resolve() / "index.html", flush=True)
    return protocol


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/cache/relevance_review")
    args = parser.parse_args(); build(args.url, args.output)


if __name__ == "__main__":
    main()
