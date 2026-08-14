"""Seal and publish the HyperFrames media for both flagship lessons.

The command upgrades only ``LessonPresentationV1``.  Course packages,
scenarios and evidence corpora remain bound to their current immutable
versions.  Re-running the command after a successful publication is
idempotent and does not create another release.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services import content
from services.content import runtime_artifacts, workflow
from services.content.flagships.dayu_l101 import (
    COURSE_ID,
    DAYU_PRESENTATION_ID,
    build_dayu_presentation,
)
from services.content.flagships.shangyang_l103 import (
    SHANGYANG_PRESENTATION_ID,
    build_shangyang_presentation,
)
from services.contracts.evidence_v1 import LessonPresentationV1


MEDIA_PUBLISHER = "content-publisher-admin"
PRESENTATION_VERSION = 2


@dataclass(frozen=True)
class FlagshipMedia:
    lesson_id: str
    presentation_id: str
    builder: Callable[..., LessonPresentationV1]
    publication_note: str


FLAGSHIP_MEDIA = (
    FlagshipMedia(
        lesson_id="L101",
        presentation_id=DAYU_PRESENTATION_ID,
        builder=build_dayu_presentation,
        publication_note=(
            "发布 L101 大禹治水 HyperFrames 课堂短片：保留课程、关卡与证据版本，"
            "将展示资源升级并精确绑定至 v002。"
        ),
    ),
    FlagshipMedia(
        lesson_id="L103",
        presentation_id=SHANGYANG_PRESENTATION_ID,
        builder=build_shangyang_presentation,
        publication_note=(
            "发布 L103 商鞅变法 HyperFrames 课堂短片：保留课程、关卡与证据版本，"
            "将展示资源升级并精确绑定至 v002。"
        ),
    ),
)


def _load_or_stage_presentation(
    media: FlagshipMedia,
    *,
    content_root: Path,
    presentation_version: int,
    actor: str,
) -> LessonPresentationV1:
    matches = [
        record
        for record in runtime_artifacts.list_staged_presentations(
            presentation_id=media.presentation_id
        )
        if record.descriptor.course_id == COURSE_ID
        and record.descriptor.lesson_id == media.lesson_id
        and record.descriptor.version == presentation_version
    ]
    if len(matches) > 1:
        raise RuntimeError(
            f"Multiple staged presentations use {media.presentation_id} "
            f"v{presentation_version}."
        )

    if matches:
        descriptor = matches[0].descriptor
        existing, _ = runtime_artifacts.load_lesson_presentation(
            course_id=descriptor.course_id,
            lesson_id=descriptor.lesson_id,
            presentation_id=descriptor.artifact_id,
            presentation_version=descriptor.version,
            presentation_checksum=descriptor.checksum,
        )
        expected = media.builder(
            content_root,
            sealed_by=existing.sealed_by,
            sealed_at=existing.sealed_at,
            presentation_version=presentation_version,
        )
        if expected != existing:
            raise RuntimeError(
                f"Staged {media.presentation_id} v{presentation_version} "
                "does not match the current source media or metadata."
            )
        return existing

    presentation = media.builder(
        content_root,
        sealed_by=actor,
        presentation_version=presentation_version,
    )
    staged = runtime_artifacts.stage_lesson_presentation(
        presentation,
        sealed_by=actor,
    )
    if staged.descriptor.checksum != presentation.checksum:
        raise RuntimeError("Staged presentation checksum changed unexpectedly.")
    return presentation


def publish_flagship_media(
    content_root: Path,
    *,
    presentation_version: int = PRESENTATION_VERSION,
    actor: str = MEDIA_PUBLISHER,
) -> dict[str, object]:
    root = content_root.resolve()
    content.configure(root)
    results: list[dict[str, object]] = []

    for media in FLAGSHIP_MEDIA:
        before = workflow.get_published_lesson_resources(COURSE_ID, media.lesson_id)
        presentation = _load_or_stage_presentation(
            media,
            content_root=root,
            presentation_version=presentation_version,
            actor=actor,
        )
        evidence = before.evidence_corpus
        release, record = workflow.publish_version(
            media.lesson_id,
            before.content_version,
            actor=actor,
            note=media.publication_note,
            evidence_selection=workflow.EvidenceReleaseSelection(
                corpus_id=evidence.corpus_id,
                corpus_version=evidence.corpus_version,
                corpus_checksum=evidence.checksum,
            ),
            presentation_selection=workflow.PresentationReleaseSelection(
                presentation_id=presentation.presentation_id,
                presentation_version=presentation.presentation_version,
                presentation_checksum=presentation.checksum,
            ),
        )
        after = workflow.get_published_lesson_resources(COURSE_ID, media.lesson_id)
        if (
            release.schema_version != "course-release/v3"
            or record.state != "published"
            or after.content_version != before.content_version
            or after.evidence_corpus.checksum != evidence.checksum
            or after.lesson_presentation.checksum != presentation.checksum
            or after.lesson_presentation.presentation_version
            != presentation_version
        ):
            raise RuntimeError(f"{media.lesson_id} media publication postcondition failed.")
        results.append(
            {
                "lesson_id": media.lesson_id,
                "release_id": release.release_id,
                "release_no": release.release_no,
                "release_checksum": release.checksum,
                "presentation_id": presentation.presentation_id,
                "presentation_version": presentation.presentation_version,
                "presentation_checksum": presentation.checksum,
                "evidence_checksum": evidence.checksum,
            }
        )

    final_release = workflow.get_current_release(COURSE_ID)
    if final_release is None or final_release.schema_version != "course-release/v3":
        raise RuntimeError("Final flagship release is not course-release/v3.")
    final_versions = {
        item.lesson_id: item.lesson_presentation.version
        for item in final_release.items
        if item.lesson_id in {media.lesson_id for media in FLAGSHIP_MEDIA}
    }
    if final_versions != {
        media.lesson_id: presentation_version for media in FLAGSHIP_MEDIA
    }:
        raise RuntimeError(
            "Final release does not bind both "
            f"v{presentation_version:03d} presentations."
        )

    return {
        "status": "published",
        "course_id": COURSE_ID,
        "presentation_version": presentation_version,
        "lessons": results,
        "final_release_id": final_release.release_id,
        "final_release_no": final_release.release_no,
        "final_release_checksum": final_release.checksum,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seal and publish both flagship HyperFrames presentations."
    )
    parser.add_argument(
        "--content-root",
        type=Path,
        default=PROJECT_ROOT / "content",
        help="Chronovita content root (default: repository content directory).",
    )
    parser.add_argument(
        "--presentation-version",
        type=int,
        default=PRESENTATION_VERSION,
        help="Immutable LessonPresentation version to publish (default: 2).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.presentation_version < 1:
        raise SystemExit("--presentation-version must be at least 1")
    result = publish_flagship_media(
        args.content_root,
        presentation_version=args.presentation_version,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
