from __future__ import annotations

import unittest
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.routers import courses
from services import content
from services.content.flagships import LESSON_ID as DAYU_LESSON_ID
from services.courses.textbooks import load_textbooks, text_checksum


class CoursePresentationApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original_root = content.content_root()
        cls.temp = TemporaryDirectory()
        root = Path(cls.temp.name) / "content"
        shutil.copytree(Path("content"), root)
        content.configure(root)
        # An explicitly aligned teacher fixture exercises media serving/security.
        resources = courses.content_workflow.get_published_lesson_resources("C-prequin-state", DAYU_LESSON_ID)
        book = load_textbooks()["C-prequin-state"].model_dump(mode="json")
        for lesson in book["lessons"]:
            if lesson["lesson_id"] == DAYU_LESSON_ID:
                for field in ("title", "abstract", "body"):
                    lesson[field] = resources.course_package.model_dump(mode="json")[field]
                lesson["keywords"] = [
                    dict(word=k.word, pinyin=k.pinyin, gloss=k.gloss)
                    for k in resources.course_package.keywords
                ]
        book["text_checksum"] = text_checksum(book)
        content._atomic_write_json(root / "textbooks/C-prequin-state.json", book)
        app = FastAPI()
        app.include_router(courses.router, prefix="/api/v1/courses")
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        content.configure(cls.original_root)
        cls.temp.cleanup()

    def test_old_shangyang_video_is_not_attached_to_new_western_zhou_text(self):
        response = self.client.get("/api/v1/courses/C-prequin-state/lessons/L103/presentation")
        self.assertEqual(response.status_code, 404)

    def test_presentation_exposes_only_release_pinned_asset_urls(self) -> None:
        response = self.client.get(
            f"/api/v1/courses/C-prequin-state/lessons/{DAYU_LESSON_ID}/presentation"
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(set(payload["asset_urls"]), {"video", "poster", "transcript"})
        for url in payload["asset_urls"].values():
            self.assertIn(payload["release_checksum"], url)
            self.assertNotIn("content/media", url)

    def test_asset_requires_current_release_checksum_and_is_immutable(self) -> None:
        presentation = self.client.get(
            f"/api/v1/courses/C-prequin-state/lessons/{DAYU_LESSON_ID}/presentation"
        ).json()
        poster_url = presentation["asset_urls"]["poster"]
        response = self.client.get(poster_url)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["content-type"], "image/webp")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertIn("immutable", response.headers["cache-control"])
        self.assertEqual(
            response.headers["etag"],
            f'"{presentation["presentation"]["poster_sha256"]}"',
        )

        stale = self.client.get(
            poster_url.replace(presentation["release_checksum"], "0" * 64)
        )
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["detail"]["code"], "presentation_release_changed")

    def test_asset_path_is_still_confined_to_lesson_media_root(self) -> None:
        presentation = self.client.get(
            f"/api/v1/courses/C-prequin-state/lessons/{DAYU_LESSON_ID}/presentation"
        ).json()
        resources = courses.content_workflow.get_published_lesson_resources(
            "C-prequin-state", DAYU_LESSON_ID
        )
        tampered_presentation = SimpleNamespace(
            **resources.lesson_presentation.model_dump(mode="python")
        )
        tampered_presentation.poster_path = "../README.md"
        tampered = SimpleNamespace(
            release_checksum=resources.release_checksum,
            lesson_presentation=tampered_presentation,
            course_package=resources.course_package,
        )
        with patch.object(
            courses.content_workflow,
            "get_published_lesson_resources",
            return_value=tampered,
        ):
            response = self.client.get(presentation["asset_urls"]["poster"])
        self.assertEqual(response.status_code, 503, response.text)


if __name__ == "__main__":
    unittest.main()
