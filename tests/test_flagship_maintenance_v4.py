from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.publish_flagship_lesson import publish_dayu, publish_shangyang
from scripts.publish_flagship_media import publish_flagship_media
from services import content
from services.content import runtime_artifacts, workflow
from services.content.flagships.dayu_l101_evidence_v2 import (
    build_dayu_evidence_v2,
)
from services.content.flagships.shangyang_l103_evidence_v2 import (
    build_shangyang_evidence_v2,
)
from services.contracts.release_v2 import (
    CourseReleaseItemV4,
    CourseReleaseManifestV3,
    CourseReleaseManifestV4,
)
from tests.release_fixture import activate_v3_release_5


REPOSITORY_CONTENT = Path(__file__).resolve().parents[1] / "content"
COURSE_ID = "C-prequin-state"


class FlagshipMaintenanceV4Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_root = content.content_root()
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "content"
        shutil.copytree(REPOSITORY_CONTENT, self.root)
        content.configure(self.root)

    def tearDown(self) -> None:
        content.configure(self.original_root)
        self.temp_dir.cleanup()

    def _activate_v4_with_v1_evidence(self) -> CourseReleaseManifestV4:
        current = workflow.get_current_release(COURSE_ID)
        self.assertIsInstance(current, CourseReleaseManifestV3)
        items = tuple(
            CourseReleaseItemV4.model_validate(item.model_dump(mode="json"))
            for item in current.items
        )
        previous_pointer = workflow._load_pointer(COURSE_ID)
        manifest, manifest_path = workflow._write_release_manifest(
            course_id=COURSE_ID,
            operation="publish",
            items=items,
            actor="v4-compatibility-test",
            note="Exercise a V4 manifest that retains reviewed V1 evidence.",
            parent=current,
        )
        workflow._commit_release(
            manifest,
            actor="v4-compatibility-test",
            note="Activate the V4 plus V1 compatibility fixture.",
            action="publish",
            previous_pointer=previous_pointer,
            cleanup_paths=[manifest_path],
        )
        self.assertIsInstance(manifest, CourseReleaseManifestV4)
        return manifest

    def _activate_v4_with_v2_evidence(self) -> CourseReleaseManifestV4:
        current = workflow.get_current_release(COURSE_ID)
        if isinstance(current, CourseReleaseManifestV4) and {
            item.evidence_corpus.schema_version for item in current.items
        } == {"evidence-corpus/v2"}:
            return current
        corpora = (
            build_dayu_evidence_v2(sealed_by="content-publisher-admin"),
            build_shangyang_evidence_v2(sealed_by="content-publisher-admin"),
        )
        for corpus in corpora:
            runtime_artifacts.stage_evidence_corpus(corpus)
        manifest = workflow.publish_evidence_bundle_v2(
            COURSE_ID,
            tuple(
                workflow.EvidenceBundleReleaseSelection(
                    lesson_id=corpus.lesson_id,
                    corpus_id=corpus.corpus_id,
                    corpus_version=corpus.corpus_version,
                    corpus_checksum=corpus.checksum,
                    schema_version=corpus.schema_version,
                )
                for corpus in corpora
            ),
            actor="content-publisher-admin",
            note="Activate both reviewed V2 corpora atomically.",
        )
        self.assertIsInstance(manifest, CourseReleaseManifestV4)
        return manifest

    def _copy_media_version(self, source_version: int, target_version: int) -> None:
        for lesson_id in ("L101", "L103"):
            source = self.root / (
                f"media/lessons/{lesson_id}/v{source_version:03d}"
            )
            target = self.root / (
                f"media/lessons/{lesson_id}/v{target_version:03d}"
            )
            shutil.copytree(source, target)

    def test_media_and_legacy_publishers_preserve_v4_with_v1_evidence(self) -> None:
        activate_v3_release_5(self.root)
        v4_release = self._activate_v4_with_v1_evidence()
        self._copy_media_version(2, 3)
        manifest_count = len(
            list((self.root / "releases/manifests" / COURSE_ID).glob("*.json"))
        )

        media_result = publish_flagship_media(self.root, presentation_version=3)

        self.assertEqual(media_result["release_schema_version"], "course-release/v4")
        current = workflow.get_current_release(COURSE_ID)
        self.assertEqual(current.parent_release_id, media_result["lessons"][0]["release_id"])
        self.assertNotEqual(current.release_id, v4_release.release_id)
        self.assertIsInstance(current, CourseReleaseManifestV4)
        self.assertEqual(
            {item.evidence_corpus.schema_version for item in current.items},
            {"evidence-corpus/v1"},
        )
        self.assertEqual(
            {item.lesson_presentation.version for item in current.items},
            {3},
        )
        self.assertEqual(
            len(list((self.root / "releases/manifests" / COURSE_ID).glob("*.json"))),
            manifest_count + 2,
        )

        for publisher in (publish_dayu, publish_shangyang):
            with self.subTest(publisher=publisher.__name__):
                result = publisher(root=self.root)
                self.assertEqual(result["status"], "already-published")
                preserved = workflow.get_current_release(COURSE_ID)
                self.assertIsInstance(preserved, CourseReleaseManifestV4)
                self.assertEqual(preserved.release_id, current.release_id)

    def test_media_preserves_v2_but_legacy_lesson_publishers_fail_closed(self) -> None:
        v4_release = self._activate_v4_with_v2_evidence()
        manifest_count = len(
            list((self.root / "releases/manifests" / COURSE_ID).glob("*.json"))
        )

        media_result = publish_flagship_media(self.root)

        self.assertEqual(media_result["release_schema_version"], "course-release/v4")
        current = workflow.get_current_release(COURSE_ID)
        self.assertEqual(current.release_id, v4_release.release_id)
        self.assertEqual(
            {item.evidence_corpus.schema_version for item in current.items},
            {"evidence-corpus/v2"},
        )
        self.assertEqual(
            len(list((self.root / "releases/manifests" / COURSE_ID).glob("*.json"))),
            manifest_count,
        )

        for publisher in (publish_dayu, publish_shangyang):
            with self.subTest(publisher=publisher.__name__):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "publish_flagship_evidence_v2.py",
                ):
                    publisher(root=self.root)
                preserved = workflow.get_current_release(COURSE_ID)
                self.assertIsInstance(preserved, CourseReleaseManifestV4)
                self.assertEqual(preserved.release_id, v4_release.release_id)


if __name__ == "__main__":
    unittest.main()
