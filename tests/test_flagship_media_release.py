from __future__ import annotations

import hashlib
import shutil
import unittest
import uuid
from pathlib import Path

from services import content
from services.content import workflow
from services.content.flagships.dayu_l101 import build_dayu_presentation
from services.content.flagships.shangyang_l103 import build_shangyang_presentation
from scripts.publish_flagship_media import publish_flagship_media


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_CONTENT = PROJECT_ROOT / "content"


class FlagshipMediaReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_root = content.content_root()
        content.configure(REPOSITORY_CONTENT)

    def tearDown(self) -> None:
        content.configure(self.original_root)

    def test_current_release_pins_both_v002_presentations_and_assets(self) -> None:
        release = workflow.get_current_release("C-prequin-state")
        self.assertIsNotNone(release)
        self.assertEqual(release.schema_version, "course-release/v3")
        self.assertEqual(release.release_no, 5)

        expected_builders = {
            "L101": build_dayu_presentation,
            "L103": build_shangyang_presentation,
        }
        for lesson_id, builder in expected_builders.items():
            resources = workflow.get_published_lesson_resources(
                "C-prequin-state", lesson_id
            )
            presentation = resources.lesson_presentation
            self.assertEqual(presentation.presentation_version, 2)
            self.assertEqual(presentation.video_duration_seconds, 45)
            self.assertIn(f"/{lesson_id}/v002/", f"/{presentation.video_path}")
            expected = builder(
                REPOSITORY_CONTENT,
                sealed_by=presentation.sealed_by,
                sealed_at=presentation.sealed_at,
                presentation_version=2,
            )
            self.assertEqual(expected, presentation)
            for path, checksum in (
                (presentation.video_path, presentation.video_sha256),
                (presentation.poster_path, presentation.poster_sha256),
                (presentation.transcript_path, presentation.transcript_sha256),
            ):
                self.assertEqual(
                    hashlib.sha256((REPOSITORY_CONTENT / path).read_bytes()).hexdigest(),
                    checksum,
                )

    def test_media_publication_is_idempotent_after_v002_is_active(self) -> None:
        temp_parent = PROJECT_ROOT / ".tmp-flagship-media" / uuid.uuid4().hex
        temp_content = temp_parent / "content"
        shutil.copytree(REPOSITORY_CONTENT, temp_content)
        try:
            pointer = temp_content / "releases/active/C-prequin-state.json"
            before_hash = hashlib.sha256(pointer.read_bytes()).hexdigest()
            manifests = temp_content / "releases/manifests/C-prequin-state"
            before_count = len(list(manifests.glob("*.json")))

            result = publish_flagship_media(temp_content)

            self.assertEqual(result["final_release_no"], 5)
            self.assertEqual(before_hash, hashlib.sha256(pointer.read_bytes()).hexdigest())
            self.assertEqual(before_count, len(list(manifests.glob("*.json"))))
        finally:
            content.configure(REPOSITORY_CONTENT)
            shutil.rmtree(temp_parent.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
