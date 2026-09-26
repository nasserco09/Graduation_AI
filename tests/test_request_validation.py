from io import BytesIO
import unittest

from PIL import Image

from backend.request_validation import validate_image_bytes


def png_bytes(size=(16, 12)):
    output = BytesIO()
    Image.new("RGB", size, "blue").save(output, format="PNG")
    return output.getvalue()


class RequestValidationTests(unittest.TestCase):
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
