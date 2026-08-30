from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from services import content
from services.content import workflow
from services.contracts.release_v2 import CourseReleaseManifestV4
from scripts.publish_flagship_evidence_v2 import publish_flagship_evidence_v2
from tests.release_fixture import activate_v3_release_5


REPOSITORY_CONTENT = Path(__file__).resolve().parents[1] / "content"


class PublishFlagshipEvidenceV2Tests(unittest.TestCase):
    def test_command_publishes_once_and_is_then_idempotent(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("media", "releases", "runtime", "sealed", "workflows"):
                shutil.copytree(REPOSITORY_CONTENT / name, root / name)
            try:
                activate_v3_release_5(root)
                first = publish_flagship_evidence_v2(root)
                manifest_count = len(
                    tuple((root / "releases" / "manifests").rglob("*.json"))
                )
                second = publish_flagship_evidence_v2(root)

                self.assertEqual(first["status"], "published")
                self.assertEqual(second["status"], "already-published")
                self.assertEqual(first["release_id"], second["release_id"])
                self.assertEqual(
                    manifest_count,
                    len(tuple((root / "releases" / "manifests").rglob("*.json"))),
                )
                current = workflow.get_current_release("C-prequin-state")
                self.assertIsInstance(current, CourseReleaseManifestV4)
                assert current is not None
                self.assertEqual(current.release_no, 6)
                self.assertEqual(
                    {item.evidence_corpus.schema_version for item in current.items},
                    {"evidence-corpus/v2"},
                )
            finally:
                content.configure()

    def test_command_is_idempotent_from_repository_v4_start(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in ("media", "releases", "runtime", "sealed", "workflows"):
                shutil.copytree(REPOSITORY_CONTENT / name, root / name)
            try:
                before = tuple((root / "releases" / "manifests").rglob("*.json"))
                result = publish_flagship_evidence_v2(root)
                after = tuple((root / "releases" / "manifests").rglob("*.json"))
                self.assertEqual(result["status"], "already-published")
                self.assertEqual(result["release_no"], 6)
                self.assertEqual(len(before), len(after))
            finally:
                content.configure()


if __name__ == "__main__":
    unittest.main()
