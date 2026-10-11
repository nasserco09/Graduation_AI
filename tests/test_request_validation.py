from io import BytesIO
import unittest

from PIL import Image

from backend.image_preprocessing import preprocess_image
from backend.request_validation import validate_image_bytes


def png_bytes(size=(16, 12)):
    output = BytesIO()
    Image.new("RGB", size, "blue").save(output, format="PNG")
    return output.getvalue()


class RequestValidationTests(unittest.TestCase):
    def assert_transparent_upload_matches_direct_preprocessing(self, source):
        output = BytesIO()
        source.save(output, format="PNG")
        uploaded = validate_image_bytes(output.getvalue(), "image/png")
        actual, _ = preprocess_image(uploaded)
        expected, _ = preprocess_image(source)
        self.assertEqual(uploaded.mode, "RGB")
        self.assertEqual(uploaded.size, source.size)
        self.assertEqual(actual.tobytes(), expected.tobytes())
        self.assertEqual(actual.getpixel((0, 0)), (255, 255, 255))

    def test_rgba_upload_composites_transparent_and_partial_alpha(self):
        source = Image.new("RGBA", (3, 3), (0, 0, 0, 0))
        source.putpixel((1, 1), (255, 0, 0, 128))
        source.putpixel((2, 2), (0, 0, 255, 255))
        self.assert_transparent_upload_matches_direct_preprocessing(source)

    def test_grayscale_alpha_upload_uses_white_background(self):
        source = Image.new("LA", (3, 3), (0, 0))
        source.putpixel((1, 1), (80, 128))
        source.putpixel((2, 2), (20, 255))
        self.assert_transparent_upload_matches_direct_preprocessing(source)

    def test_palette_transparency_upload_uses_white_background(self):
        source = Image.new("P", (3, 3), 0)
        source.putpalette([0, 0, 0, 255, 0, 0] + [0] * 762)
        source.info["transparency"] = 0
        source.putpixel((1, 1), 1)
        self.assert_transparent_upload_matches_direct_preprocessing(source)

    def test_accepts_supported_image_and_normalizes_to_rgb(self):
        image = validate_image_bytes(png_bytes(), "image/png")
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.size, (16, 12))

    def test_rejects_empty_upload(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            validate_image_bytes(b"", "image/png")

    def test_rejects_oversized_upload(self):
        with self.assertRaisesRegex(ValueError, "limit"):
            validate_image_bytes(png_bytes(), "image/png", max_bytes=2)

    def test_rejects_spoofed_content_type(self):
        with self.assertRaisesRegex(ValueError, "content type"):
            validate_image_bytes(png_bytes(), "text/plain")

    def test_rejects_invalid_image_payload(self):
        with self.assertRaisesRegex(ValueError, "valid supported image"):
            validate_image_bytes(b"not-an-image", "image/png")

    def test_rejects_excessive_pixel_count(self):
        with self.assertRaisesRegex(ValueError, "pixel limit"):
            validate_image_bytes(png_bytes((20, 20)), "image/png", max_pixels=100)


if __name__ == "__main__":
    unittest.main()
