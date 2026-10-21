from __future__ import annotations

import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from services.contracts.release_v2 import (
    CourseReleaseItemV5,
    CourseReleaseManifestV5,
    PersonaSupplementDescriptorV1,
    parse_signed_course_release_manifest,
    release_v5_schema_document,
)

ROOT = Path(__file__).resolve().parents[1]
RELEASE_PATH = (
    ROOT
    / "content"
    / "releases"
    / "manifests"
    / "C-prequin-state"
    / "rel-28b5624648-0007.json"
)
SCHEMA_PATH = (
    ROOT
    / "content"
    / "schemas"
    / "releases"
    / "v5"
    / "course-release-manifest.schema.json"
)


class ReleaseV5ContractTests(unittest.TestCase):
    def test_committed_schema_and_release_match_contract(self):
        self.assertEqual(
            json.loads(SCHEMA_PATH.read_text(encoding="utf-8")),
            release_v5_schema_document(),
        )
        release = parse_signed_course_release_manifest(
            json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
        )
        self.assertIsInstance(release, CourseReleaseManifestV5)
        self.assertEqual(release.release_no, 7)
        self.assertEqual(
            [item.lesson_id for item in release.items],
            ["L101", "L103"],
        )

    def test_persona_descriptor_requires_content_addressed_path(self):
        release = CourseReleaseManifestV5.model_validate_json(
            RELEASE_PATH.read_text(encoding="utf-8")
        )
        descriptor = release.items[0].persona_pack
        payload = descriptor.model_dump(mode="json")
        payload["path"] = "runtime/v1/personas/tampered.json"
        with self.assertRaises(ValidationError):
            PersonaSupplementDescriptorV1.model_validate(payload)

    def test_v5_requires_v2_evidence_and_persona_identity(self):
        release = CourseReleaseManifestV5.model_validate_json(
            RELEASE_PATH.read_text(encoding="utf-8")
        )
        item = release.items[0]
        payload = item.model_dump(mode="json")
        payload["evidence_corpus"]["schema_version"] = "evidence-corpus/v1"
        payload["evidence_corpus"]["path"] = payload["evidence_corpus"]["path"].replace(
            "runtime/v2/evidence", "runtime/v1/evidence"
        )
        with self.assertRaises(ValidationError):
            CourseReleaseItemV5.model_validate(payload)

        payload = item.model_dump(mode="json")
        payload["persona_pack"]["lesson_id"] = "L103"
        with self.assertRaises(ValidationError):
            CourseReleaseItemV5.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
