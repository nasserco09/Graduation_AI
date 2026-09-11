from io import BytesIO
from pathlib import Path
import json
from pathlib import Path

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
)

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from backend.search_engine import SearchEngine
from backend.segmenter import Segmenter


# =========================================================
# PATHS
# =========================================================

ROOT = Path(__file__).resolve().parent.parent

FRONTEND = ROOT / "frontend"
CATALOG = ROOT / "catalog"


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="Graduation AI Visual Search"
)


# =========================================================
# SERVICES
# =========================================================

engine = SearchEngine()

segmenter = Segmenter()


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
        "search_device": engine.device,
        "segmentation_device": segmenter.device,
        "indexed_images": len(
            engine.image_paths
        )
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

        content = await image.read()

        pil_image = Image.open(
            BytesIO(content)
        ).convert("RGB")


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
    top_k: int = 8
):

    try:

        content = await image.read()

        pil_image = Image.open(
            BytesIO(content)
        ).convert("RGB")


        results = engine.search(
            pil_image,
            top_k
        )


        for result in results:

            result["url"] = (
                "/catalog/"
                + result["image"]
            )


        return {
            "results": results
        }


    except Exception as error:

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )