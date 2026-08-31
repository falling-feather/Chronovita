from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts import build_pages_preview


ROOT = Path(__file__).resolve().parents[1]


class PagesPreviewTests(unittest.TestCase):
    def test_builder_follows_active_v5_release(self) -> None:
        payload = build_pages_preview.build()
        pointer = json.loads(
            (ROOT / "content/releases/active/C-prequin-state.json").read_text(
                encoding="utf-8"
            )
        )
        manifest = json.loads(
            (ROOT / "content" / pointer["manifest_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema_version"], "course-release/v5")
        self.assertEqual(manifest["release_no"], 8)
        self.assertIn(
            f'{manifest["course_id"]}#8:{manifest["checksum"][:12]}',
            payload["release_identity"],
        )
        for lesson_id in ("L101", "L103"):
            lesson = payload["lessons"][f"C-prequin-state/{lesson_id}"]
            self.assertEqual(len(lesson["scenario_refs"]), 1)
            self.assertEqual(
                lesson["primary_scenario_id"],
                lesson["scenario_refs"][0]["scenario_id"],
            )
            self.assertTrue(lesson["scenario_refs"][0]["primary"])
            presentation = payload["presentations"][
                f"C-prequin-state/{lesson_id}"
            ]
            self.assertEqual(presentation["release_no"], 8)
            self.assertEqual(
                presentation["release_checksum"], manifest["checksum"]
            )

    def test_committed_preview_matches_deterministic_builder(self) -> None:
        committed = json.loads(
            build_pages_preview.OUTPUT.read_text(encoding="utf-8")
        )
        self.assertEqual(committed, build_pages_preview.build())


if __name__ == "__main__":
    unittest.main()
