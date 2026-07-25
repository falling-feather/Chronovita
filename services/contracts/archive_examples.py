from __future__ import annotations

import hashlib
import html
import json
from datetime import datetime, timezone

from pydantic import BaseModel

from services.content import (
    KeywordCard,
    LessonContentPackage,
    MapPoint,
    PersonCard,
    SourceRef,
    package_checksum,
)
from services.contracts.archive_v1 import (
    ARCHIVE_MANIFEST_FILENAME,
    ARCHIVE_RELEASE_MANIFEST_FILENAME,
    ArchiveRendererV1,
    CourseArchiveFileV1,
    CourseArchiveLessonV1,
    CourseArchiveManifestV1,
    CourseArchivePayloadV1,
    CourseArchivePublishRequestV1,
    CourseArchiveScenarioV1,
    GitPublicationIntentV1,
    GitPublicationRecordV1,
    GitRepositoryBindingV1,
    archive_id_for_checksum,
    archive_relative_path,
    calculate_archive_payload_checksum,
    lesson_archive_paths,
    publication_branch_name,
    publication_id_for_key,
    publication_operation_key,
    scenario_archive_path,
    sign_archive_manifest,
    sign_publication_metadata,
)
from services.contracts.examples import build_dayu_bundle
from services.contracts.release_examples import build_dayu_release_manifest
from services.contracts.release_v2 import (
    CourseReleaseManifestV2,
    sign_release_metadata,
)


ARCHIVE_EXAMPLE_PACKAGE_DIRECTORY = "dayu-course-archive"
_FIXTURE_AT = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)
_FIXTURE_ACTOR = "archive-contract-fixture"


def build_dayu_sealed_lesson() -> LessonContentPackage:
    course = build_dayu_bundle().course
    provisional = LessonContentPackage(
        lesson_id=course.lesson_id,
        title=course.title,
        unit=course.unit,
        era=course.era,
        body=list(course.body),
        course_id=course.course_id,
        course_title=course.course_title or course.unit,
        era_id=course.era_id,
        section=course.section,
        lesson_no=course.lesson_no or "A1",
        duration=course.duration or "08:00",
        abstract=course.abstract,
        keywords=[
            KeywordCard(
                word=item.word,
                pinyin=item.pinyin,
                gloss=item.gloss,
            )
            for item in course.keywords
        ],
        people=[
            PersonCard(
                name=item.name,
                role=item.role,
                summary=item.summary,
                persona=item.persona,
                boundaries=list(item.boundaries),
            )
            for item in course.people
        ],
        map_points=[
            MapPoint(
                label=item.label,
                region=item.region,
                lat=item.lat,
                lng=item.lng,
                note=item.note,
                kind=item.kind,
            )
            for item in course.map_points
        ],
        source_refs=[
            SourceRef(
                title=item.title,
                source=item.publisher or item.kind,
                url_or_path=item.url_or_path,
                citation_note=item.citation_note,
                reliability=item.reliability,
            )
            for item in course.source_refs
        ],
        facts=[item.statement for item in course.facts],
        qa_points=list(course.qa_points),
        level_goals=list(course.level_goals),
        teacher_notes=course.teacher_notes,
        status="sealed",
        version=course.content_version,
        created_at=course.created_at,
        updated_at=course.updated_at,
        sealed_at=course.sealed_at,
        sealed_by=_FIXTURE_ACTOR,
        checksum="0" * 64,
    )
    return LessonContentPackage.model_validate(
        {
            **provisional.model_dump(mode="json"),
            "checksum": package_checksum(provisional),
        }
    )


def build_dayu_archive_release() -> CourseReleaseManifestV2:
    sealed = build_dayu_sealed_lesson()
    release = build_dayu_release_manifest()
    raw = release.model_dump(mode="json")
    raw["items"][0]["source_checksum"] = sealed.checksum
    raw["checksum"] = "0" * 64
    return sign_release_metadata(CourseReleaseManifestV2.model_validate(raw))


