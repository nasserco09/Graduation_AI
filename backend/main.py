from pathlib import Path
import hashlib
import json
import time
import os

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
)

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.category_routing import CATEGORY_LABELS
from backend.catalog_config import CATALOG_DIR, CATALOG_SOURCE
from backend.catalog_metadata import METADATA_SCHEMA_VERSION
from backend.image_preprocessing import PREPROCESSING_VERSION, preprocess_image
from backend.request_validation import MAX_IMAGE_BYTES, validate_image_bytes
from backend.admin_auth import install_admin_security
from backend.demo_catalog_api import create_demo_catalog_router
from backend.product_grouping import ReviewedProductGroups
from backend.search_engine import SearchEngine
from backend.search_observability import SearchObservability
from backend.segmenter import Segmenter


# =========================================================
# PATHS
# =========================================================

ROOT = Path(__file__).resolve().parent.parent

FRONTEND = ROOT / "frontend"
CATALOG = CATALOG_DIR
DATA = ROOT / "data"


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="Graduation AI Visual Search"
)

admin_auth = install_admin_security(
    app, Path(os.getenv('GRADUATION_AI_AUTH_DB', str(DATA / 'admin_auth.db'))), FRONTEND
)


# =========================================================
# SERVICES
# =========================================================

engine = SearchEngine()

reviewed_group_file = os.getenv("GRADUATION_AI_REVIEWED_GROUPS")
reviewed_groups = (
    ReviewedProductGroups.load(reviewed_group_file, engine.catalog_metadata.items, CATALOG)
    if reviewed_group_file else ReviewedProductGroups()
)

app.include_router(create_demo_catalog_router(engine, DATA / "demo_store" / "catalog.db"))

segmenter = Segmenter()

observability = SearchObservability(
    DATA / "search_observability.db"
)


class FeedbackPayload(BaseModel):
    search_id: str
    verdict: str
    selected_product_id: str | None = None
    corrected_category: str | None = None
    notes: str | None = None


# =========================================================
# STATIC FILES
# =========================================================

app.mount(
    "/catalog",
    StaticFiles(
        directory=CATALOG
    ),
    name="catalog"
)


# =========================================================
# HOME
# =========================================================

@app.get("/")
def home():

    return FileResponse(
        FRONTEND / "index.html"
    )


# =========================================================
# HEALTH CHECK
# =========================================================

@app.get("/api/health")
def health():

    return {
        "status": "ok",
        "reviewed_product_groups": len(reviewed_groups.groups),
        "search_device": engine.device,
        "segmentation_device": segmenter.device,
        "index_ready": engine.index is not None,
        "preprocessing_version": PREPROCESSING_VERSION,
        "catalog_metadata_version": METADATA_SCHEMA_VERSION,
        "catalog_source": CATALOG_SOURCE,
        "indexed_images": len(
            engine.image_paths
        )
    }


@app.get("/api/categories")
def categories():
    return {
        "categories": [
            {"key": key, "label": label}
            for key, label in CATEGORY_LABELS.items()
        ]
    }


@app.get("/api/catalog/validation")
def catalog_validation():
    try:
        return engine.validate_catalog_metadata()
    except Exception as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


@app.post("/api/feedback")
def save_feedback(payload: FeedbackPayload):
    try:
        return observability.record_feedback(
            search_id=payload.search_id,
            verdict=payload.verdict,
            selected_product_id=payload.selected_product_id,
            corrected_category=payload.corrected_category,
            notes=payload.notes,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.get("/api/monitoring/summary")
def monitoring_summary():
    return observability.summary()


@app.get("/api/monitoring/failures")
def monitoring_failures(limit: int = 100):
    return {
        "failures": observability.failure_cases(limit=limit)
    }


# =========================================================
# BUILD / REFRESH CATALOG INDEX
# =========================================================

@app.post("/api/reindex")
def reindex():

    try:

        count = engine.build_index()

        return {
            "status": "success",
            "indexed_images": count
        }

    except Exception as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


# =========================================================
# AI SEGMENTATION
# =========================================================

@app.post("/api/segment")
async def segment_product(
    image: UploadFile = File(...),
    points: str = Form(...),
    labels: str = Form(...)
):

    try:

        content = await image.read(MAX_IMAGE_BYTES + 1)
        pil_image = validate_image_bytes(content, image.content_type)


        parsed_points = json.loads(
            points
        )

        parsed_labels = json.loads(
            labels
        )


        if not isinstance(
            parsed_points,
            list
        ):

            raise ValueError(
                "Points must be a list."
            )


        if not isinstance(
            parsed_labels,
            list
        ):

            raise ValueError(
                "Labels must be a list."
            )


        if len(parsed_points) == 0:

            raise ValueError(
                "At least one AI selection point is required."
            )

        if len(parsed_points) > 50:
            raise ValueError("No more than 50 AI selection points are allowed.")


        if len(parsed_points) != len(
            parsed_labels
        ):

            raise ValueError(
                "Points and labels count must match."
            )


        result = segmenter.segment(
            pil_image,
            parsed_points,
            parsed_labels
        )


        return result


    except Exception as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


# =========================================================
# VISUAL SEARCH
# =========================================================

@app.post("/api/search")
async def search(
    image: UploadFile = File(...),
    search_mode: str = Form("full"),
    category: str = Form("auto"),
    top_k: int = 8,
    group_products: bool = False
):

    try:

        request_started = time.perf_counter()

        if not 1 <= top_k <= 50:
            raise ValueError("top_k must be between 1 and 50.")

        if group_products and not reviewed_groups.groups:
            raise ValueError("Reviewed product grouping is not configured.")

        content = await image.read(MAX_IMAGE_BYTES + 1)
        query_sha256 = hashlib.sha256(content).hexdigest()

        allowed_modes = {"full", "ai", "rect", "poly", "free"}
        if search_mode not in allowed_modes:
            raise ValueError("Unsupported search mode.")

        pil_image = validate_image_bytes(content, image.content_type)

        prepared_image, preprocessing = preprocess_image(pil_image)


        results, category_routing = engine.search(
            prepared_image,
            len(engine.image_paths) if group_products else top_k,
            category=category,
            return_metadata=True,
        )


        if group_products:
            results = reviewed_groups.select(results, top_k)

        for result in results:

            result["url"] = (
                "/catalog/"
                + result["image"]
            )

        latency_ms = round(
            (time.perf_counter() - request_started) * 1000,
            3,
        )
        search_id = None
        logging_warning = None
        try:
            search_id = observability.record_search(
                query_sha256=query_sha256,
                search_mode=search_mode,
                routing=dict(category_routing, reviewed_grouping_applied=group_products),
                top_k=top_k,
                results=results,
                latency_ms=latency_ms,
                model_name="SigLIP2",
                preprocessing_version=PREPROCESSING_VERSION,
            )
        except Exception as logging_error:
            logging_warning = f"Search completed but monitoring failed: {logging_error}"


        return {
            "results": results,
            "query": {
                "sha256": query_sha256,
                "search_id": search_id,
                "latency_ms": latency_ms,
                "monitoring_warning": logging_warning,
                "file_name": image.filename,
                "content_type": image.content_type,
                "byte_size": len(content),
                "search_mode": search_mode,
                "category_routing": category_routing,
                "reviewed_grouping_applied": group_products,
                "preprocessing": preprocessing.as_dict(),
            }
        }


    except Exception as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )


@app.get('/demo-catalog.html')
def demo_catalog_page():
    return FileResponse(FRONTEND / 'demo-catalog.html')
