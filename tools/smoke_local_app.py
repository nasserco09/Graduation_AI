"""Repeatable HTTP integration checks against an already-running local app.

Successful searches append normal telemetry. This checks the HTTP/frontend
asset contract; it is not a substitute for clicking through the browser UI.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import time
from urllib.parse import urlparse

from PIL import Image
import requests

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--image", type=Path, default=ROOT / "evaluation/cache/sam2_ab/composites/000_dress.jpg")
    parser.add_argument("--point", nargs=2, type=int, default=[768, 256])
    parser.add_argument("--output", type=Path, default=ROOT / "evaluation/results/local_smoke.json")
    args = parser.parse_args()
    if urlparse(args.url).hostname not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Only a local server is supported.")
    image_bytes = args.image.read_bytes()
    with Image.open(BytesIO(image_bytes)) as image:
        width, height = image.size
        if not (0 <= args.point[0] < width and 0 <= args.point[1] < height):
            parser.error("Selection point is outside the image.")
        mime = Image.MIME[image.format]
    session = requests.Session()
    session.trust_env = False
    checks = []
    def check(name, condition, **details):
        checks.append({"name": name, "passed": bool(condition), **details})
        print(f"{'PASS' if condition else 'FAIL'} {name}", flush=True)
    def upload(path, content=image_bytes, image_type=mime, **fields):
        return session.post(args.url.rstrip('/') + path,
                            files={"image": ("smoke-query", content, image_type)},
                            data=fields, timeout=120)
    health = session.get(args.url + "/api/health", timeout=30)
    check("health", health.status_code == 200 and health.json().get("index_ready") is True,
          response=health.json())
    validation = session.get(args.url + "/api/catalog/validation", timeout=30)
    check("catalog_metadata", validation.status_code == 200 and validation.json().get("valid") is True)
    for path in ("/", "/about.html", "/js/app.js", "/styles/styles.css", "/styles/about.css", "/assets/logo.svg", "/docs"):
        response = session.get(args.url + path, timeout=30)
        check(f"asset:{path}", response.status_code == 200 and bool(response.content), status=response.status_code)
    def search(name, content, image_type, mode, category="auto"):
        start = time.perf_counter()
        response = upload("/api/search?top_k=8", content, image_type, search_mode=mode, category=category)
        body = response.json()
        results, query = body.get("results", []), body.get("query", {})
        check(name, response.status_code == 200 and bool(results) and len(results) <= 8
              and query.get("sha256") == hashlib.sha256(content).hexdigest()
              and query.get("monitoring_warning") is None,
              status=response.status_code, elapsed_ms=round((time.perf_counter()-start)*1000, 3),
              top1_category=results[0].get("category_key") if results else None,
              routing=query.get("category_routing"), search_id=query.get("search_id"))
        if results:
            image_response = session.get(args.url + results[0]["url"], timeout=30)
            check(f"{name}:result_image", image_response.status_code == 200)
    search("full_image", image_bytes, mime, "full")
    for name, points, labels in (
        ("sam2_positive", [args.point], [1]),
        ("sam2_refined", [args.point, [0, 0]], [1, 0]),
    ):
        response = upload("/api/segment", points=json.dumps(points), labels=json.dumps(labels))
        body = response.json()
        valid = response.status_code == 200 and bool(body.get("cutout")) and bool(body.get("overlay"))
        check(name, valid, status=response.status_code, score=body.get("score"), bbox=body.get("bbox"))
        if valid:
            cutout = base64.b64decode(body["cutout"])
            with Image.open(BytesIO(cutout)) as image:
                check(f"{name}:cutout", image.width > 0 and image.height > 0)
            search(f"{name}:search", cutout, "image/png", "ai")
    # Exercise the API's manual-mode contract with a prepared crop, not frontend gestures.
    with Image.open(BytesIO(image_bytes)) as image:
        half_start = 0 if args.point[0] < width / 2 else width // 2
        crop = image.crop((half_start, 0, half_start + width // 2, height))
        buffer = BytesIO()
        crop.save(buffer, format="PNG")
    for mode in ("rect", "poly", "free"):
        search(f"prepared_manual_{mode}", buffer.getvalue(), "image/png", mode)
    search("unrestricted", image_bytes, mime, "full", "all")
    search("category_override", image_bytes, mime, "full", "dress")
    for name, path, content, image_type, fields in (
        ("invalid_image", "/api/search", b"not an image", "image/jpeg", {}),
        ("empty_points", "/api/segment", image_bytes, mime, {"points": "[]", "labels": "[]"}),
        ("invalid_top_k", "/api/search?top_k=51", image_bytes, mime, {}),
    ):
        response = upload(path, content, image_type, **fields)
        check(name, response.status_code == 400, status=response.status_code)
    report = {"schema_version": "1.0", "created_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "http_integration_not_browser_interaction", "url": args.url,
              "fixture": str(args.image), "fixture_sha256": hashlib.sha256(image_bytes).hexdigest(),
              "passed": all(c["passed"] for c in checks), "checks": checks,
              "limitations": ["Prepared manual crops validate API modes, not rectangle/polygon/lasso gestures.",
                              "Does not establish aggregate retrieval accuracy or exact product identity.",
                              "Successful searches append normal local telemetry."]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Report: {args.output.resolve()}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