def build_example_repository_binding() -> GitRepositoryBindingV1:
    return GitRepositoryBindingV1(
        binding_id="content-history-primary",
        repository_id=123456789,
        owner="chronovita-example",
        repository="chronovita-course-content",
        base_branch="main",
        root_prefix="courses",
        asset_root_prefix="assets",
        credential_kind="github_app",
        installation_id=12345678,
        allowed_modes=("pull_request", "direct_commit"),
    )


def build_dayu_archive_package() -> tuple[CourseArchiveManifestV1, dict[str, bytes]]:
    bundle = build_dayu_bundle()
    course = bundle.course
    scenario = bundle.scenario
    sealed = build_dayu_sealed_lesson()
    release = build_dayu_archive_release()
    release_item = release.items[0]
    paths = lesson_archive_paths(sealed.lesson_id, sealed.title)
    scenario_path = scenario_archive_path(
        sealed.lesson_id,
        scenario.scenario_id,
        scenario.scenario_version,
    )

    payloads = {
        ARCHIVE_RELEASE_MANIFEST_FILENAME: _json_bytes(
            release.model_dump(mode="json")
        ),
        paths["sealed-lesson"]: _json_bytes(sealed.model_dump(mode="json")),
        paths["course-package"]: _json_bytes(course.model_dump(mode="json")),
        scenario_path: _json_bytes(scenario.model_dump(mode="json")),
        paths["format-layer"]: _json_bytes(_format_layer(sealed)),
        paths["teacher-markdown"]: _teacher_markdown(sealed).encode("utf-8"),
        paths["preview-html"]: _preview_html(sealed).encode("utf-8"),
    }
    descriptors = (
        _file_descriptor(
            path=ARCHIVE_RELEASE_MANIFEST_FILENAME,
            kind="release-manifest",
            media_type="application/json",
            payload=payloads[ARCHIVE_RELEASE_MANIFEST_FILENAME],
            artifact_id=release.release_id,
            artifact_version=release.release_no,
            schema_version=release.schema_version,
            contract_checksum=release.checksum,
        ),
        _file_descriptor(
            path=paths["sealed-lesson"],
            kind="sealed-lesson",
            media_type="application/json",
            payload=payloads[paths["sealed-lesson"]],
            lesson_id=sealed.lesson_id,
            artifact_id=sealed.lesson_id,
            artifact_version=sealed.version,
            schema_version="lesson-content-package/v1",
            contract_checksum=str(sealed.checksum),
        ),
        _file_descriptor(
            path=paths["course-package"],
            kind="course-package",
            media_type="application/json",
            payload=payloads[paths["course-package"]],
            lesson_id=sealed.lesson_id,
            artifact_id=course.package_id,
            artifact_version=course.content_version,
            schema_version=course.schema_version,
            contract_checksum=str(course.checksum),
        ),
        _file_descriptor(
            path=scenario_path,
            kind="scenario-template",
            media_type="application/json",
            payload=payloads[scenario_path],
            lesson_id=sealed.lesson_id,
            artifact_id=scenario.scenario_id,
            artifact_version=scenario.scenario_version,
            schema_version=scenario.schema_version,
            contract_checksum=str(scenario.checksum),
        ),
        _file_descriptor(
            path=paths["format-layer"],
            kind="format-layer",
            media_type="application/json",
            payload=payloads[paths["format-layer"]],
            lesson_id=sealed.lesson_id,
        ),
        _file_descriptor(
            path=paths["teacher-markdown"],
            kind="teacher-markdown",
            media_type="text/markdown; charset=utf-8",
            payload=payloads[paths["teacher-markdown"]],
            lesson_id=sealed.lesson_id,
        ),
        _file_descriptor(
            path=paths["preview-html"],
            kind="preview-html",
            media_type="text/html; charset=utf-8",
            payload=payloads[paths["preview-html"]],
            lesson_id=sealed.lesson_id,
        ),
    )
    sorted_descriptors = tuple(sorted(descriptors, key=lambda item: item.path.casefold()))
    lesson_files = tuple(
        item.path for item in sorted_descriptors if item.lesson_id == sealed.lesson_id
    )
    lesson = CourseArchiveLessonV1(
        lesson_id=sealed.lesson_id,
        title=sealed.title,
        content_version=sealed.version,
        source_checksum=str(sealed.checksum),
        course_package_id=release_item.course_package.artifact_id,
        course_package_checksum=release_item.course_package.checksum,
        scenarios=(
            CourseArchiveScenarioV1(
                scenario_id=scenario.scenario_id,
                scenario_version=scenario.scenario_version,
                scenario_checksum=str(scenario.checksum),
                primary=True,
            ),
        ),
        files=lesson_files,
    )
    archive_payload = CourseArchivePayloadV1(
        course_id=release.course_id,
        course_title=sealed.course_title,
        release_schema_version=release.schema_version,
        release_id=release.release_id,
        release_no=release.release_no,
        release_checksum=release.checksum,
        release_operation=release.operation,
        release_created_at=release.created_at,
        release_created_by=release.created_by,
        release_note=release.note,
        renderer=ArchiveRendererV1(
            renderer_id="chronovita-teacher-export",
            renderer_version=1,
            style_profile="course-preview-default",
        ),
        lessons=(lesson,),
        files=sorted_descriptors,
        file_count=len(sorted_descriptors),
        total_size_bytes=sum(item.size_bytes for item in sorted_descriptors),
    )
    archive_checksum = calculate_archive_payload_checksum(archive_payload)
    unsigned = CourseArchiveManifestV1(
        **archive_payload.model_dump(mode="json"),
        archive_id=archive_id_for_checksum(archive_checksum),
        archive_checksum=archive_checksum,
        archive_path=archive_relative_path(
            release.course_id,
            release.release_id,
            archive_id_for_checksum(archive_checksum),
        ),
        manifest_checksum="0" * 64,
    )
    manifest = sign_archive_manifest(unsigned)
    package_files = {
        ARCHIVE_MANIFEST_FILENAME: _json_bytes(manifest.model_dump(mode="json")),
        **payloads,
    }
    return manifest, package_files


