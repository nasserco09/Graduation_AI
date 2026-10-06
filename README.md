# Graduation_AI

Hybrid AI-based visual search prototype for a graduation project.

The system allows users to upload an image of a fashion product, optionally select the target object manually or with AI assistance, and search for visually similar products from a local catalog.

---

## Current Features

- Image upload
- Full-image visual search
- Manual product selection:
  - Rectangle
  - Polygon
  - Free Draw / Lasso
- AI-assisted product selection using SAM2
- Positive selection points
- Negative exclusion points
- Interactive mask refinement
- Product cutout generation
- Visual similarity search using SigLIP2
- Fast vector similarity search using FAISS
- GPU acceleration with PyTorch and CUDA
- Local/offline model support
- Exact final-query preview before search
- Browser/server SHA-256 verification of the uploaded query
- Shared deterministic preprocessing for queries and catalog images
- Automatic index invalidation when preprocessing or catalog content changes
- Automatic product-category prediction from catalog embedding centroids
- Category-aware retrieval with a user correction override
- Category confidence and routing details returned by the API
- Versioned catalog metadata with stable product identities
- Catalog-to-metadata validation before indexing
- Exact-product evaluation metrics separated from category accuracy
- Anonymous local search telemetry and user feedback
- Monitoring summaries and privacy-safe failure exports
- Server-side upload validation (type, size, dimensions, and image integrity)
- Concurrency-safe catalog reindexing and searching
- Expanded application catalog using all 3,068 images from the train split
- Strict separation of train catalog, validation, and test images

---

## Current AI Pipeline

```text
User Image
   ↓
Optional Product Selection
   ├── Manual Selection
   │   ├── Rectangle
   │   ├── Polygon
   │   └── Free Draw
   │
   └── AI Assisted Selection
       └── SAM2
            ↓
        Product Mask
            ↓
        Product Cutout
            ↓
Shared image preprocessing
   ↓
SigLIP2 Image Encoder
   ↓
Embedding Vector
   ↓
Automatic or user-selected category
   ↓
FAISS Index
   ↓
Similar Products
```

---

## Query and Catalog Consistency

Both the selected query image and every catalog image pass through the same
preprocessing contract before SigLIP2 encoding:

1. Apply EXIF orientation.
2. Replace transparent pixels with a white background.
3. Convert to RGB.
4. Preserve aspect ratio and center the image on a square white canvas.

The preprocessing version and a catalog checksum are saved beside the FAISS
index. If either one changes, the application rejects the stale index and
builds a fresh one on the next search.

The search screen also displays the exact file being uploaded. The browser
and backend independently calculate its SHA-256 digest, so the interface can
confirm that the server received the same bytes the user previewed.

---

## Historical Evaluation Baseline

The checked-in baseline is stored in `data/baseline_metrics.json`. It records
the existing class-level evaluation separately from exact-product matching:

- Clean test set: 372 queries, P@1 = 0.908602, P@5 = 0.889785,
  P@10 = 0.870968, mAP@10 = 0.825378, MRR = 0.944806.
- Multi-product test set: full-image top-1 = 0.46 and SAM2 top-1 = 0.75,
  an improvement of 29 percentage points.

These saved test results agree with `evaluation/results/FINAL_TEST_RESULTS.json`.
The separate `sam2_vs_full.json` result (48% to 80%) uses validation composites,
not the held-out test composites (46% to 75%). They are different experiments.
Historical scripts use existence-based caches and do not explicitly apply the
current square preprocessing contract, so these numbers must not be described
as a fresh measurement of the current application. They do not prove exact
catalog-item identity matching. See `docs/EVALUATION_EVIDENCE_AR.md`.

Fresh category-routing checks on 6 October 2026 used the current original index
and application query encoder: unrestricted versus automatic Top-1 was
92.08% versus 94.72% on validation (341), and 92.20% versus 96.24% on test (372).
This covers clean images and category relevance only; no routing threshold was
tuned and production behavior was not changed.

---

## Application Catalog and Category-Aware Search

