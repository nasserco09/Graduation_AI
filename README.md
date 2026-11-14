# Graduation_AI

Hybrid AI-based visual search prototype for a graduation project.

The system allows users to upload an image of a fashion product, optionally select the target object manually or with AI assistance, and search for visually similar products from a local catalog.

The local presentation release is **v1.2.0-rc.9** on `feature/frontend-v2`.
Launch it with `Start_Demo.cmd` or the existing desktop shortcut at
`http://127.0.0.1:8000/`. See [release verification](docs/PRESENTATION_RC9_AR.md)
and [product management](docs/PRODUCT_MANAGEMENT_AR.md).
The Word and PowerPoint files under `docs/preliminary_discussion/` document the
earlier rc.7 preliminary discussion. The editable final-report project now contains
the submission report with seven chapters, two appendices, editable system/data
diagrams, linked bibliography sources and source-backed results. See the
[LaTeX editing and build guide](docs/final_report/README_AR.md),
[submission PDF](docs/final_report/preview/AI_Visual_Product_Search_Submission_2026.pdf), and
[university submission status](docs/UNIVERSITY_SUBMISSION_2026_AR.md).
The [250 x 140 cm university poster](docs/poster/README_AR.md) includes a
print-ready PDF, editable SVG and verified public GitHub QR. The final
presentation, brochure, and video are separate deliverables.
The application release tag remains `v1.2.0-rc.9`. On 14 November 2026 the team
authorized public repository access and completed the verified split-runtime upload.
The repository's default branch is `feature/frontend-v2`, which contains the
verified application and current submission materials; `main` is historical.

The locally verified Windows x86_64 runtime package targets Python 3.12.
Download all 28 parts plus the manifest and assembly tools from
[runtime-rc9-v1](https://github.com/nasserco09/Graduation_AI/releases/tag/runtime-rc9-v1).
Run `Assemble_Runtime.cmd` to rebuild and SHA-256 verify the original ZIP.
All 28 parts and five support files were published and their remote digests
verified on 14 November 2026; see [publication verification](runtime/VERIFICATION_PUBLICATION_20261114.json).
The package includes the two active models, all 3,068 gallery images, the original FAISS
index, application code and local frontend assets. Extract the assembled ZIP into a new folder,
run `Setup_Runtime.cmd`, then `Start_Demo.cmd`. Initial dependency installation
requires internet or compatible local wheels; Python and wheels are not bundled.
Personal accounts, added products and telemetry are excluded. The repository is
public and its QR link opens without signing in. See the
[runtime distribution and verification guide](docs/RUNTIME_DISTRIBUTION_AR.md).

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
- Independent added-product catalog, searchable from the main interface with the same selection tools
- Product creation, editing and deletion, with category, optional price, currency and availability
- One to five photos per product, photo replacement/removal and a selectable cover photo
- Product-name search, category/availability filters and catalog summaries in the management page
- Atomic metadata/photo updates and revision checks that reject stale saves or deletes

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

As an authenticated administrator, open `/api/monitoring/summary` for aggregate indicators, or run locally:

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

For a presentation on the current Windows machine, double-click `Start_Demo.cmd`.
It uses the existing `.venv`, opens the browser after readiness, and reuses a
ready local server. Keep its window open; press Ctrl+C there to stop a server
started by the launcher. The UI fonts and icons are bundled for offline use.
See [the local presentation guide](docs/LOCAL_PRESENTATION_AR.md) for demo images
and the walkthrough. This is not a distribution package for another computer.

Open `http://127.0.0.1:8000`. API documentation is available at
`http://127.0.0.1:8000/docs`.

`requirements.txt` is the UTF-8 exact environment snapshot. For an offline
installation, use the wheels already downloaded in `offline_wheels` together
with `requirements_offline.txt`; the CUDA-specific PyTorch packages must match
the target computer's CUDA installation.

## Verification

### Local administrator and catalog backups

Opening `/demo-catalog.html` requires the
single local administrator. First use opens `/admin-login.html` to create the
account with your own password; there are no default credentials. Visitors can
still search both catalogs and use SAM2 without an account. Administration is
checked server-side on every product-management request. Writes require a
session-bound CSRF token. Account settings support password changes and logout.

The ignored `data/admin_auth.db` stores the account and revocable sessions,
independently of products and FAISS. Local recovery uses
`python tools/admin_account.py --reset` with interactive password prompts.
See [the administrator guide](docs/ADMIN_ACCESS_AR.md).

The product manager supports a portable ZIP backup of added products, photos
and embeddings. Restore validates the archive, previews counts, checks for
intervening edits, and saves a downloadable recovery copy before replacement.
The account and original research catalog are separate. See
[the backup and recovery guide](docs/CATALOG_BACKUP_AR.md).

### Test commands

Run the dependency-light unit suite from the project root:

```powershell
python -m unittest discover -s tests -v
node --test tests/frontend_selection.test.cjs tests/frontend_demo_catalog.test.cjs tests/frontend_admin_auth.test.cjs tests/frontend_catalog_backup.test.cjs
```

The JavaScript tests require Node.js only for development and execute the actual
frontend source with a minimal DOM and controlled API responses. They cover
late SAM2 responses after reset, stale failures during a new request, and
retaining the previous selection after failed refinement. They do not verify
browser gestures or canvas rendering.

The suite also covers native Enter behavior on controls, repeated keys, open
dialogs, and the preview badge when switching selection modes. Interactive
browser checks and their limits are recorded in `docs/BROWSER_QA_AR.md`.

Then start the application and verify `/api/health`. A stale index is rejected
automatically; use authenticated `POST /api/reindex` (with CSRF) or perform the
first search to rebuild it.

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

## Uncertain-category fallback review

Six fallback policies were replayed on the 341 historical validation records,
with query/model/index hashes checked and no test records used for selection.
The best exploratory policy changed 323/341 correct categories to 324/341;
other thresholds tied or worsened the result. This does not establish a robust
improvement. Current production routing is retained. No new exact-product
accuracy is claimed. See [the comparison and limits](docs/UNCERTAIN_CATEGORY_REPLAY_AR.md).

## Reviewed identity pilot and further collection

The current dataset uses image IDs rather than merchant product IDs. Seven
previously reviewed alternate-view pairs were evaluated after removing every
query from the gallery and recomputing category centroids from gallery images
only. This small, selected development pilot is separate from aggregate search
accuracy. No new customer-photo accuracy is claimed. The collection tools record
the target product and SAM2 points before retrieval and reject byte/pixel copies
of indexed photos. See [the protocol and results](docs/SEARCH_IDENTITY_PILOT_AR.md)
and [the dataset audit](docs/DATASET_IDENTITY_AUDIT_AR.md).