def build_dayu_publish_request() -> CourseArchivePublishRequestV1:
    manifest, _ = build_dayu_archive_package()
    binding = build_example_repository_binding()
    return CourseArchivePublishRequestV1(
        binding_id=binding.binding_id,
        course_id=manifest.course_id,
        release_id=manifest.release_id,
        expected_release_checksum=manifest.release_checksum,
        archive_id=manifest.archive_id,
        expected_archive_checksum=manifest.archive_checksum,
        mode="pull_request",
        client_request_id="request-dayu-archive-001",
        change_summary="提交大禹治水开发夹具，用于验证课程归档与审校流程。",
    )


def build_dayu_publication_intent() -> GitPublicationIntentV1:
    binding = build_example_repository_binding()
    request = build_dayu_publish_request()
    operation_key = publication_operation_key(binding, request)
    unsigned = GitPublicationIntentV1(
        publication_id=publication_id_for_key(operation_key),
        operation_key=operation_key,
        binding=binding,
        request=request,
        requested_at=_FIXTURE_AT,
        requested_by=_FIXTURE_ACTOR,
        checksum="0" * 64,
    )
    return sign_publication_metadata(unsigned)


def build_dayu_publication_record() -> GitPublicationRecordV1:
    intent = build_dayu_publication_intent()
    request = intent.request
    unsigned = GitPublicationRecordV1(
        intent=intent,
        status="succeeded",
        attempt=1,
        revision=6,
        branch_ref=publication_branch_name(
            request.course_id,
            request.release_id,
            request.expected_archive_checksum,
        ),
        base_sha="1" * 40,
        tree_sha="2" * 40,
        commit_sha="3" * 40,
        pull_request_number=17,
        pull_request_url=(
            f"https://github.com/{intent.binding.full_name}/pull/17"
        ),
        updated_at=_FIXTURE_AT,
        completed_at=_FIXTURE_AT,
        checksum="0" * 64,
    )
    return sign_publication_metadata(unsigned)


