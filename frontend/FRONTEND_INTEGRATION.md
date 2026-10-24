# Frontend ↔ Backend integration

The frontend and FastAPI application use same-origin relative URLs. Run the
application and open `http://127.0.0.1:8000`; do not open `index.html` through
`file://`.

## Current API contract

### `POST /api/segment`

Multipart fields:

- `image`: JPEG, PNG, WebP, or BMP, at most 8 MB and 25 million pixels.
- `points`: JSON array such as `[[120, 80], [30, 40]]`.
- `labels`: JSON array containing `1` for inclusion and `0` for exclusion.
- A maximum of 50 points is accepted.

The response includes `overlay`, `cutout`, `score`, `bbox`, and point counts.
Both image values are raw base64 PNG strings. The frontend adds the
`data:image/png;base64,` prefix when displaying them.

### `POST /api/search?top_k=N`

Multipart fields:

- `image`: the full image or the already-selected crop/cutout.
- `search_mode`: `full`, `ai`, `rect`, `poly`, or `free`.
- `category`: `auto`, `all`, or one of the keys returned by
  `GET /api/categories`.

`top_k` is a query parameter from 1 to 50. The response contains `results`
and a `query` object with the search ID, measured latency, category-routing
decision, SHA-256 verification value, and preprocessing metadata.

### Feedback and diagnostics

- `POST /api/feedback`: save `correct`, `no_match`, or `wrong_category`
  feedback for a returned `search_id`.
- `GET /api/health`: model devices, index readiness, and version information.
- `GET /api/categories`: supported category keys and Arabic labels.
- `GET /api/catalog/validation`: catalog-metadata consistency check.
- `GET /api/monitoring/summary`: aggregate search and feedback measurements.
- `GET /api/monitoring/failures`: failed cases without query image/hash data.
- `POST /api/reindex`: rebuild the catalog index; this is an administrative
  endpoint and is intentionally not exposed in the public UI.

Monitoring and all
`/api/demo-catalog/products` routes require the administrator session cookie.
Unsafe administration requests also require `X-CSRF-Token` from the
authenticated `/api/auth/session` response. Private pages use
`js/admin-session.js` to attach it and redirect expired sessions to login.
`/api/auth/setup` is a one-time local setup, `/api/auth/login` signs in,
`/api/auth/logout` revokes the session, and `/api/auth/password` changes the
password after verification and revokes all sessions. Search, segmentation,
feedback, health, categories, catalog validation and result images stay public.

## Search flow

1. Upload, capture, paste, or choose a local catalog sample.
2. Search the full image, use SAM2 points, or make a manual selection.
3. Review the exact query preview before searching.
4. Choose automatic, unrestricted, or explicit category routing.
5. Send the prepared image to `/api/search`.
6. Review ordered results and optionally record correctness feedback.

The similarity percentage is a display of cosine similarity. It is not a
probability and does not guarantee that the returned item is the same product.
