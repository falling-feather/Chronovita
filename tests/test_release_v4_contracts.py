import json
from pathlib import Path
import unittest
from pydantic import ValidationError

from services.contracts.release_examples import build_dayu_release_manifest_v3
from services.contracts.release_v2 import (
    CourseReleaseItemV4, CourseReleaseManifestV3, CourseReleaseManifestV4,
    EvidenceSupplementDescriptorV2, parse_signed_course_release_manifest,
    RELEASE_V4_SCHEMA_DOCUMENTS, ReleaseSupplementDescriptorV1,
    RuntimeArtifactDescriptorV1, runtime_artifact_path,
    sign_release_metadata, supplement_artifact_path, supplement_artifact_path_v2,
    verify_release_metadata_checksum,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "content" / "schemas" / "releases" / "v4"


def manifest_v4(*, v2: bool) -> CourseReleaseManifestV4:
    old = build_dayu_release_manifest_v3()
    old_item = old.items[0]
    evidence = old_item.evidence_corpus
    if v2:
        evidence = EvidenceSupplementDescriptorV2(
            artifact_id=evidence.artifact_id, course_id=evidence.course_id,
            lesson_id=evidence.lesson_id, version=2, checksum="a" * 64,
            path=supplement_artifact_path_v2(
                artifact_id=evidence.artifact_id, course_id=evidence.course_id,
                lesson_id=evidence.lesson_id, version=2, checksum="a" * 64,
            ),
        )
    item = CourseReleaseItemV4(**{
        **old_item.model_dump(mode="json"),
        "evidence_corpus": evidence.model_dump(mode="json"),
    })
    return sign_release_metadata(CourseReleaseManifestV4(
        release_id="rel-1234567890-0001", release_no=1, course_id=old.course_id,
        operation="bootstrap", created_at=old.created_at, created_by="test",
        items=(item,), checksum="0" * 64,
    ))


class ReleaseV4ContractTests(unittest.TestCase):
    def test_committed_v4_schema_matches_model_without_stale_files(self):
        for filename, builder in RELEASE_V4_SCHEMA_DOCUMENTS.items():
            with self.subTest(filename=filename):
                self.assertEqual(
                    json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8")),
                    builder(),
                )
        self.assertEqual(
            {path.name for path in SCHEMA_DIR.glob("*.json")},
            set(RELEASE_V4_SCHEMA_DOCUMENTS),
        )

    def test_v4_reads_v1_or_v2_evidence(self):
        for uses_v2 in (False, True):
            with self.subTest(uses_v2=uses_v2):
                manifest = manifest_v4(v2=uses_v2)
                self.assertTrue(verify_release_metadata_checksum(manifest))
                parsed = parse_signed_course_release_manifest(
                    manifest.model_dump(mode="json")
                )
                self.assertIsInstance(parsed, CourseReleaseManifestV4)

    def test_v3_still_rejects_v2_evidence(self):
        item = manifest_v4(v2=True).items[0].model_dump(mode="json")
        with self.assertRaises(ValidationError):
            CourseReleaseManifestV3(
                release_id="rel-1234567890-0001",
                release_no=1,
                course_id="C-prequin-state",
                operation="bootstrap",
                created_at=manifest_v4(v2=True).created_at,
                created_by="test",
                items=(item,),
                checksum="0" * 64,
            )

    def test_v2_descriptor_path_tampering_fails_closed(self):
        raw = manifest_v4(v2=True).items[0].evidence_corpus.model_dump(
            mode="json"
        )
        raw["path"] = "runtime/v2/evidence/latest.json"
        with self.assertRaisesRegex(ValidationError, "canonical"):
            EvidenceSupplementDescriptorV2.model_validate(raw)

    def test_v4_rejects_duplicate_artifact_ids_across_lessons(self):
        for duplicate, message in (
            ("scenario", "scenario_id"),
            ("evidence", "evidence corpus identity"),
            ("presentation", "lesson presentation identity"),
        ):
            with self.subTest(duplicate=duplicate):
                with self.assertRaisesRegex(ValidationError, message):
                    _two_lesson_manifest(duplicate)


def _two_lesson_manifest(duplicate: str) -> CourseReleaseManifestV4:
    first = manifest_v4(v2=True).items[0]
    lesson_id = "L103"
    package_checksum = "b" * 64
    package_id = "course-L103"
    package = RuntimeArtifactDescriptorV1(
        kind="course-package", schema_version="course-package/v1",
        artifact_id=package_id, course_id=first.course_id, lesson_id=lesson_id,
        version=first.content_version, checksum=package_checksum,
        path=runtime_artifact_path(
            kind="course-package", artifact_id=package_id, course_id=first.course_id,
            lesson_id=lesson_id, version=first.content_version, checksum=package_checksum,
        ),
    )
    scenario_id = first.scenarios[0].artifact_id if duplicate == "scenario" else "scenario-L103"
    scenario_checksum = "c" * 64
    scenario = RuntimeArtifactDescriptorV1(
        kind="scenario-template", schema_version="scenario-template/v1",
        artifact_id=scenario_id, course_id=first.course_id, lesson_id=lesson_id,
        version=1, checksum=scenario_checksum,
        path=runtime_artifact_path(
            kind="scenario-template", artifact_id=scenario_id, course_id=first.course_id,
            lesson_id=lesson_id, version=1, checksum=scenario_checksum,
        ),
    )
    evidence_id = first.evidence_corpus.artifact_id if duplicate == "evidence" else "evidence-L103-v2"
    evidence_checksum = "d" * 64
    evidence = EvidenceSupplementDescriptorV2(
        artifact_id=evidence_id, course_id=first.course_id, lesson_id=lesson_id,
        version=2, checksum=evidence_checksum,
        path=supplement_artifact_path_v2(
            artifact_id=evidence_id, course_id=first.course_id, lesson_id=lesson_id,
            version=2, checksum=evidence_checksum,
        ),
    )
    presentation_id = first.lesson_presentation.artifact_id if duplicate == "presentation" else "presentation-L103-v1"
    presentation_checksum = "e" * 64
    presentation = ReleaseSupplementDescriptorV1(
        kind="lesson-presentation", schema_version="lesson-presentation/v1",
        artifact_id=presentation_id, course_id=first.course_id, lesson_id=lesson_id,
        version=1, checksum=presentation_checksum,
        path=supplement_artifact_path(
            kind="lesson-presentation", artifact_id=presentation_id,
            course_id=first.course_id, lesson_id=lesson_id, version=1,
            checksum=presentation_checksum,
        ),
    )
    second = CourseReleaseItemV4(
        lesson_id=lesson_id, course_id=first.course_id,
        content_version=first.content_version, source_path=f"sealed/{lesson_id}-v{first.content_version:03d}.json",
        source_checksum="f" * 64, course_package=package, scenarios=(scenario,),
        primary_scenario_id=scenario_id, evidence_corpus=evidence,
        lesson_presentation=presentation,
    )
    return CourseReleaseManifestV4(
        release_id="rel-1234567890-0001", release_no=1, course_id=first.course_id,
        operation="bootstrap", created_at=manifest_v4(v2=True).created_at,
        created_by="test", items=tuple(sorted((first, second), key=lambda item: item.lesson_id)),
        checksum="0" * 64,
    )


if __name__ == "__main__":
    unittest.main()
