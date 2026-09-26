import unittest

from PIL import Image

from backend.image_preprocessing import (
    NEUTRAL_BACKGROUND,
    PREPROCESSING_VERSION,
    preprocess_image,
)


class ImagePreprocessingTests(unittest.TestCase):
    def test_rectangular_image_is_centered_on_square_canvas(self):
        source = Image.new("RGB", (4, 2), (10, 20, 30))

        result, info = preprocess_image(source)

        self.assertEqual(result.mode, "RGB")
        self.assertEqual(result.size, (4, 4))
        self.assertEqual(result.getpixel((0, 0)), NEUTRAL_BACKGROUND)
        self.assertEqual(result.getpixel((1, 1)), (10, 20, 30))
        self.assertEqual(info.version, PREPROCESSING_VERSION)
        self.assertEqual((info.input_width, info.input_height), (4, 2))

    def test_transparency_becomes_white_not_black(self):
        source = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
        source.putpixel((1, 1), (255, 0, 0, 255))

        result, _ = preprocess_image(source)

        self.assertEqual(result.getpixel((0, 0)), NEUTRAL_BACKGROUND)
        self.assertEqual(result.getpixel((1, 1)), (255, 0, 0))

    def test_preprocessing_is_idempotent(self):
        source = Image.new("RGB", (3, 5), (80, 90, 100))

        first, _ = preprocess_image(source)
        second, _ = preprocess_image(first)

        self.assertEqual(first.size, second.size)
        self.assertEqual(first.tobytes(), second.tobytes())


if __name__ == "__main__":
    unittest.main()
