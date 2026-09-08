from pathlib import Path
from io import BytesIO
import base64

import numpy as np
import torch
from PIL import Image
from transformers import Sam2Model, Sam2Processor


# =========================================================
# PATHS
# =========================================================

ROOT = Path(__file__).resolve().parent.parent

MODEL_PATH = (
    ROOT
    / "models"
    / "sam2_base_plus"
)


# =========================================================
# SEGMENTER
# =========================================================

class Segmenter:

    def __init__(self):

        # -------------------------------------------------
        # DEVICE
        # -------------------------------------------------

        self.device = (
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        )

        print(
            f"SAM2 using device: {self.device}"
        )

        print(
            f"SAM2 model: {MODEL_PATH}"
        )


        # -------------------------------------------------
        # PROCESSOR
        # -------------------------------------------------

        self.processor = (
            Sam2Processor.from_pretrained(
                MODEL_PATH,
                local_files_only=True
            )
        )


        # -------------------------------------------------
        # MODEL
        # -------------------------------------------------

        self.model = (
            Sam2Model.from_pretrained(
                MODEL_PATH,
                local_files_only=True
            )
            .to(self.device)
        )

        self.model.eval()


    # =====================================================
    # SEGMENT IMAGE
    # =====================================================

    def segment(
        self,
        image: Image.Image,
        points: list,
        labels: list
    ):

        # -------------------------------------------------
        # IMAGE
        # -------------------------------------------------

        image = image.convert("RGB")


        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------

        if not points:

            raise ValueError(
                "At least one selection point is required."
            )


        if len(points) != len(labels):

            raise ValueError(
                "Points and labels count must match."
            )


        cleaned_points = []
        cleaned_labels = []


        for point, label in zip(
            points,
            labels
        ):

            if (
                not isinstance(point, list)
                or len(point) != 2
            ):

                raise ValueError(
                    "Each point must contain [x, y]."
                )


            x = float(point[0])
            y = float(point[1])


            # Prevent coordinates outside the image
            x = max(
                0.0,
                min(
                    x,
                    float(image.width - 1)
                )
            )

            y = max(
                0.0,
                min(
                    y,
                    float(image.height - 1)
                )
            )


            label = int(label)


            if label not in (0, 1):

                raise ValueError(
                    "AI point labels must be 0 or 1."
                )


            cleaned_points.append(
                [x, y]
            )

            cleaned_labels.append(
                label
            )


        # -------------------------------------------------
        # SAM2 INPUT FORMAT
        #
        # Batch
        #   └── Object
        #       └── Points
        #           └── [x, y]
        # -------------------------------------------------

        input_points = [
            [
                cleaned_points
            ]
        ]


        input_labels = [
            [
                cleaned_labels
            ]
        ]


        # -------------------------------------------------
        # PROCESS INPUT
        # -------------------------------------------------

        inputs = self.processor(
            images=image,
            input_points=input_points,
            input_labels=input_labels,
            return_tensors="pt"
        )


        # Keep original size before moving tensors to GPU
        original_sizes = (
            inputs["original_sizes"]
            .clone()
            .cpu()
        )


        inputs = inputs.to(
            self.device
        )


        # -------------------------------------------------
        # RUN SAM2
        # -------------------------------------------------

        with torch.inference_mode():

            outputs = self.model(
                **inputs,
                multimask_output=True
            )


        # -------------------------------------------------
        # RESTORE MASKS TO ORIGINAL IMAGE SIZE
        # -------------------------------------------------

        masks = (
            self.processor
            .post_process_masks(
                outputs.pred_masks.cpu(),
                original_sizes
            )[0]
        )


        # -------------------------------------------------
        # BEST MASK
        # -------------------------------------------------

        scores = (
            outputs.iou_scores[
                0,
                0
            ]
            .detach()
            .cpu()
        )


        best_index = int(
            torch.argmax(
                scores
            ).item()
        )


        best_score = float(
            scores[
                best_index
            ].item()
        )


        mask = (
            masks[
                0,
                best_index
            ]
            .cpu()
            .numpy()
            .astype(bool)
        )


        # -------------------------------------------------
        # VALID MASK
        # -------------------------------------------------

        ys, xs = np.where(
            mask
        )


        if len(xs) == 0:

            raise RuntimeError(
                "SAM2 could not detect the selected object."
            )


        # -------------------------------------------------
        # BOUNDING BOX
        # -------------------------------------------------

        x1 = int(
            xs.min()
        )

        y1 = int(
            ys.min()
        )

        x2 = int(
            xs.max()
        ) + 1

        y2 = int(
            ys.max()
        ) + 1


        # -------------------------------------------------
        # ORIGINAL IMAGE ARRAY
        # -------------------------------------------------

        image_array = np.array(
            image
        )


        cropped_image = (
            image_array[
                y1:y2,
                x1:x2
            ]
        )


        cropped_mask = (
            mask[
                y1:y2,
                x1:x2
            ]
        )


        # -------------------------------------------------
        # CREATE CUTOUT
        #
        # Product stays visible.
        # Everything outside mask becomes white.
        # -------------------------------------------------

        cutout_array = (
            np.ones_like(
                cropped_image
            )
            * 255
        )


        cutout_array[
            cropped_mask
        ] = (
            cropped_image[
                cropped_mask
            ]
        )


        cutout = Image.fromarray(
            cutout_array
        )


        # -------------------------------------------------
        # CREATE GREEN TRANSPARENT OVERLAY
        # -------------------------------------------------

        overlay_array = np.zeros(
            (
                image.height,
                image.width,
                4
            ),
            dtype=np.uint8
        )


        overlay_array[
            mask
        ] = [
            0,      # Red
            255,    # Green
            80,     # Blue
            105     # Alpha
        ]


        overlay = Image.fromarray(
            overlay_array
        )


        # -------------------------------------------------
        # RESULT
        # -------------------------------------------------

        return {

            "overlay":
                self._image_to_base64(
                    overlay
                ),

            "cutout":
                self._image_to_base64(
                    cutout
                ),

            "bbox": {

                "x":
                    x1,

                "y":
                    y1,

                "width":
                    x2 - x1,

                "height":
                    y2 - y1
            },

            "score":
                best_score,

            "positive_points":
                cleaned_labels.count(1),

            "negative_points":
                cleaned_labels.count(0)
        }


    # =====================================================
    # PIL IMAGE → BASE64
    # =====================================================

    @staticmethod
    def _image_to_base64(
        image: Image.Image
    ):

        buffer = BytesIO()


        image.save(
            buffer,
            format="PNG"
        )


        return (
            base64
            .b64encode(
                buffer.getvalue()
            )
            .decode("utf-8")
        )