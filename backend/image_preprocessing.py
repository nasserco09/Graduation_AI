"""Shared image preparation for catalog indexing and visual-search queries."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageOps


PREPROCESSING_VERSION = "visual-search-rgb-square-v1"
NEUTRAL_BACKGROUND = (255, 255, 255)


@dataclass(frozen=True)
class PreprocessingInfo:
    version: str
    input_width: int
    input_height: int
    output_width: int
    output_height: int
    background: str

    def as_dict(self) -> dict:
        return {
            "version": self.version,
            "input_width": self.input_width,
            "input_height": self.input_height,
            "output_width": self.output_width,
            "output_height": self.output_height,
            "background": self.background,
        }


def prepare_rgb_image(image: Image.Image) -> Image.Image:
    """Apply orientation and composite transparency before discarding alpha."""
    oriented = ImageOps.exif_transpose(image)
    if oriented.mode in {"RGBA", "LA"} or "transparency" in oriented.info:
        rgba = oriented.convert("RGBA")
        background = Image.new("RGBA", rgba.size, NEUTRAL_BACKGROUND + (255,))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return oriented.convert("RGB")


def preprocess_image(image: Image.Image) -> tuple[Image.Image, PreprocessingInfo]:
    """Return a deterministic RGB image on a square neutral canvas.

    The function intentionally does not claim to segment the catalog image. It
    standardizes orientation, alpha handling, color mode, and aspect-ratio
    padding so query and catalog images follow the same basic contract.
    """

    if image.width < 1 or image.height < 1:
        raise ValueError("Image dimensions must be greater than zero.")

    input_width, input_height = image.size
    rgb = prepare_rgb_image(image)

    side = max(rgb.size)
    canvas = Image.new("RGB", (side, side), NEUTRAL_BACKGROUND)
    offset = ((side - rgb.width) // 2, (side - rgb.height) // 2)
    canvas.paste(rgb, offset)

    info = PreprocessingInfo(
        version=PREPROCESSING_VERSION,
        input_width=input_width,
        input_height=input_height,
        output_width=canvas.width,
        output_height=canvas.height,
        background="white",
    )
    return canvas, info