When `datasets/clothing_small/train` and its generated metadata are available,
the application uses all 3,068 train images as its searchable catalog. The 341
validation images and 372 test images remain excluded, preventing evaluation
leakage. If the train split is unavailable, the application falls back to the
original 30-image demo catalog.

During a search, the system calculates one normalized embedding centroid per
category and routes the query to its closest category. FAISS still ranks
products by visual similarity, but results outside the applied category are
removed.

The interface defaults to automatic prediction and displays the predicted
category and catalog-relative confidence. Users can override the prediction or
disable category filtering. The health endpoint reports the active catalog
source, and the validation endpoint reports the number of searchable images.

---

## Product Metadata and Exact-Identity Evaluation

`data/catalog_metadata_train.json` is the authoritative mapping for the 3,068
train images. `data/catalog_metadata.json` remains the fallback mapping for the
30-image demo. Every searchable image must have one valid metadata record
before indexing. Regenerate the train mapping after changing that split with:

```powershell
python -m tools.build_train_catalog_metadata
```

Exact-product evaluation is intentionally separate from the existing
class-level evaluation. Add different photos of catalog products to the
manifest described in `docs/EXACT_PRODUCT_EVALUATION_AR.md`, then run:

```powershell
python -m evaluation.exact_product_evaluation
```

The generated report contains exact Top-1, Top-5, Top-10, MRR, category
accuracy, per-query rankings, and average latency. An empty manifest produces
an explicit error instead of publishing an invented accuracy figure.

---

## Search Monitoring and Feedback

Each successful search receives an anonymous `search_id`. The interface lets a
user identify the correct product, report no match, or correct a predicted
category. Search mode, routing, ranked product IDs, scores, and latency are
stored in a local SQLite database. Raw query images and personal identity are
not stored.

Open `/api/monitoring/summary` for aggregate indicators, or run:

```powershell
python -m evaluation.analyze_search_feedback
```

See `docs/SEARCH_MONITORING_AR.md` for the Arabic workflow and interpretation
limits.

---

## Run the application

The two local model folders are intentionally excluded from Git and must exist
before startup:

```text
models/siglip2_base/
models/sam2_base_plus/
```

From the project root on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. API documentation is available at
`http://127.0.0.1:8000/docs`.

`requirements.txt` is the UTF-8 exact environment snapshot. For an offline
installation, use the wheels already downloaded in `offline_wheels` together
with `requirements_offline.txt`; the CUDA-specific PyTorch packages must match
the target computer's CUDA installation.

## Verification

Run the dependency-light unit suite from the project root:

```powershell
python -m unittest discover -s tests -v
node --test tests/frontend_selection.test.cjs
```

The JavaScript tests require Node.js only for development and execute the actual
frontend source with a minimal DOM and controlled API responses. They cover
late SAM2 responses after reset, stale failures during a new request, and
retaining the previous selection after failed refinement. They do not verify
browser gestures or canvas rendering.

Then start the application and verify `/api/health`. A stale index is rejected
automatically; use `POST /api/reindex` or perform the first search to rebuild it.

For repeatable evidence and integration checks:

```powershell
.\.venv\Scripts\python.exe -m evaluation.audit_evidence
.\.venv\Scripts\python.exe -m evaluation.compare_category_routing
.\.venv\Scripts\python.exe -m tools.smoke_local_app
```

The evidence audit checks saved results and byte-level split overlap without
inference. The routing comparison freshly encodes validation/test queries
against the existing index. The HTTP smoke check requires a running server and
the local composite fixture; successful searches append normal local telemetry.
It does not verify browser gestures. See `docs/DEFENSE_READINESS_AR.md` for the
remaining browser checks and the discussion preparation checklist.

## Experimental safe-crop catalog

The full-catalog safe-crop experiment is isolated from the production catalog
and index. It uses per-image SHA-256 records for resumability, builds a separate
FAISS index, selects any hybrid weight on validation only, and reports a paired
held-out comparison with bootstrap confidence intervals and an exact McNemar
test. See `docs/SAFE_CROP_CATALOG_EXPERIMENT_AR.md` for the commands and the
decision limits. The experiment does not authorize a production switch without
exact-product or real-user evidence.
