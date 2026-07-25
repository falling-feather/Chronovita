import json
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from services.contracts.release_examples import (
    build_dayu_release_manifest,
    release_example_documents,
)
from services.contracts.release_v2 import (
    ActiveReleasePointerV1,
    CourseReleaseItemV1,
    CourseReleaseManifestV1,
    CourseReleaseManifestV2,
    RELEASE_SCHEMA_DOCUMENTS,
    RuntimeArtifactDescriptorV1,
    parse_course_release_manifest,
    parse_signed_course_release_manifest,
    release_schema_document,
    runtime_artifact_path,
    sign_release_metadata,
    verify_release_metadata_checksum,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "content" / "schemas" / "releases" / "v2"
EXAMPLE_DIR = REPO_ROOT / "content" / "examples" / "releases" / "v2"


class ReleaseContractTests(unittest.TestCase):
    def test_committed_release_schema_and_example_match_models(self):
        for filename, builder in RELEASE_SCHEMA_DOCUMENTS.items():
            with self.subTest(filename=filename):
                self.assertEqual(_read_json(SCHEMA_DIR / filename), builder())
        for filename, example in release_example_documents().items():
            with self.subTest(filename=filename):
                raw = _read_json(EXAMPLE_DIR / filename)
                parsed = parse_signed_course_release_manifest(raw)
                self.assertIsInstance(parsed, CourseReleaseManifestV2)
                self.assertEqual(parsed.model_dump(mode="json"), raw)
                self.assertEqual(example.model_dump(mode="json"), raw)
        self.assertEqual(
            {path.name for path in SCHEMA_DIR.glob("*.json")},
            set(RELEASE_SCHEMA_DOCUMENTS),
        )
        self.assertEqual(
            {path.name for path in EXAMPLE_DIR.glob("*.json")},
            set(release_example_documents()),
        )

    def test_v1_and_v2_manifests_use_one_discriminated_reader(self):
        legacy = sign_release_metadata(
            CourseReleaseManifestV1(
                release_id="rel-1234567890-0001",
                release_no=1,
                course_id="C-legacy",
                operation="bootstrap",
                created_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
                created_by="migration-test",
                items=(
                    CourseReleaseItemV1(
                        lesson_id="legacy-lesson",
                        course_id="C-legacy",
                        content_version=1,
                        source_path="sealed/legacy-lesson-v001.json",
                        source_checksum="1" * 64,
                        package_path="packages/v1/legacy-lesson-v001.json",
                        package_checksum="2" * 64,
                    ),
                ),
                checksum="0" * 64,
            )
        )
        parsed_v1 = parse_signed_course_release_manifest(
            legacy.model_dump(mode="json")
        )
        parsed_v2 = parse_signed_course_release_manifest(
            build_dayu_release_manifest().model_dump(mode="json")
        )
        self.assertIsInstance(parsed_v1, CourseReleaseManifestV1)
        self.assertIsInstance(parsed_v2, CourseReleaseManifestV2)
        self.assertEqual(parsed_v1.items[0].package_path, "packages/v1/legacy-lesson-v001.json")

    def test_runtime_descriptors_require_kind_schema_and_content_address(self):
        descriptor = build_dayu_release_manifest().items[0].course_package
        expected = runtime_artifact_path(
            kind=descriptor.kind,
            artifact_id=descriptor.artifact_id,
            course_id=descriptor.course_id,
            lesson_id=descriptor.lesson_id,
            version=descriptor.version,
            checksum=descriptor.checksum,
        )
        self.assertEqual(descriptor.path, expected)

        wrong_schema = descriptor.model_dump(mode="json")
        wrong_schema["schema_version"] = "scenario-template/v1"
        with self.assertRaisesRegex(ValidationError, "require schema_version"):
            RuntimeArtifactDescriptorV1.model_validate(wrong_schema)

        wrong_path = descriptor.model_dump(mode="json")
        wrong_path["path"] = "packages/v1/latest.json"
        with self.assertRaisesRegex(ValidationError, "content-addressed"):
            RuntimeArtifactDescriptorV1.model_validate(wrong_path)

    def test_release_item_rejects_identity_order_and_primary_drift(self):
        item = build_dayu_release_manifest().items[0].model_dump(mode="json")

        wrong_identity = deepcopy(item)
        wrong_identity["course_package"]["lesson_id"] = "other-lesson"
        wrong_identity["course_package"]["path"] = runtime_artifact_path(
            kind="course-package",
            artifact_id=wrong_identity["course_package"]["artifact_id"],
            course_id=wrong_identity["course_package"]["course_id"],
            lesson_id="other-lesson",
            version=wrong_identity["course_package"]["version"],
            checksum=wrong_identity["course_package"]["checksum"],
        )
        with self.assertRaisesRegex(ValidationError, "identity must match"):
            CourseReleaseManifestV2.model_validate(
                {
                    **build_dayu_release_manifest().model_dump(mode="json"),
                    "items": [wrong_identity],
                }
            )

        no_primary = deepcopy(item)
        no_primary["primary_scenario_id"] = None
        with self.assertRaisesRegex(ValidationError, "requires one primary"):
            CourseReleaseManifestV2.model_validate(
                {
                    **build_dayu_release_manifest().model_dump(mode="json"),
                    "items": [no_primary],
                }
            )

        second = deepcopy(item["scenarios"][0])
        second["artifact_id"] = "scenario-aardvark"
        second["path"] = runtime_artifact_path(
            kind="scenario-template",
            artifact_id=second["artifact_id"],
            course_id=second["course_id"],
            lesson_id=second["lesson_id"],
            version=second["version"],
            checksum=second["checksum"],
        )
        unsorted = deepcopy(item)
        unsorted["scenarios"].append(second)
        with self.assertRaisesRegex(ValidationError, "sorted by artifact_id"):
            CourseReleaseManifestV2.model_validate(
                {
                    **build_dayu_release_manifest().model_dump(mode="json"),
                    "items": [unsorted],
                }
            )

    def test_manifest_rejects_duplicate_scenario_ids_across_lessons(self):
        raw = build_dayu_release_manifest().model_dump(mode="json")
        second = deepcopy(raw["items"][0])
        second["lesson_id"] = "second-lesson"
        second["source_path"] = "sealed/second-lesson-v001.json"
        second["course_package"]["lesson_id"] = "second-lesson"
        second["course_package"]["path"] = runtime_artifact_path(
            kind="course-package",
            artifact_id=second["course_package"]["artifact_id"],
            course_id=second["course_id"],
            lesson_id="second-lesson",
            version=second["content_version"],
            checksum=second["course_package"]["checksum"],
        )
        second["scenarios"][0]["lesson_id"] = "second-lesson"
        second["scenarios"][0]["path"] = runtime_artifact_path(
            kind="scenario-template",
            artifact_id=second["scenarios"][0]["artifact_id"],
            course_id=second["course_id"],
            lesson_id="second-lesson",
            version=second["scenarios"][0]["version"],
            checksum=second["scenarios"][0]["checksum"],
        )
        raw["items"] = [raw["items"][0], second]
        with self.assertRaisesRegex(ValidationError, "scenario_id must be unique"):
            CourseReleaseManifestV2.model_validate(raw)

    def test_checksum_detects_payload_tampering(self):
        manifest = build_dayu_release_manifest()
        self.assertTrue(verify_release_metadata_checksum(manifest))
        raw = manifest.model_dump(mode="json")
        raw["note"] = "tampered after signing"
        parsed = parse_course_release_manifest(raw)
        self.assertFalse(verify_release_metadata_checksum(parsed))
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            parse_signed_course_release_manifest(raw)

    def test_v1_pointer_can_commit_a_v2_manifest_without_a_second_pointer(self):
        manifest = build_dayu_release_manifest()
        pointer = sign_release_metadata(
            ActiveReleasePointerV1(
                course_id=manifest.course_id,
                release_id=manifest.release_id,
                release_no=manifest.release_no,
                manifest_path=(
                    f"releases/manifests/{manifest.course_id}/{manifest.release_id}.json"
                ),
                manifest_checksum=manifest.checksum,
                generation=1,
                activated_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
                activated_by="publisher",
                checksum="0" * 64,
            )
        )
        self.assertTrue(verify_release_metadata_checksum(pointer))
        self.assertEqual(pointer.manifest_checksum, manifest.checksum)

    def test_contracts_reject_unknown_fields(self):
        raw = build_dayu_release_manifest().model_dump(mode="json")
        raw["catalog_path"] = "latest.json"
        with self.assertRaises(ValidationError):
            CourseReleaseManifestV2.model_validate(raw)

    def test_schema_explains_semantic_validation_boundary(self):
        document = release_schema_document()
        self.assertIn("content-addressed paths", document["$comment"])
        self.assertEqual(document["properties"]["schema_version"]["const"], "course-release/v2")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
