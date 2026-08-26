from __future__ import annotations

from datetime import datetime, timezone

from services.contracts.examples import build_dayu_bundle
from services.contracts.release_v2 import (
    CourseReleaseItemV2,
    CourseReleaseItemV3,
    CourseReleaseManifestV2,
    CourseReleaseManifestV3,
    ReleaseSupplementDescriptorV1,
    RuntimeArtifactDescriptorV1,
    runtime_artifact_path,
    sign_release_metadata,
    supplement_artifact_path,
)


def build_dayu_release_manifest() -> CourseReleaseManifestV2:
    bundle = build_dayu_bundle()
    course = bundle.course
    scenario = bundle.scenario
    course_descriptor = RuntimeArtifactDescriptorV1(
        kind="course-package",
        schema_version=course.schema_version,
        artifact_id=course.package_id,
        course_id=course.course_id,
        lesson_id=course.lesson_id,
        version=course.content_version,
        checksum=str(course.checksum),
        path=runtime_artifact_path(
            kind="course-package",
            artifact_id=course.package_id,
            course_id=course.course_id,
            lesson_id=course.lesson_id,
            version=course.content_version,
            checksum=str(course.checksum),
        ),
    )
    scenario_descriptor = RuntimeArtifactDescriptorV1(
        kind="scenario-template",
        schema_version=scenario.schema_version,
        artifact_id=scenario.scenario_id,
        course_id=scenario.course_id,
        lesson_id=scenario.lesson_id,
        version=scenario.scenario_version,
        checksum=str(scenario.checksum),
        path=runtime_artifact_path(
            kind="scenario-template",
            artifact_id=scenario.scenario_id,
            course_id=scenario.course_id,
            lesson_id=scenario.lesson_id,
            version=scenario.scenario_version,
            checksum=str(scenario.checksum),
        ),
    )
    manifest = CourseReleaseManifestV2(
        release_id="rel-01a2b3c4d5-0001",
        release_no=1,
        course_id=course.course_id,
        operation="bootstrap",
        created_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
        created_by="architecture-fixture",
        note="Development-only contract fixture; not an active published release.",
        items=(
            CourseReleaseItemV2(
                lesson_id=course.lesson_id,
                course_id=course.course_id,
                content_version=course.content_version,
                source_path=f"sealed/{course.lesson_id}-v{course.content_version:03d}.json",
                source_checksum=str(course.compatibility.source_checksum or course.checksum),
                course_package=course_descriptor,
                scenarios=(scenario_descriptor,),
                primary_scenario_id=scenario.scenario_id,
            ),
        ),
        checksum="0" * 64,
    )
    return sign_release_metadata(manifest)


def release_example_documents() -> dict[str, CourseReleaseManifestV2]:
    return {"dayu-course-release-manifest.json": build_dayu_release_manifest()}


def build_dayu_release_manifest_v3() -> CourseReleaseManifestV3:
    v2 = build_dayu_release_manifest()
    item = v2.items[0]
    evidence_checksum = "3" * 64
    presentation_checksum = "4" * 64
    evidence = ReleaseSupplementDescriptorV1(
        kind="evidence-corpus",
        schema_version="evidence-corpus/v1",
        artifact_id="evidence-dayu-v1",
        course_id=item.course_id,
        lesson_id=item.lesson_id,
        version=1,
        checksum=evidence_checksum,
        path=supplement_artifact_path(
            kind="evidence-corpus",
            artifact_id="evidence-dayu-v1",
            course_id=item.course_id,
            lesson_id=item.lesson_id,
            version=1,
            checksum=evidence_checksum,
        ),
    )
    presentation = ReleaseSupplementDescriptorV1(
        kind="lesson-presentation",
        schema_version="lesson-presentation/v1",
        artifact_id="presentation-dayu-v1",
        course_id=item.course_id,
        lesson_id=item.lesson_id,
        version=1,
        checksum=presentation_checksum,
        path=supplement_artifact_path(
            kind="lesson-presentation",
            artifact_id="presentation-dayu-v1",
            course_id=item.course_id,
            lesson_id=item.lesson_id,
            version=1,
            checksum=presentation_checksum,
        ),
    )
    return sign_release_metadata(
        CourseReleaseManifestV3(
            release_id="rel-11a2b3c4d5-0002",
            release_no=2,
            course_id=v2.course_id,
            operation="publish",
            parent_release_id=v2.release_id,
            created_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
            created_by="architecture-fixture",
            note="V3 contract fixture; not an active published release.",
            items=(
                CourseReleaseItemV3(
                    lesson_id=item.lesson_id,
                    course_id=item.course_id,
                    content_version=item.content_version,
                    source_path=item.source_path,
                    source_checksum=item.source_checksum,
                    course_package=item.course_package,
                    scenarios=item.scenarios,
                    primary_scenario_id=item.primary_scenario_id,
                    evidence_corpus=evidence,
                    lesson_presentation=presentation,
                ),
            ),
            checksum="0" * 64,
        )
    )


def release_v3_example_documents() -> dict[str, CourseReleaseManifestV3]:
    return {"dayu-course-release-manifest-v3.json": build_dayu_release_manifest_v3()}


__all__ = [
    "build_dayu_release_manifest",
    "build_dayu_release_manifest_v3",
    "release_example_documents",
    "release_v3_example_documents",
]
