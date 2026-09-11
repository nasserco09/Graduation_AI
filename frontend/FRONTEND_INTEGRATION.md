# Frontend ↔ AI Backend Integration

This frontend is configured for the tested same-origin FastAPI contract:

- `POST /api/segment`
  - multipart: `image`, `x`, `y`
  - response: `{ "mask": "<base64 png>", "cutout": "<base64 png>", "score": 0.0-1.0 }`
- `POST /api/search?top_k=N`
  - multipart: `image`
  - response: `{ "results": [{ "url": "...", "score": 0.0-1.0 }] }`
- `POST /api/reindex` (backend/admin endpoint; not exposed in the public UI)

## Search flow

1. Upload/capture/paste an image.
2. Choose **Full image** or **AI product selection**.
3. In AI mode, click the target product. SAM2 returns a mask and cutout.
4. Review and accept the selected cutout.
5. The accepted cutout (or the original full image) is sent to `/api/search`.
6. Backend results are normalized to the existing result-card UI.

## Serving

The API paths are relative (`/api/...`) by design. Serve this frontend from the same origin as the FastAPI application (recommended), or configure a reverse proxy so `/api/*` reaches FastAPI.

Do not open `index.html` directly with `file://` when testing API integration.
