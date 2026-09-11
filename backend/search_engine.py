from pathlib import Path
import json

import faiss
import numpy as np
import torch
import torch.nn.functional as F

from PIL import Image
from transformers import AutoModel, AutoProcessor


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

CATALOG_DIR = ROOT / "catalog"
DATA_DIR = ROOT / "data"

MODEL_DIR = (
    ROOT
    / "models"
    / "siglip2_base"
)

INDEX_FILE = (
    DATA_DIR
    / "catalog_siglip2.faiss"
)

PATHS_FILE = (
    DATA_DIR
    / "catalog_siglip2_paths.json"
)


# ============================================================
# SETTINGS
# ============================================================

SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
}

BATCH_SIZE = 8


# ============================================================
# SEARCH ENGINE
# ============================================================

class SearchEngine:

    def __init__(self):

        self.device = (
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )

        print("=" * 60)
        print("VISUAL SEARCH ENGINE")
        print("=" * 60)

        print(
            f"Search model: SigLIP2"
        )

        print(
            f"Device: {self.device}"
        )

        print(
            f"Model path: {MODEL_DIR}"
        )

        if not MODEL_DIR.exists():

            raise FileNotFoundError(
                f"SigLIP2 model not found:\n"
                f"{MODEL_DIR}"
            )

        DATA_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        # ----------------------------------------------------
        # Load processor
        # ----------------------------------------------------

        self.processor = (
            AutoProcessor.from_pretrained(
                MODEL_DIR,
                local_files_only=True
            )
        )

        # ----------------------------------------------------
        # Load model
        # ----------------------------------------------------

        self.model = (
            AutoModel.from_pretrained(
                MODEL_DIR,
                local_files_only=True
            )
            .to(self.device)
            .eval()
        )

        self.index = None
        self.image_paths = []

        # ----------------------------------------------------
        # Load existing SigLIP2 index if available
        # ----------------------------------------------------

        if (
            INDEX_FILE.exists()
            and PATHS_FILE.exists()
        ):

            try:

                self.load_index()

            except Exception as error:

                print(
                    "Could not load existing "
                    "SigLIP2 index."
                )

                print(
                    f"Reason: {error}"
                )

                print(
                    "A new index will be required."
                )

                self.index = None
                self.image_paths = []

        else:

            print(
                "No SigLIP2 catalog index found."
            )

            print(
                "Use Build/Refresh Catalog "
                "from the application."
            )

    # ========================================================
    # IMAGE ENCODING
    # ========================================================

    def _encode_images(
        self,
        images
    ):

        if not images:

            raise ValueError(
                "No images were provided."
            )

        inputs = self.processor(
            images=images,
            return_tensors="pt"
        )

        pixel_values = (
            inputs["pixel_values"]
            .to(self.device)
        )

        with torch.inference_mode():

            output = (
                self.model
                .get_image_features(
                    pixel_values=pixel_values
                )
            )

            # Transformers versions may return
            # a tensor or BaseModelOutputWithPooling.
            if hasattr(
                output,
                "pooler_output"
            ):

                features = (
                    output.pooler_output
                )

            else:

                features = output

            features = F.normalize(
                features,
                dim=-1
            )

        return (
            features
            .detach()
            .cpu()
            .numpy()
            .astype("float32")
        )

    # ========================================================
    # SINGLE IMAGE
    # ========================================================

    def encode_image(
        self,
        image: Image.Image
    ):

        image = image.convert(
            "RGB"
        )

        vectors = self._encode_images(
            [image]
        )

        return vectors

    # ========================================================
    # DISCOVER CATALOG
    # ========================================================

    def _get_catalog_images(
        self
    ):

        if not CATALOG_DIR.exists():

            raise FileNotFoundError(
                f"Catalog folder not found:\n"
                f"{CATALOG_DIR}"
            )

        paths = sorted(
            [
                path
                for path
                in CATALOG_DIR.rglob("*")
                if (
                    path.is_file()
                    and
                    path.suffix.lower()
                    in SUPPORTED_EXTENSIONS
                )
            ]
        )

        if not paths:

            raise ValueError(
                "No supported images "
                "were found in catalog."
            )

        return paths

    # ========================================================
    # BUILD FAISS INDEX
    # ========================================================

    def build_index(
        self
    ):

        catalog_paths = (
            self._get_catalog_images()
        )

        print()
        print("=" * 60)
        print("BUILDING SIGLIP2 CATALOG INDEX")
        print("=" * 60)

        print(
            f"Catalog images: "
            f"{len(catalog_paths)}"
        )

        embeddings = []

        total = len(
            catalog_paths
        )

        for start in range(
            0,
            total,
            BATCH_SIZE
        ):

            end = min(
                start + BATCH_SIZE,
                total
            )

            batch_paths = (
                catalog_paths[
                    start:end
                ]
            )

            images = []

            for path in batch_paths:

                with Image.open(
                    path
                ) as image:

                    images.append(
                        image
                        .convert("RGB")
                        .copy()
                    )

            vectors = (
                self._encode_images(
                    images
                )
            )

            embeddings.append(
                vectors
            )

            print(
                f"Encoded "
                f"{end}/{total}"
            )

        embeddings = np.vstack(
            embeddings
        ).astype("float32")

        dimension = (
            embeddings.shape[1]
        )

        print(
            f"Embedding dimension: "
            f"{dimension}"
        )

        # ----------------------------------------------------
        # Cosine similarity
        #
        # Embeddings are normalized, therefore
        # inner product == cosine similarity.
        # ----------------------------------------------------

        self.index = faiss.IndexFlatIP(
            dimension
        )

        self.index.add(
            embeddings
        )

        # Store paths relative to catalog/
        self.image_paths = [
            path
            .relative_to(
                CATALOG_DIR
            )
            .as_posix()

            for path
            in catalog_paths
        ]

        # ----------------------------------------------------
        # Save FAISS index
        # ----------------------------------------------------

        faiss.write_index(
            self.index,
            str(INDEX_FILE)
        )

        # ----------------------------------------------------
        # Save image mapping
        # ----------------------------------------------------

        with open(
            PATHS_FILE,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                {
                    "model":
                        "siglip2_base",

                    "embedding_dimension":
                        dimension,

                    "image_count":
                        len(
                            self.image_paths
                        ),

                    "paths":
                        self.image_paths,
                },
                file,
                indent=2
            )

        print()
        print(
            "SigLIP2 catalog index built."
        )

        print(
            f"Indexed images: "
            f"{len(self.image_paths)}"
        )

        print(
            f"Index file: "
            f"{INDEX_FILE}"
        )

        return len(
            self.image_paths
        )

    # ========================================================
    # LOAD EXISTING INDEX
    # ========================================================

    def load_index(
        self
    ):

        print(
            "Loading existing "
            "SigLIP2 catalog index..."
        )

        self.index = (
            faiss.read_index(
                str(INDEX_FILE)
            )
        )

        with open(
            PATHS_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(
                file
            )

        if isinstance(
            data,
            list
        ):

            # Compatibility fallback
            self.image_paths = data

        else:

            model_name = data.get(
                "model"
            )

            if (
                model_name
                != "siglip2_base"
            ):

                raise ValueError(
                    "The saved index does not "
                    "belong to SigLIP2."
                )

            self.image_paths = (
                data["paths"]
            )

        if (
            self.index.ntotal
            != len(
                self.image_paths
            )
        ):

            raise ValueError(
                "FAISS index and image path "
                "mapping have different sizes."
            )

        print(
            f"Loaded "
            f"{self.index.ntotal} "
            f"catalog images."
        )

        print(
            f"Embedding dimension: "
            f"{self.index.d}"
        )

    # ========================================================
    # SEARCH
    # ========================================================

    def search(
        self,
        image: Image.Image,
        top_k: int = 8
    ):

        if self.index is None:

            raise RuntimeError(
                "Catalog index has not "
                "been built yet."
            )

        if not self.image_paths:

            raise RuntimeError(
                "Catalog image mapping "
                "is empty."
            )

        if top_k < 1:

            raise ValueError(
                "top_k must be at least 1."
            )

        query_vector = (
            self.encode_image(
                image
            )
        )

        top_k = min(
            top_k,
            self.index.ntotal
        )

        scores, indices = (
            self.index.search(
                query_vector,
                top_k
            )
        )

        results = []

        for score, index in zip(
            scores[0],
            indices[0]
        ):

            if index < 0:
                continue

            image_path = (
                self.image_paths[
                    int(index)
                ]
            )

            similarity = float(
                score
            )

            results.append(
                {
                    "image":
                        image_path,

                    "score":
                        similarity,

                    "similarity":
                        similarity,

                    "similarity_percent":
                        round(
                            similarity
                            * 100,
                            2
                        ),

                    "model":
                        "SigLIP2",
                }
            )

        return results