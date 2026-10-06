from pathlib import Path
from typing import List

import numpy as np
import torch
import torch.nn.functional as F
import timm

from PIL import Image
from safetensors.torch import load_file
from timm.data import resolve_model_data_config, create_transform
from transformers import (
    CLIPModel,
    CLIPProcessor,
    AutoModel,
    AutoProcessor,
)


ROOT = Path(__file__).resolve().parent.parent
MODELS_ROOT = ROOT / "models"


def open_image(path: Path) -> Image.Image:
    return Image.open(path).convert("RGB")


def normalize_numpy(array: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(
        array,
        axis=1,
        keepdims=True
    )

    norms[norms == 0] = 1.0

    return (
        array / norms
    ).astype("float32")


class BaseAdapter:

    name = "base"

    def __init__(self):

        self.device = (
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )

        self.model = None

    def encode_paths(
        self,
        paths: List[Path],
        batch_size: int = 16
    ) -> np.ndarray:

        raise NotImplementedError

    def cleanup(self):

        if self.model is not None:
            del self.model

        if torch.cuda.is_available():
            torch.cuda.empty_cache()


class CLIPAdapter(BaseAdapter):

    name = "clip"

    def __init__(self):

        super().__init__()

        model_path = (
            MODELS_ROOT
            / "clip_vit_b32"
        )

        print(
            f"[CLIP] Loading from {model_path}"
        )

        self.processor = (
            CLIPProcessor.from_pretrained(
                model_path,
                local_files_only=True
            )
        )

        self.model = (
            CLIPModel.from_pretrained(
                model_path,
                local_files_only=True
            )
            .to(self.device)
            .eval()
        )

    def encode_paths(
        self,
        paths,
        batch_size=16
    ):

        vectors = []

        for start in range(
            0,
            len(paths),
            batch_size
        ):

            batch_paths = paths[
                start:start + batch_size
            ]

            images = [
                open_image(path)
                for path in batch_paths
            ]

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

                # New Transformers versions may
                # return BaseModelOutputWithPooling.
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

            vectors.append(
                features
                .cpu()
                .numpy()
                .astype("float32")
            )

        return np.vstack(vectors)


class SigLIP2Adapter(BaseAdapter):

    name = "siglip2"

    def __init__(self):

        super().__init__()

        model_path = (
            MODELS_ROOT
            / "siglip2_base"
        )

        print(
            f"[SigLIP2] Loading from {model_path}"
        )

        self.processor = (
            AutoProcessor.from_pretrained(
                model_path,
                local_files_only=True
            )
        )

        self.model = (
            AutoModel.from_pretrained(
                model_path,
                local_files_only=True
            )
            .to(self.device)
            .eval()
        )

    def encode_paths(
        self,
        paths,
        batch_size=8,
        image_transform=None,
    ):

        vectors = []

        for start in range(
            0,
            len(paths),
            batch_size
        ):

            batch_paths = paths[
                start:start + batch_size
            ]

            images = [
                open_image(path)
                for path in batch_paths
            ]

            if image_transform is not None:
                images = [
                    image_transform(image)
                    for image in images
                ]

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

            vectors.append(
                features
                .cpu()
                .numpy()
                .astype("float32")
            )

        return np.vstack(vectors)


class TimmAdapter(BaseAdapter):

    def __init__(
        self,
        name: str,
        timm_name: str,
        weights_folder: str,
        batch_size: int = 16
    ):

        super().__init__()

        self.name = name
        self.default_batch_size = batch_size

        weights_path = (
            MODELS_ROOT
            / weights_folder
            / "model.safetensors"
        )

        print(
            f"[{name}] Loading {timm_name}"
        )

        print(
            f"[{name}] Weights: {weights_path}"
        )

        self.model = timm.create_model(
            timm_name,
            pretrained=False,
            num_classes=0
        )

        state_dict = load_file(
            str(weights_path)
        )

        missing, unexpected = (
            self.model.load_state_dict(
                state_dict,
                strict=False
            )
        )

        # Classification-head mismatches are expected
        # because num_classes=0 gives embeddings only.
        if missing:
            print(
                f"[{name}] Missing keys: "
                f"{len(missing)}"
            )

        if unexpected:
            print(
                f"[{name}] Unexpected keys: "
                f"{len(unexpected)}"
            )

        self.model = (
            self.model
            .to(self.device)
            .eval()
        )

        data_config = (
            resolve_model_data_config(
                self.model
            )
        )

        self.transform = create_transform(
            **data_config,
            is_training=False
        )

    def encode_paths(
        self,
        paths,
        batch_size=None
    ):

        if batch_size is None:
            batch_size = (
                self.default_batch_size
            )

        vectors = []

        for start in range(
            0,
            len(paths),
            batch_size
        ):

            batch_paths = paths[
                start:start + batch_size
            ]

            tensors = [
                self.transform(
                    open_image(path)
                )
                for path in batch_paths
            ]

            batch = (
                torch.stack(tensors)
                .to(self.device)
            )

            with torch.inference_mode():

                features = self.model(
                    batch
                )

                if features.ndim > 2:

                    features = (
                        features.flatten(
                            start_dim=2
                        )
                        .mean(dim=-1)
                    )

                features = F.normalize(
                    features,
                    dim=-1
                )

            vectors.append(
                features
                .cpu()
                .numpy()
                .astype("float32")
            )

        return np.vstack(vectors)


def create_adapter(
    model_name: str
):

    if model_name == "clip":

        return CLIPAdapter()

    if model_name == "siglip2":

        return SigLIP2Adapter()

    if model_name == "dinov2":

        return TimmAdapter(
            name="dinov2",
            timm_name=(
                "vit_small_patch14_dinov2.lvd142m"
            ),
            weights_folder="dinov2_small",
            batch_size=16
        )

    if model_name == "resnet50":

        return TimmAdapter(
            name="resnet50",
            timm_name="resnet50.a1_in1k",
            weights_folder="resnet50",
            batch_size=32
        )

    if model_name == "efficientnet_b3":

        return TimmAdapter(
            name="efficientnet_b3",
            timm_name=(
                "efficientnet_b3.ra2_in1k"
            ),
            weights_folder=(
                "efficientnet_b3"
            ),
            batch_size=24
        )

    raise ValueError(
        f"Unknown model: {model_name}"
    )