def archive_example_documents() -> dict[str, BaseModel]:
    manifest, _ = build_dayu_archive_package()
    return {
        "dayu-course-archive-manifest.json": manifest,
        "github-repository-binding.json": build_example_repository_binding(),
        "dayu-course-archive-publish-request.json": build_dayu_publish_request(),
        "dayu-git-publication-intent.json": build_dayu_publication_intent(),
        "dayu-git-publication-record.json": build_dayu_publication_record(),
    }


def archive_example_package_files() -> dict[str, bytes]:
    _, files = build_dayu_archive_package()
    return files


def _file_descriptor(
    *,
    path: str,
    kind: str,
    media_type: str,
    payload: bytes,
    lesson_id: str | None = None,
    artifact_id: str | None = None,
    artifact_version: int | None = None,
    schema_version: str | None = None,
    contract_checksum: str | None = None,
) -> CourseArchiveFileV1:
    return CourseArchiveFileV1(
        path=path,
        kind=kind,
        media_type=media_type,
        size_bytes=len(payload),
        blob_sha256=hashlib.sha256(payload).hexdigest(),
        lesson_id=lesson_id,
        artifact_id=artifact_id,
        artifact_version=artifact_version,
        schema_version=schema_version,
        contract_checksum=contract_checksum,
    )


def _format_layer(item: LessonContentPackage) -> dict:
    return {
        "schema_version": "teacher-format-layer/v1",
        "lesson_id": item.lesson_id,
        "source_checksum": item.checksum,
        "syntax": {
            "bold": "**文字**",
            "highlight": "==标红文字==",
            "keyword": "【关键词】",
            "heading": "# 一级标题 / ## 二级标题 / ### 三级标题",
            "colors": "{{红色:文字}} / {{蓝色:文字}} / {{金色:文字}}",
            "font_size": "{{大字:文字}} / {{小字:文字}}",
        },
        "paragraphs": [
            {
                "index": index,
                "raw": paragraph,
            }
            for index, paragraph in enumerate(item.body)
        ],
    }


def _teacher_markdown(item: LessonContentPackage) -> str:
    lines = [
        f"# {item.title}",
        "",
        f"- lesson_id: {item.lesson_id}",
        f"- course_id: {item.course_id}",
        f"- unit: {item.unit}",
        f"- era: {item.era}",
        f"- status: {item.status}",
        "",
        "## 正文",
    ]
    lines.extend(f"\n{paragraph}" for paragraph in item.body)
    lines.extend(["", "## 关键词"])
    lines.extend(
        f"- {keyword.word}{f'：{keyword.gloss}' if keyword.gloss else ''}"
        for keyword in item.keywords
    )
    lines.extend(["", "## 重点块"])
    lines.extend(f"- {fact}" for fact in item.facts)
    return "\n".join(lines) + "\n"


def _preview_html(item: LessonContentPackage) -> str:
    body = "\n".join(f"    <p>{html.escape(text)}</p>" for text in item.body)
    keywords = "".join(
        f"<li><strong>{html.escape(keyword.word)}</strong>"
        f"{'：' + html.escape(keyword.gloss) if keyword.gloss else ''}</li>"
        for keyword in item.keywords
    )
    people = "".join(
        f"<li><strong>{html.escape(person.name)}</strong>"
        f"{' · ' + html.escape(person.role) if person.role else ''}</li>"
        for person in item.people
    )
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '  <meta charset="utf-8" />\n'
        f"  <title>{html.escape(item.title)}</title>\n"
        "</head>\n"
        "<body>\n"
        "  <main>\n"
        f"    <h1>{html.escape(item.title)}</h1>\n"
        f"{body}\n"
        f"    <section><h2>关键词</h2><ul>{keywords}</ul></section>\n"
        f"    <section><h2>人物</h2><ul>{people}</ul></section>\n"
        "  </main>\n"
        "</body>\n"
        "</html>\n"
    )


def _json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


__all__ = [
    "ARCHIVE_EXAMPLE_PACKAGE_DIRECTORY",
    "archive_example_documents",
    "archive_example_package_files",
    "build_dayu_archive_package",
    "build_dayu_archive_release",
    "build_dayu_publication_intent",
    "build_dayu_publication_record",
    "build_dayu_publish_request",
    "build_dayu_sealed_lesson",
    "build_example_repository_binding",
]
