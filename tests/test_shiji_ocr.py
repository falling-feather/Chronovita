from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from scripts.install_shiji_facsimile import install
from services import shiji_ocr


class ShijiSmokeFixtureTests(unittest.TestCase):
    def test_browser_smoke_page_is_a_real_indexed_facsimile(self) -> None:
        root = Path(__file__).resolve().parents[1]
        index = json.loads((root / "content/shiji/ocr-pages-index.json").read_text(encoding="utf-8"))
        page = next(item for item in index["pages"]
                    if item["id"] == "shiji--baina-ia-mirror--6c5c0783a987--p0124")
        fixture = root / "tests/fixtures/shiji-baina-page0124.webp"
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(), page["image_sha256"])


class ShijiOcrBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.pages = []
        self.images = {}
        with ZipFile(self.root / "records.zip", "w") as archive:
            for version, page_no in [("baina-ia-mirror", 2), ("baina-ia-mirror", 1), ("siku-quanshu-ia-zju", 1)]:
                page_id = f"{version}-{page_no}"
                relative_record = f"{version}/source/page-{page_no:04d}/page.json"
                relative_image = relative_record.replace(".json", ".webp")
                image = f"image-{page_id}".encode()
                payload = {"id": page_id, "book": {"id": "shiji"}, "version": {"id": version},
                           "transcription": {"raw_text": "禹疏九河。", "corrected_text": "", "status": "unreviewed"},
                           "ocr": {"blocks": [{"text": "禹疏九河。"}]}, "source": {"pdf_page": page_no},
                           "mapping": {"status": "draft"}, "manual_content": {"keywords": []}}
                data = json.dumps(payload, ensure_ascii=False).encode()
                archive.writestr(relative_record, data)
                self.images[relative_image] = image
                self.pages.append({"id": page_id, "version_id": version, "source_file_label": "史记01.pdf",
                                   "pdf_page": page_no, "relative_record": relative_record, "relative_image": relative_image,
                                   "image_sha256": hashlib.sha256(image).hexdigest(),
                                   "record_sha256": hashlib.sha256(data).hexdigest()})
        self.index_path = self.root / "index.json"
        self.write_index()
        self.index_patch = patch.object(shiji_ocr, "INDEX_PATH", self.index_path)
        self.content_patch = patch.object(shiji_ocr, "CONTENT_ROOT", self.root)
        self.index_patch.start()
        self.content_patch.start()
        shiji_ocr.clear_cache()

    def tearDown(self) -> None:
        shiji_ocr.clear_cache()
        self.content_patch.stop()
        self.index_patch.stop()
        self.temp.cleanup()

    def write_index(self) -> None:
        self.index_path.write_text(json.dumps({"book_id": "shiji", "page_count": len(self.pages), "pages": self.pages,
                                              "records_archive": "records.zip",
                                              "records_sha256": hashlib.sha256((self.root / "records.zip").read_bytes()).hexdigest()}), encoding="utf-8")

    def image_archive(self, *, incomplete: bool = False, unsafe: bool = False) -> Path:
        path = self.root / "images.zip"
        with ZipFile(path, "w") as archive:
            for position, (name, data) in enumerate(self.images.items()):
                if not incomplete or position > 0:
                    archive.writestr(name, data)
            if unsafe:
                archive.writestr("../escaped.webp", b"unsafe")
        return path

    def test_ocr_text_and_blocks_are_real_and_sha_bound(self) -> None:
        payload = shiji_ocr.page_payload("baina-ia-mirror-1")
        self.assertEqual(payload["transcription"]["raw_text"], "禹疏九河。")
        self.assertTrue(payload["ocr"]["blocks"])
        self.pages[1]["record_sha256"] = "0" * 64
        self.write_index()
        shiji_ocr.clear_cache()
        with self.assertRaises(shiji_ocr.ShijiOcrError):
            shiji_ocr.page_payload("baina-ia-mirror-1")

    def test_neighbors_follow_pages_and_do_not_cross_versions(self) -> None:
        neighbors = shiji_ocr.page_neighbors("baina-ia-mirror-1")
        self.assertEqual(neighbors["position"], 1)
        self.assertEqual(neighbors["next_page_id"], "baina-ia-mirror-2")
        self.assertIsNone(shiji_ocr.page_neighbors("baina-ia-mirror-2")["next_page_id"])
        self.assertEqual(len(shiji_ocr.filtered_pages(version_id="siku-quanshu-ia-zju")), 1)
        self.assertEqual(shiji_ocr.filtered_pages(book_id="other"), [])

    def test_install_preserves_version_paths_and_is_idempotent(self) -> None:
        target = self.root / "installed"
        archive = self.image_archive()
        installed = install(archive, target, index_path=self.index_path)
        self.assertEqual(installed["page_count"], 3)
        for name, data in self.images.items():
            self.assertEqual((target / name).read_bytes(), data)
        again = install(archive, target, index_path=self.index_path)
        self.assertEqual(len(again["reused_versions"]), 2)

    def test_install_refuses_missing_pages_and_zip_slip(self) -> None:
        for options in ({"incomplete": True}, {"unsafe": True}):
            target = self.root / "rejected"
            with self.assertRaises(ValueError):
                install(self.image_archive(**options), target, index_path=self.index_path)
            self.assertFalse(target.exists())
            self.assertFalse((self.root / "escaped.webp").exists())

    def test_install_never_overwrites_existing_user_files(self) -> None:
        target = self.root / "existing"
        existing = target / next(iter(self.images))
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b"user data")
        with self.assertRaises(ValueError):
            install(self.image_archive(), target, index_path=self.index_path)
        self.assertEqual(existing.read_bytes(), b"user data")


if __name__ == "__main__":
    unittest.main()
