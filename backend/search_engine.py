from pathlib import Path
import hashlib
import json
import threading

import faiss
import numpy as np
import torch
import torch.nn.functional as F

from PIL import Image
from transformers import AutoModel, AutoProcessor

from backend.category_routing import (
    CATEGORY_LABELS,
    normalize_category,
    predict_category,
)
from backend.catalog_config import (
    CATALOG_DIR,
    CATALOG_METADATA_FILE,
    DATA_DIR,
    ROOT,
)
from backend.catalog_metadata import CatalogMetadata, METADATA_SCHEMA_VERSION
from backend.image_preprocessing import PREPROCESSING_VERSION, preprocess_image


# ============================================================
# PATHS
# ============================================================

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

        self.catalog_metadata = CatalogMetadata(
            CATALOG_METADATA_FILE
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
        self.catalog_vectors = None
        self._index_lock = threading.RLock()

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
                self.catalog_vectors = None

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

        prepared_images = [
            preprocess_image(image)[0]
            for image in images
        ]

        inputs = self.processor(
            images=prepared_images,
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

    def validate_catalog_metadata(self):
        catalog_paths = self._get_catalog_images()
        relative_paths = [
            path.relative_to(CATALOG_DIR).as_posix()
            for path in catalog_paths
        ]
        self.catalog_metadata.reload()
        summary = self.catalog_metadata.validate_catalog_paths(relative_paths)
        summary["metadata_checksum"] = self.catalog_metadata.checksum()
        return summary

    def _catalog_checksum(self, paths):
        digest = hashlib.sha256()
        for path in paths:
            relative_path = path.relative_to(CATALOG_DIR).as_posix()
            digest.update(relative_path.encode("utf-8"))
            with path.open("rb") as image_file:
                for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
                    digest.update(chunk)
        digest.update(self.catalog_metadata.checksum().encode("ascii"))
        return digest.hexdigest()

    # ========================================================
    # BUILD FAISS INDEX
    # ========================================================

    def build_index(self):
        """Build and persist an index while blocking concurrent searches."""
        with self._index_lock:
            return self._build_index_unlocked()

    def _build_index_unlocked(
        self
    ):

        catalog_paths = (
            self._get_catalog_images()
        )

        relative_catalog_paths = [
            path.relative_to(CATALOG_DIR).as_posix()
            for path in catalog_paths
        ]
        self.catalog_metadata.reload()
        self.catalog_metadata.require_valid_catalog(relative_catalog_paths)

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
                        image.copy()
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

        new_index = faiss.IndexFlatIP(
            dimension
        )

        new_index.add(
            embeddings
        )

        # Store paths relative to catalog/
        new_image_paths = [
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

        temporary_index = INDEX_FILE.with_name(INDEX_FILE.name + ".tmp")
        temporary_paths = PATHS_FILE.with_name(PATHS_FILE.name + ".tmp")

        # ----------------------------------------------------
        # Save image mapping
        # ----------------------------------------------------

        mapping = {
            "model": "siglip2_base",

            "embedding_dimension": dimension,

            "preprocessing_version": PREPROCESSING_VERSION,

            "metadata_schema_version": METADATA_SCHEMA_VERSION,

            "catalog_checksum": self._catalog_checksum(catalog_paths),

            "image_count": len(new_image_paths),

            "paths": new_image_paths,
        }

        try:
            faiss.write_index(new_index, str(temporary_index))
            with temporary_paths.open("w", encoding="utf-8") as file:
                json.dump(mapping, file, indent=2)
                file.flush()

            temporary_index.replace(INDEX_FILE)
            temporary_paths.replace(PATHS_FILE)
        finally:
            temporary_index.unlink(missing_ok=True)
            temporary_paths.unlink(missing_ok=True)

        self.index = new_index
        self.image_paths = new_image_paths
        self.catalog_vectors = embeddings

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
            raise ValueError(
                "The saved index uses the legacy mapping format "
                "and must be rebuilt."
            )

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

            preprocessing_version = data.get(
                "preprocessing_version"
            )

            if preprocessing_version != PREPROCESSING_VERSION:

                raise ValueError(
                    "The saved index uses a different image "
                    "preprocessing version and must be rebuilt."
                )

            catalog_paths = self._get_catalog_images()
            relative_catalog_paths = [
                path.relative_to(CATALOG_DIR).as_posix()
                for path in catalog_paths
            ]
            self.catalog_metadata.reload()
            self.catalog_metadata.require_valid_catalog(relative_catalog_paths)

            if data.get("metadata_schema_version") != METADATA_SCHEMA_VERSION:
                raise ValueError(
                    "The saved index uses a different catalog metadata "
                    "schema and must be rebuilt."
                )

            expected_checksum = self._catalog_checksum(catalog_paths)
            if data.get("catalog_checksum") != expected_checksum:
                raise ValueError(
                    "The catalog changed after the index was built "
                    "and the index must be rebuilt."
                )

            saved_paths = data.get("paths")
            if (
                not isinstance(saved_paths, list)
                or not all(isinstance(path, str) for path in saved_paths)
            ):
                raise ValueError("The saved index path mapping is invalid.")
            if data.get("image_count") != len(saved_paths):
                raise ValueError("The saved index image count is invalid.")
            if data.get("embedding_dimension") != self.index.d:
                raise ValueError("The saved index embedding dimension is invalid.")

            self.image_paths = saved_paths

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

        self.catalog_vectors = np.asarray(
            self.index.reconstruct_n(0, self.index.ntotal),
            dtype="float32",
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
        top_k: int = 8,
        category: str = "auto",
        return_metadata: bool = False,
    ):

        with self._index_lock:
            if self.index is None:
                self._build_index_unlocked()

            return self._search_unlocked(
                image,
                top_k=top_k,
                category=category,
                return_metadata=return_metadata,
            )

    def _search_unlocked(
        self,
        image: Image.Image,
        top_k: int = 8,
        category: str = "auto",
        return_metadata: bool = False,
    ):
        if not self.image_paths:

            raise RuntimeError(
                "Catalog image mapping "
                "is empty."
            )

        if top_k < 1:

            raise ValueError(
                "top_k must be at least 1."
            )

        requested_category = normalize_category(category)

        query_vector = (
            self.encode_image(
                image
            )
        )

        if self.catalog_vectors is None:
            self.catalog_vectors = np.asarray(
                self.index.reconstruct_n(0, self.index.ntotal),
                dtype="float32",
            )
        catalog_vectors = self.catalog_vectors
        prediction = predict_category(
            query_vector,
            catalog_vectors,
            self.image_paths,
            category_keys=[
                self.catalog_metadata.get(path)["category_key"]
                for path in self.image_paths
            ],
        )

        if requested_category == "auto":
            applied_category = prediction["category"]
        elif requested_category == "all":
            applied_category = None
        else:
            applied_category = requested_category

        available_categories = {
            self.catalog_metadata.get(path)["category_key"]
            for path in self.image_paths
        }
        if applied_category and applied_category not in available_categories:
            raise ValueError(
                "The selected category has no images in the current catalog."
            )

        top_k = min(
            top_k,
            self.index.ntotal
        )

        scores, indices = (
            self.index.search(
                query_vector,
                self.index.ntotal
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

            item_metadata = self.catalog_metadata.get(image_path)
            result_category = item_metadata["category_key"]
            if applied_category and result_category != applied_category:
                continue

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

                    "category_key":
                        result_category,

                    "category":
                        item_metadata["category"],

                    "product_id":
                        item_metadata["product_id"],

                    "title":
                        item_metadata["title_ar"],

                    "source_dataset":
                        item_metadata["source_dataset"],
                }
            )

            if len(results) >= top_k:
                break

        routing = {
            "requested_category": requested_category,
            "predicted_category": prediction["category"],
            "predicted_label": prediction["label"],
            "confidence": prediction["confidence"],
            "margin": prediction["margin"],
            "applied_category": applied_category,
            "applied_label": CATEGORY_LABELS.get(applied_category),
            "method": "catalog_embedding_centroids",
        }

        if return_metadata:
            return results, routing
        return results
