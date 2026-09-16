from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from services import content
from services.content import workflow
from services.contracts.release_v2 import (
    CourseReleaseManifestV4,
    CourseReleaseManifestV5,
)
from scripts.publish_flagship_evidence_v2 import publish_flagship_evidence_v2
from tests.release_fixture import activate_v3_release_5


REPOSITORY_CONTENT = Path(__file__).resolve().parents[1] / "content"


class PublishFlagshipEvidenceV2Tests(unittest.TestCase):
    def test_command_cannot_skip_the_reviewed_v2_lineage_from_release_five(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("media", "releases", "runtime", "sealed", "workflows"):
                shutil.copytree(REPOSITORY_CONTENT / name, root / name)
            try:
                activate_v3_release_5(root)
                pointer = root / "releases/active/C-prequin-state.json"
                pointer_before = pointer.read_bytes()
                manifests_before = tuple(
                    (root / "releases" / "manifests").rglob("*.json")
                )
                with self.assertRaisesRegex(
                    workflow.ContentConflict,
                    "does not supersede the exact published corpus",
                ):
                    publish_flagship_evidence_v2(root)

                self.assertEqual(pointer.read_bytes(), pointer_before)
                self.assertEqual(
                    len(manifests_before),
                    len(tuple((root / "releases" / "manifests").rglob("*.json"))),
                )
                current = workflow.get_current_release("C-prequin-state")
                self.assertNotIsInstance(current, CourseReleaseManifestV4)
                assert current is not None
                self.assertEqual(current.release_no, 5)
            finally:
                content.configure()

    def test_command_is_idempotent_from_repository_v5_start(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("media", "releases", "runtime", "sealed", "workflows"):
                shutil.copytree(REPOSITORY_CONTENT / name, root / name)
            try:
                before = tuple((root / "releases" / "manifests").rglob("*.json"))
                result = publish_flagship_evidence_v2(root)
                after = tuple((root / "releases" / "manifests").rglob("*.json"))
                self.assertEqual(result["status"], "already-published")
                self.assertEqual(result["release_no"], 10)
                self.assertEqual(len(before), len(after))
                current = workflow.get_current_release("C-prequin-state")
                self.assertIsInstance(current, CourseReleaseManifestV5)
                assert current is not None
                selections = tuple(
                    workflow.EvidenceBundleReleaseSelection(
                        lesson_id=item.lesson_id,
                        corpus_id=item.evidence_corpus.artifact_id,
                        corpus_version=item.evidence_corpus.version,
                        corpus_checksum=item.evidence_corpus.checksum,
                        schema_version=item.evidence_corpus.schema_version,
                    )
                    for item in current.items
                )
                replay = workflow.publish_evidence_bundle_v2(
                    "C-prequin-state",
                    selections,
                    actor="content-publisher-admin",
                )
                self.assertIsInstance(replay, CourseReleaseManifestV5)
                self.assertEqual(replay.release_id, current.release_id)
                changed = (
                    selections[0].model_copy(
                        update={"corpus_checksum": "0" * 64}
                    ),
                    selections[1],
                )
                with self.assertRaisesRegex(
                    workflow.ContentConflict,
                    "cannot be replaced independently",
                ):
                    workflow.publish_evidence_bundle_v2(
                        "C-prequin-state",
                        changed,
                        actor="content-publisher-admin",
                    )
                final_manifests = tuple(
                    (root / "releases/manifests").rglob("*.json")
                )
                self.assertEqual(len(before), len(final_manifests))
            finally:
                content.configure()


if __name__ == "__main__":
    unittest.main()
