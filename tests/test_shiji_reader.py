from __future__ import annotations

import unittest

from services import shiji_reader


class ShijiReaderArchiveTests(unittest.TestCase):
    def tearDown(self) -> None:
        shiji_reader.close()

    def test_navigation_exposes_130_volumes_and_first_chapter(self) -> None:
        navigation = shiji_reader.navigation()
        self.assertEqual(navigation["book_id"], "shiji")
        self.assertEqual(navigation["total_volumes"], 130)
        self.assertTrue(navigation["volumes"][0]["chapters"])

    def test_chapter_contains_ocr_and_reading_layers(self) -> None:
        navigation = shiji_reader.navigation()
        chapter_id = navigation["volumes"][0]["chapters"][0]["id"]
        result = shiji_reader.chapter(chapter_id)
        chapter = result["payload"]["chapter"]
        self.assertEqual(result["book_id"], "shiji")
        self.assertTrue(chapter["sentences"])
        first = chapter["sentences"][0]
        self.assertTrue(first.get("simplified"))
        self.assertIn("raw_ocr_available", first)


if __name__ == "__main__":
    unittest.main()
