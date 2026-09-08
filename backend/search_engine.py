from pathlib import Path
import json

import faiss
import numpy as np
import torch

from PIL import Image
from transformers import CLIPModel, CLIPProcessor


ROOT = Path(__file__).resolve().parent.parent

MODEL_PATH = ROOT / "models" / "clip_vit_b32"
CATALOG_PATH = ROOT / "catalog"
DATA_PATH = ROOT / "data"

INDEX_PATH = DATA_PATH / "catalog.faiss"
PATHS_PATH = DATA_PATH / "catalog_paths.json"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


class SearchEngine:

    def __init__(self):

        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        print(f"Using device: {self.device}")

        self.model = CLIPModel.from_pretrained(
            MODEL_PATH,
            local_files_only=True
        ).to(self.device)

        self.processor = CLIPProcessor.from_pretrained(
            MODEL_PATH,
            local_files_only=True
        )

        self.model.eval()

        self.index = None
        self.image_paths = []

        DATA_PATH.mkdir(exist_ok=True)

        self.load_index()

    def encode_image(self, image: Image.Image):

        image = image.convert("RGB")

        inputs = self.processor(
            images=image,
            return_tensors="pt"
        )

        pixel_values = inputs["pixel_values"].to(self.device)

        with torch.inference_mode():
            outputs = self.model.get_image_features(
                pixel_values=pixel_values
            )

            features = outputs.pooler_output

        features = features / features.norm(
            dim=-1,
            keepdim=True
        )

        return features.cpu().numpy().astype("float32")


    def build_index(self):

        files = [
            p for p in CATALOG_PATH.rglob("*")
            if p.is_file()
            and p.suffix.lower() in IMAGE_EXTENSIONS
        ]

        if not files:
            raise RuntimeError(
                "No images found inside catalog folder."
            )

        vectors = []
        valid_paths = []

        print(f"Indexing {len(files)} images...")

        for number, path in enumerate(files, start=1):

            try:

                image = Image.open(path)

                vector = self.encode_image(image)

                vectors.append(vector)

                relative_path = path.relative_to(
                    CATALOG_PATH
                ).as_posix()

                valid_paths.append(relative_path)

                print(
                    f"[{number}/{len(files)}] {relative_path}"
                )

            except Exception as error:

                print(
                    f"Skipped {path.name}: {error}"
                )

        if not vectors:
            raise RuntimeError(
                "Could not index any catalog images."
            )

        matrix = np.vstack(vectors)

        faiss.normalize_L2(matrix)

        index = faiss.IndexFlatIP(
            matrix.shape[1]
        )

        index.add(matrix)

        faiss.write_index(
            index,
            str(INDEX_PATH)
        )

        with open(
            PATHS_PATH,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                valid_paths,
                file,
                ensure_ascii=False,
                indent=2
            )

        self.index = index
        self.image_paths = valid_paths

        return len(valid_paths)


    def load_index(self):

        if (
            INDEX_PATH.exists()
            and PATHS_PATH.exists()
        ):

            self.index = faiss.read_index(
                str(INDEX_PATH)
            )

            with open(
                PATHS_PATH,
                "r",
                encoding="utf-8"
            ) as file:

                self.image_paths = json.load(file)


    def search(self, image, top_k=8):

        if self.index is None:
            raise RuntimeError(
                "Catalog index does not exist yet."
            )

        query = self.encode_image(image)

        faiss.normalize_L2(query)

        k = min(
            top_k,
            len(self.image_paths)
        )

        scores, ids = self.index.search(
            query,
            k
        )

        results = []

        for score, idx in zip(
            scores[0],
            ids[0]
        ):

            if idx < 0:
                continue

            path = self.image_paths[idx]

            results.append(
                {
                    "image": path,
                    "score": float(score)
                }
            )

        return results