# Visual Search API Contract

## Search endpoint

`POST /api/search?top_k=8`

Multipart form fields:

- `image`: required PNG, JPEG, WebP, or BMP image. The server enforces an
  8 MB byte limit, a 25-million-pixel limit, and verifies the actual image.
- `search_mode`: one of `full`, `ai`, `rect`, `poly`, or `free`.
- `category`: `auto`, `all`, or a category key returned by `/api/categories`.

Successful response:

```json
{
  "results": [
    {
      "image": "shoes/example.jpg",
      "url": "/catalog/shoes/example.jpg",
      "score": 0.81,
      "similarity": 0.81,
      "similarity_percent": 81.0,
      "model": "SigLIP2",
      "product_id": "00f6e504-7c27-438e-a5d7-bc65e557bb2b",
      "title": "حذاء رقم 1",
      "category_key": "shoes",
      "category": "أحذية",
      "source_dataset": "clothing_small_catalog_sample"
    }
  ],
  "query": {
    "sha256": "...",
    "search_id": "generated-search-id",
    "latency_ms": 245.7,
    "monitoring_warning": null,
    "file_name": "query.png",
    "content_type": "image/png",
    "byte_size": 12345,
    "search_mode": "ai",
    "category_routing": {
      "requested_category": "auto",
      "predicted_category": "shoes",
      "predicted_label": "أحذية",
      "confidence": 0.84,
      "margin": 0.62,
      "applied_category": "shoes",
      "applied_label": "أحذية",
      "method": "catalog_embedding_centroids"
    },
    "preprocessing": {
      "version": "visual-search-rgb-square-v1"
    }
  }
}
```

The category confidence is relative only to categories represented in the
current catalog. It must not be described as a universal classification
accuracy measurement.

`top_k` must be between 1 and 50. Similarity is cosine similarity, not a
probability of exact product identity.

## Segmentation endpoint

`POST /api/segment`

Multipart form fields:

- `image`: subject to the same validation as the search image.
- `points`: a JSON array of `[x, y]` coordinates, with 1–50 items.
- `labels`: a same-length JSON array containing only `0` or `1`.

The response contains the mask overlay, transparent product cutout, selected
bounding box, segmentation score, and positive/negative point counts.

## Categories endpoint

`GET /api/categories`

Returns every supported category key and its Arabic display label.

## Catalog validation endpoint

`GET /api/catalog/validation`

Checks that every catalog image has one active metadata record and that every
metadata record points to an existing image. It also returns the metadata
schema version and checksum. A failed validation prevents a new index from
being built.

The default expanded catalog is `datasets/clothing_small/train` with 3,068
images. Validation and test splits are deliberately excluded from application
search to keep later evaluation independent. `/api/health` reports
`catalog_source: clothing_small_train` when the expanded catalog is active.

## Error behavior

The API returns HTTP 400 with a readable `detail` message for invalid search
modes, unsupported categories, invalid or oversized images, invalid point
prompts, missing catalog categories,
or other request-processing errors.

## Feedback endpoint

`POST /api/feedback`

JSON body fields:

- `search_id`: the anonymous identifier returned by the search response.
- `verdict`: `correct`, `no_match`, `wrong_category`, or `bad_selection`.
- `selected_product_id`: required when the verdict is `correct`.
- `corrected_category`: required when the verdict is `wrong_category`.
- `notes`: optional, with a maximum of 500 characters.

Only the latest feedback for a search is retained.

## Monitoring endpoints

- `GET /api/monitoring/summary` returns aggregate counts, feedback coverage,
  correct-match rate, average latency, search-mode counts, and predicted-category
  counts.
- `GET /api/monitoring/failures?limit=100` returns unsuccessful feedback cases
  without query hashes, raw images, or personal identity.

These prototype endpoints are intended for local research use. Authentication
must be added before exposing monitoring data on a public deployment.
