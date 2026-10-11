"""Validation helpers for images received by the public API."""

from io import BytesIO

from PIL import Image, UnidentifiedImageError

from backend.image_preprocessing import prepare_rgb_image


MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/bmp",
}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP", "BMP"}


def validate_image_bytes(
    content: bytes,
    content_type: str | None = None,
    *,
    max_bytes: int = MAX_IMAGE_BYTES,
    max_pixels: int = MAX_IMAGE_PIXELS,
) -> Image.Image:
    """Return a safe RGB image or raise ``ValueError`` for invalid input."""

    if not content:
        raise ValueError("The uploaded image is empty.")
    if len(content) > max_bytes:
        raise ValueError(
            f"The uploaded image exceeds the {max_bytes // (1024 * 1024)} MB limit."
        )
    if content_type and content_type.lower() not in ALLOWED_CONTENT_TYPES:
        raise ValueError("Unsupported image content type.")

    try:
        with Image.open(BytesIO(content)) as probe:
            image_format = (probe.format or "").upper()
            width, height = probe.size
            probe.verify()

        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise ValueError("Unsupported image format.")
        if width < 1 or height < 1:
            raise ValueError("The uploaded image has invalid dimensions.")
        if width * height > max_pixels:
            raise ValueError(
                f"The uploaded image exceeds the {max_pixels:,}-pixel limit."
            )

        with Image.open(BytesIO(content)) as uploaded_image:
            uploaded_image.load()
            return prepare_rgb_image(uploaded_image)
    except ValueError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as error:
        raise ValueError("The uploaded file is not a valid supported image.") from error
