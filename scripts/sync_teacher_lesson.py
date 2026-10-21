"""Publish one reviewed teacher lesson while preserving pending V5 modules.

The source draft is first sealed exactly as imported. A second immutable student
package keeps the new reading experience but retains the active release's
structural fields that are still required by scenario, evidence and persona
contracts. The active release only moves after a new persona pack is rebound to
that exact student package.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services import content  # noqa: E402
from services.content import runtime_artifacts, workflow  # noqa: E402
from services.contracts.persona_v1 import (  # noqa: E402
    PersonaPackV1,
    sign_persona_pack,
)
from services.contracts.release_v2 import CourseReleaseManifestV5  # noqa: E402
from services.contracts.v1 import course_package_from_legacy  # noqa: E402


PRESERVED_MODULE_FIELDS = (
    "facts",
    "people",
    "source_refs",
    "qa_points",
    "level_goals",
    "saga_material",
    "sandbox_material",
    "seed_canvas",
)
COMPATIBILITY_NOTE = "学生端兼容发布："


def _student_text_view(payload: object) -> dict[str, object]:
    return {
        "title": getattr(payload, "title"),
        "abstract": getattr(payload, "abstract"),
        "body": list(getattr(payload, "body")),
        "course_title": getattr(payload, "course_title"),
        "era": getattr(payload, "era"),
        "era_id": getattr(payload, "era_id"),
        "section": getattr(payload, "section"),
        "lesson_no": getattr(payload, "lesson_no"),
        "duration": getattr(payload, "duration"),
        "keywords": [
            {
                "word": item.word,
                "pinyin": item.pinyin,
                "gloss": item.gloss,
            }
            for item in getattr(payload, "keywords")
        ],
        "map_points": [
            {
                "label": item.label,
                "region": item.region,
                "lat": item.lat,
                "lng": item.lng,
                "note": item.note,
                "kind": item.kind,
            }
            for item in getattr(payload, "map_points")
        ],
    }


def _as_teacher_draft(
    source: content.LessonContentPackage,
) -> content.LessonContentPackage:
    payload = source.model_dump(mode="json")
    payload.update(
        status="draft",
        version=0,
        sealed_at=None,
        sealed_by=None,
        checksum=None,
    )
    return content.LessonContentPackage.model_validate(payload)


def _advance_and_seal(
    lesson_id: str,
    *,
    author: str,
    reviewer: str,
) -> content.LessonContentPackage:
    record = workflow.get_workflow(lesson_id)
    if record is None:
        raise RuntimeError(f"No content workflow exists for {lesson_id}.")
    if record.state == "draft":
        record = workflow.validate_draft(lesson_id, actor=author)
    if record.state == "validated":
        record = workflow.submit_for_review(
            lesson_id,
            actor=author,
            note="Teacher lesson passed local preview and is ready for review.",
        )
    if record.state == "in_review":
        record = workflow.approve_draft(
            lesson_id,
            actor=reviewer,
            note="Teacher lesson identity, layout and source metadata verified.",
        )
    if record.state == "approved":
        return workflow.seal_approved_draft(lesson_id, actor=reviewer)[0]
    if record.state == "sealed" and record.sealed_version is not None:
        return content.get_sealed_package(lesson_id, record.sealed_version)
    raise RuntimeError(
        f"Cannot seal {lesson_id} from workflow state {record.state!r}."
    )


def _compatibility_draft(
    source: content.LessonContentPackage,
    previous: content.LessonContentPackage,
    *,
    source_pr: int,
) -> content.LessonContentPackage:
    payload = source.model_dump(mode="json")
    previous_payload = previous.model_dump(mode="json")
    for field in PRESERVED_MODULE_FIELDS:
        payload[field] = previous_payload[field]
    payload.update(
        status="draft",
        version=0,
        sealed_at=None,
        sealed_by=None,
        checksum=None,
        teacher_notes=(
            source.teacher_notes.rstrip()
            + "\n\n"
            + f"{COMPATIBILITY_NOTE}PR #{source_pr} 的标题、摘要、正文、关键词、"
            + "课时元数据与地图点已同步；练、问、创、人物和视频继续绑定"
            + "上一发布，等待单独适配。"
        ),
    )
    return content.LessonContentPackage.model_validate(payload)


def _rebound_persona(
    sealed: content.LessonContentPackage,
    current: CourseReleaseManifestV5,
    *,
    reviewer: str,
) -> PersonaPackV1:
    item = next(
        (candidate for candidate in current.items if candidate.lesson_id == sealed.lesson_id),
        None,
    )
    if item is None:
        raise RuntimeError(f"Active release does not contain {sealed.lesson_id}.")
    scenarios = tuple(
        (
            runtime_artifacts.load_runtime_scenario(descriptor),
            descriptor.artifact_id == item.primary_scenario_id,
        )
        for descriptor in item.scenarios
    )
    bound_course = runtime_artifacts.bind_course_package(
        course_package_from_legacy(sealed),
        scenarios,
    )
    previous = runtime_artifacts.load_release_persona(item.persona_pack)
    staged_versions = [
        record.descriptor.version
        for record in runtime_artifacts.list_staged_personas(pack_id=previous.pack_id)
    ]
    next_version = max([previous.pack_version, *staged_versions]) + 1
    now = datetime.now(timezone.utc)
    payload = previous.model_dump(mode="json")
    payload.update(
        pack_version=next_version,
        course_content_version=sealed.version,
        course_checksum=bound_course.checksum,
        created_at=now,
        sealed_at=now,
        sealed_by=reviewer,
        checksum="0" * 64,
    )
    return sign_persona_pack(PersonaPackV1.model_validate(payload))


def sync_teacher_lesson(
    content_root: Path,
    *,
    lesson_id: str,
    source_pr: int,
    source_commit: str,
    source_checksum: str,
    author: str,
    reviewer: str,
    publisher: str,
) -> dict[str, object]:
    content.configure(content_root)
    source_draft = content.get_draft(lesson_id)
    if source_draft is None:
        raise RuntimeError(f"Teacher draft not found: {lesson_id}.")
    provenance = source_draft.teacher_notes
    for label, value in (
        ("PR", f"PR #{source_pr}"),
        ("commit", source_commit),
        ("source checksum", source_checksum),
    ):
        if value not in provenance:
            raise RuntimeError(f"Teacher draft does not contain the expected {label}.")

    current = workflow.get_current_release(source_draft.course_id)
    if not isinstance(current, CourseReleaseManifestV5):
        raise RuntimeError("Text-first synchronization currently requires a V5 release.")
    current_item = next(
        (item for item in current.items if item.lesson_id == lesson_id),
        None,
    )
    if current_item is None:
        raise RuntimeError(f"Active release does not contain {lesson_id}.")
    current_resources = workflow.get_published_lesson_resources(
        source_draft.course_id,
        lesson_id,
    )
    if (
        source_commit in current.note
        and _student_text_view(current_resources.course_package)
        == _student_text_view(source_draft)
    ):
        exact_sources = [
            package
            for package in content.load_sealed_packages(latest_only=False)
            if package.lesson_id == lesson_id
            and source_commit in package.teacher_notes
            and COMPATIBILITY_NOTE not in package.teacher_notes
            and _student_text_view(package) == _student_text_view(source_draft)
        ]
        if COMPATIBILITY_NOTE in source_draft.teacher_notes and exact_sources:
            source_draft = _as_teacher_draft(
                max(exact_sources, key=lambda package: package.version)
            )
            content.save_draft(source_draft, saved_by=author)
            workflow.validate_draft(lesson_id, actor=author)
        return {
            "status": "already-published",
            "course_id": source_draft.course_id,
            "lesson_id": lesson_id,
            "title": source_draft.title,
            "source_pr": source_pr,
            "source_commit": source_commit,
            "source_checksum": source_checksum,
            "exact_source_version": (
                max((item.version for item in exact_sources), default=None)
            ),
            "student_source_version": current_item.content_version,
            "release_id": current.release_id,
            "release_no": current.release_no,
            "release_checksum": current.checksum,
            "parent_release_id": current.parent_release_id,
            "persona_version": (
                current_resources.persona_pack.pack_version
                if current_resources.persona_pack
                else None
            ),
            "persona_checksum": (
                current_resources.persona_pack.checksum
                if current_resources.persona_pack
                else None
            ),
            "pending_modules": ["practice", "ask", "create", "persona", "video"],
        }
    previous_source = content.get_sealed_package(
        lesson_id,
        current_item.content_version,
    )
    previous_manifest_checksum = current.checksum

    exact_source = _advance_and_seal(
        lesson_id,
        author=author,
        reviewer=reviewer,
    )
    compatibility = _compatibility_draft(
        exact_source,
        previous_source,
        source_pr=source_pr,
    )
    content.save_draft(compatibility, saved_by=author)
    compatibility_source = _advance_and_seal(
        lesson_id,
        author=author,
        reviewer=reviewer,
    )

    persona = _rebound_persona(
        compatibility_source,
        current,
        reviewer=reviewer,
    )
    staged_persona = runtime_artifacts.stage_persona_pack(persona)
    published, _ = workflow.publish_version(
        lesson_id,
        compatibility_source.version,
        actor=publisher,
        note=(
            f"PR #{source_pr} text synchronized from {source_commit}; pending "
            "practice, ask, create, persona semantics and video remain pinned."
        ),
        persona_selection=workflow.PersonaBundleReleaseSelection(
            lesson_id=lesson_id,
            pack_id=persona.pack_id,
            pack_version=persona.pack_version,
            pack_checksum=persona.checksum,
        ),
    )
    resources = workflow.get_published_lesson_resources(
        source_draft.course_id,
        lesson_id,
    )
    if (
        resources.course_package.title != exact_source.title
        or resources.course_package.abstract != exact_source.abstract
        or list(resources.course_package.body) != exact_source.body
    ):
        raise RuntimeError("Published student text does not match the sealed teacher source.")
    if published.parent_release_id != current.release_id:
        raise RuntimeError("The new release does not descend from the previous active release.")
    historical = workflow.get_release(source_draft.course_id, current.release_id)
    if historical.checksum != previous_manifest_checksum:
        raise RuntimeError("The previous immutable release changed during synchronization.")

    content.save_draft(_as_teacher_draft(source_draft), saved_by=author)
    restored = workflow.validate_draft(lesson_id, actor=author)
    if restored.validation is None or not restored.validation.valid:
        raise RuntimeError("The exact teacher source could not be restored after publication.")

    return {
        "status": "published",
        "course_id": source_draft.course_id,
        "lesson_id": lesson_id,
        "title": exact_source.title,
        "source_pr": source_pr,
        "source_commit": source_commit,
        "source_checksum": source_checksum,
        "exact_source_version": exact_source.version,
        "student_source_version": compatibility_source.version,
        "release_id": published.release_id,
        "release_no": published.release_no,
        "release_checksum": published.checksum,
        "parent_release_id": published.parent_release_id,
        "persona_version": staged_persona.descriptor.version,
        "persona_checksum": staged_persona.descriptor.checksum,
        "pending_modules": ["practice", "ask", "create", "persona", "video"],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish a reviewed teacher lesson as a V5 text-first revision."
    )
    parser.add_argument("lesson_id")
    parser.add_argument("--source-pr", type=int, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--source-checksum", required=True)
    parser.add_argument("--content-root", type=Path, default=PROJECT_ROOT / "content")
    parser.add_argument("--author", default="content-sync-author")
    parser.add_argument("--reviewer", default="content-sync-reviewer")
    parser.add_argument("--publisher", default="content-sync-publisher")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = sync_teacher_lesson(
        args.content_root,
        lesson_id=args.lesson_id,
        source_pr=args.source_pr,
        source_commit=args.source_commit,
        source_checksum=args.source_checksum,
        author=args.author,
        reviewer=args.reviewer,
        publisher=args.publisher,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
