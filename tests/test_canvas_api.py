import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from main import app
from settings import settings
from services import content, persistence


class CanvasApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous = {
            "auth_mode": settings.auth_mode,
            "content_root": settings.content_root,
            "game_catalog_path": settings.game_catalog_path,
            "sqlite_path": settings.sqlite_path,
        }
        settings.auth_mode = "legacy-local"
        settings.content_root = str(REPO_ROOT / "content")
        settings.game_catalog_path = "scenarios/catalog.v1.json"
        settings.sqlite_path = str(Path(self.temp_dir.name) / "chronovita.db")
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        for key, value in self.previous.items():
            setattr(settings, key, value)
        content.configure()
        self.temp_dir.cleanup()

    def test_missing_canvas_and_explicit_empty_canvas_are_distinct(self):
        missing = self.client.get("/api/v1/practice/canvas/lesson-empty")
        self.assertEqual(missing.status_code, 200, missing.text)
        self.assertEqual(
            missing.json(),
            {
                "nodes": [],
                "edges": [],
                "schema_version": "canvas/v1",
                "found": False,
                "revision": 0,
            },
        )

        saved = self.client.put(
            "/api/v1/practice/canvas/lesson-empty",
            json={"expected_revision": 0, "nodes": [], "edges": []},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertTrue(saved.json()["found"])
        self.assertEqual(saved.json()["revision"], 1)

        fetched = self.client.get("/api/v1/practice/canvas/lesson-empty")
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertTrue(fetched.json()["found"])
        self.assertEqual(fetched.json()["nodes"], [])
        self.assertEqual(fetched.json()["revision"], 1)

    def test_stale_save_is_rejected_without_overwriting_newer_graph(self):
        first = self.client.put(
            "/api/v1/practice/canvas/lesson-cas",
            json={
                "expected_revision": 0,
                "nodes": [{"id": "first", "position": {"x": 0, "y": 0}, "data": {"label": "初稿"}}],
                "edges": [],
            },
        )
        self.assertEqual(first.status_code, 200, first.text)

        newer = self.client.put(
            "/api/v1/practice/canvas/lesson-cas",
            json={
                "expected_revision": 1,
                "nodes": [{"id": "newer", "position": {"x": 20, "y": 20}, "data": {"label": "新稿"}}],
                "edges": [],
            },
        )
        self.assertEqual(newer.status_code, 200, newer.text)
        self.assertEqual(newer.json()["revision"], 2)

        stale = self.client.put(
            "/api/v1/practice/canvas/lesson-cas",
            json={
                "expected_revision": 1,
                "nodes": [{"id": "stale", "position": {"x": 5, "y": 5}, "data": {"label": "旧稿"}}],
                "edges": [],
            },
        )
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(
            stale.json()["detail"]["code"],
            "canvas_revision_conflict",
        )

        fetched = self.client.get("/api/v1/practice/canvas/lesson-cas")
        self.assertEqual(fetched.json()["revision"], 2)
        self.assertEqual(fetched.json()["nodes"][0]["id"], "newer")

    def test_legacy_canvas_migrates_on_the_next_successful_save(self):
        persistence.kv_set("canvas", "lesson-legacy", {"nodes": [], "edges": []})

        fetched = self.client.get("/api/v1/practice/canvas/lesson-legacy")
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertTrue(fetched.json()["found"])
        self.assertEqual(fetched.json()["revision"], 1)

        saved = self.client.put(
            "/api/v1/practice/canvas/lesson-legacy",
            json={"expected_revision": 1, "nodes": [], "edges": []},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["revision"], 2)
        stored = persistence.kv_get("canvas", "lesson-legacy")
        self.assertEqual(stored["schema_version"], "canvas/v1")
        self.assertEqual(stored["revision"], 2)

    def test_corrupt_canvas_fails_closed(self):
        for lesson_id, corrupt in (
            ("lesson-corrupt", {"nodes": "not-a-list", "edges": []}),
            ("lesson-null", None),
        ):
            with self.subTest(lesson_id=lesson_id):
                persistence.kv_set("canvas", lesson_id, corrupt)

                fetched = self.client.get(f"/api/v1/practice/canvas/{lesson_id}")
                self.assertEqual(fetched.status_code, 500, fetched.text)
                self.assertEqual(
                    fetched.json()["detail"]["code"],
                    "canvas_integrity_error",
                )
                saved = self.client.put(
                    f"/api/v1/practice/canvas/{lesson_id}",
                    json={"expected_revision": 0, "nodes": [], "edges": []},
                )
                self.assertEqual(saved.status_code, 500, saved.text)
                self.assertEqual(
                    saved.json()["detail"]["code"],
                    "canvas_integrity_error",
                )
                found, stored = persistence.kv_get_with_presence("canvas", lesson_id)
                self.assertTrue(found)
                self.assertEqual(stored, corrupt)


if __name__ == "__main__":
    unittest.main()
