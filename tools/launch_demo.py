"""Run the local presentation with the existing environment and model files."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys
import threading
import time
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parent.parent


def health(port: int) -> dict | None:
    try:
        # Loopback readiness must bypass system proxies and their network policy.
        with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:{port}/api/health", timeout=2) as response:
            data = json.load(response)
        if (data.get("status") == "ok" and data.get("index_ready") is True
                and data.get("indexed_images") == 3068
                and data.get("catalog_source") == "clothing_small_train"
                and data.get("search_device") in {"cuda", "cpu"}
                and data.get("segmentation_device") in {"cuda", "cpu"}):
            return data
    except (OSError, ValueError):
        pass
    return None


def preflight() -> None:
    required = ["frontend/index.html", "data/catalog_metadata_train.json",
                "data/catalog_siglip2.faiss", "data/catalog_siglip2_paths.json",
                "models/siglip2_base/model.safetensors",
                "models/sam2_base_plus/model.safetensors"]
    missing = [name for name in required if not (ROOT / name).is_file()]
    if missing:
        raise RuntimeError("Missing presentation files: " + ", ".join(missing))
    catalog = ROOT / "datasets/clothing_small/train"
    if not catalog.is_dir():
        raise RuntimeError("Missing catalog: " + str(catalog))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true", help="Check files and health without starting a server")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    preflight()
    url = f"http://127.0.0.1:{args.port}/"
    current = health(args.port)
    if args.check:
        print(json.dumps({"files_ready": True, "health": current}, indent=2))
        return 0 if current else 1
    if current:
        print(f"Application is already ready: {url}")
        if not args.no_browser:
            webbrowser.open(url)
        return 0
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            raise RuntimeError(f"Port {args.port} is occupied by a service that is not ready. "
                               "Check its window; this launcher will not stop it.")
    # Local models already exist. Avoid model downloads during the presentation.
    reviewed_groups = ROOT / "data/reviewed_product_groups.json"
    if reviewed_groups.is_file():
        os.environ.setdefault("GRADUATION_AI_REVIEWED_GROUPS", str(reviewed_groups))
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    print("Loading local models. Keep this window open; press Ctrl+C to stop.", flush=True)
    print(f"Browser opens after readiness check: {url}", flush=True)
    stop = threading.Event()
    def open_when_ready():
        deadline = time.monotonic() + 180
        while not stop.is_set() and time.monotonic() < deadline:
            if health(args.port):
                print(f"READY: {url}", flush=True)
                if not args.no_browser:
                    webbrowser.open(url)
                return
            stop.wait(1)
        if not stop.is_set():
            print("Readiness timed out. Check the errors in this window; browser was not opened.", flush=True)
    watcher = threading.Thread(target=open_when_ready, daemon=True)
    watcher.start()
    try:
        import uvicorn
        uvicorn.run("app:app", host="127.0.0.1", port=args.port, reload=False)
    finally:
        stop.set()
        watcher.join(timeout=3)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError) as error:
        print(f"Presentation could not start: {error}", flush=True)
        raise SystemExit(1)
