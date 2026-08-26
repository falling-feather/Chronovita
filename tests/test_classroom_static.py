from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.static_web import mount_classroom_web


class ClassroomStaticTests(unittest.TestCase):
    def test_spa_routes_and_hashed_assets_share_one_origin(self):
        with tempfile.TemporaryDirectory() as temporary:
            dist = Path(temporary)
            (dist / "assets").mkdir()
            (dist / "index.html").write_text(
                "<!doctype html><title>Chronovita</title>", encoding="utf-8"
            )
            (dist / "assets" / "app-abc123.js").write_text(
                "console.log('classroom')", encoding="utf-8"
            )
            app = FastAPI()
            mount_classroom_web(app, dist)

            with TestClient(app) as client:
                login = client.get("/login")
                asset = client.get("/assets/app-abc123.js")
                api = client.get("/api/not-real")
                missing_file = client.get("/missing.txt")

            self.assertEqual(login.status_code, 200)
            self.assertIn("Chronovita", login.text)
            self.assertEqual(login.headers["cache-control"], "no-cache")
            self.assertEqual(asset.status_code, 200)
            self.assertIn("immutable", asset.headers["cache-control"])
            self.assertEqual(asset.headers["x-content-type-options"], "nosniff")
            self.assertEqual(api.status_code, 404)
            self.assertEqual(missing_file.status_code, 404)

    def test_mount_rejects_incomplete_prebuilt_frontend(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(RuntimeError, "prebuilt classroom web app"):
                mount_classroom_web(FastAPI(), Path(temporary))


if __name__ == "__main__":
    unittest.main()
