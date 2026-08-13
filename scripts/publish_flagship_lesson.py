"""Materialize a reviewed flagship lesson through the production workflows.

The command is intentionally narrow.  It installs one canonical source module,
uses distinct author/reviewer/publisher identities, then verifies the active V3
release.  Re-running an already published, byte-identical lesson is read-only.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services import content
from services.content import evidence_workflow, runtime_artifacts, scenario_authoring, workflow
from services.contracts import verify_contract_checksum
from services.content.flagships import (
    COURSE_ID,
    DAYU_CORPUS_ID,
    DAYU_PRESENTATION_ID,
    DAYU_SCENARIO_ID,
    LESSON_ID,
    build_dayu_course_draft,
    build_dayu_evidence_draft,
    build_dayu_presentation,
    build_dayu_scenario_draft,
)


@dataclass(frozen=True)
class Actors:
    author: str
    reviewer: str
    publisher: str


DAYU_ACTORS = Actors(
    author="content-author-dayu",
    reviewer="content-reviewer-dayu",
    publisher="content-publisher-admin",
)


def _assert_existing_dayu_matches_source(
    *,
    root: Path,
    content_item: object,
) -> None:
    sealed = content.get_sealed_package(
        LESSON_ID,
        content_item.content_version,
    )
    if content.draft_fingerprint(sealed) != content.draft_fingerprint(
        build_dayu_course_draft()
    ):
        raise RuntimeError(
            "The published L101 package differs from the canonical source; "
            "publish a new immutable content version instead of silently "
            "accepting source drift."
        )

    resources = workflow.get_published_lesson_resources(COURSE_ID, LESSON_ID)
    canonical_scenario = build_dayu_scenario_draft(build_dayu_course_draft())
    primary_descriptor = next(
        descriptor
        for descriptor in content_item.scenarios
        if descriptor.artifact_id == content_item.primary_scenario_id
    )
    sealed_scenario = runtime_artifacts.load_runtime_scenario(primary_descriptor)
    scenario_payload = sealed_scenario.model_dump(mode="json")
    for field in (
        "scenario_version",
        "status",
        "created_at",
        "updated_at",
        "sealed_at",
        "sealed_by",
        "checksum",
    ):
        scenario_payload.pop(field, None)
    if scenario_payload != canonical_scenario.contract_content():
        raise RuntimeError("The published L101 scenario differs from its source.")

    canonical_evidence = build_dayu_evidence_draft(build_dayu_course_draft())
    sealed_evidence = resources.evidence_corpus
    evidence_fields = (
        "corpus_id",
        "course_id",
        "lesson_id",
        "title",
        "scope_note",
        "sources",
        "passages",
    )
    evidence_payload = sealed_evidence.model_dump(
        mode="json",
        include=set(evidence_fields),
    )
    draft_payload = canonical_evidence.model_dump(
        mode="json",
        include=set(evidence_fields),
    )
    if evidence_payload != draft_payload:
        raise RuntimeError("The published L101 evidence differs from its source.")

    canonical_presentation = build_dayu_presentation(
        root,
        sealed_by=DAYU_ACTORS.publisher,
    )
    presentation_payload = resources.lesson_presentation.model_dump(mode="json")
    canonical_presentation_payload = canonical_presentation.model_dump(mode="json")
    for field in ("sealed_at", "checksum"):
        presentation_payload.pop(field, None)
        canonical_presentation_payload.pop(field, None)
    if not verify_contract_checksum(
        resources.lesson_presentation
    ) or presentation_payload != canonical_presentation_payload:
        raise RuntimeError("The published L101 presentation differs from local media.")


def publish_dayu(*, root: Path) -> dict[str, object]:
    content.configure(root)
    draft_source = build_dayu_course_draft()
    current = workflow.get_current_release(draft_source.course_id)
    if current is not None:
        item = next(
            (
                candidate
                for candidate in current.items
                if candidate.lesson_id == draft_source.lesson_id
            ),
            None,
        )
        if item is not None:
            _assert_existing_dayu_matches_source(root=root, content_item=item)
            resources = workflow.get_published_lesson_resources(
                draft_source.course_id,
                draft_source.lesson_id,
            )
            return {
                "status": "already-published",
                "release_id": current.release_id,
                "release_checksum": current.checksum,
                "content_version": item.content_version,
                "scenario_id": item.primary_scenario_id,
                "evidence_checksum": resources.evidence_corpus.checksum,
                "presentation_checksum": resources.lesson_presentation.checksum,
            }

    saved = content.save_draft(draft_source, saved_by=DAYU_ACTORS.author)
    validated = workflow.validate_draft(saved.lesson_id, actor=DAYU_ACTORS.author)
    if validated.validation is None or not validated.validation.valid:
        raise RuntimeError("Dayu course draft did not pass formal validation.")
    workflow.submit_for_review(
        saved.lesson_id,
        actor=DAYU_ACTORS.author,
        note="L101 正文、史实边界、人物、地图与课堂结构已完成，申请独立审校。",
    )
    workflow.approve_draft(
        saved.lesson_id,
        actor=DAYU_ACTORS.reviewer,
        note="已逐项核对传说、传世文献、考古判断和教学解释，批准封存。",
    )
    sealed_course, _, _ = workflow.seal_approved_draft(
        saved.lesson_id,
        actor=DAYU_ACTORS.publisher,
    )

    scenario_saved = scenario_authoring.save_scenario_draft(
        build_dayu_scenario_draft(saved),
        saved_by=DAYU_ACTORS.author,
    )
    scenario_report = scenario_authoring.validate_saved_scenario_draft(
        scenario_saved.scenario_id
    )
    if not scenario_report.valid:
        raise RuntimeError(
            "Dayu scenario did not validate: "
            + "; ".join(item.message for item in scenario_report.issues)
        )
    scenario, scenario_record, _ = scenario_authoring.seal_scenario_draft(
        scenario_saved.scenario_id,
        sealed_by=DAYU_ACTORS.publisher,
    )

    evidence_saved, _ = evidence_workflow.save_evidence_draft(
        build_dayu_evidence_draft(saved),
        saved_by=DAYU_ACTORS.author,
    )
    _, evidence_report = evidence_workflow.validate_evidence_draft(
        evidence_saved.corpus_id,
        actor=DAYU_ACTORS.author,
    )
    if not evidence_report.valid:
        raise RuntimeError("Dayu evidence corpus did not pass formal validation.")
    evidence_workflow.submit_evidence_for_review(
        evidence_saved.corpus_id,
        actor=DAYU_ACTORS.author,
        note="12 项来源与 30 个稳定片段已逐项绑定课程事实，申请独立审校。",
    )
    evidence_workflow.review_evidence_draft(
        evidence_saved.corpus_id,
        actor=DAYU_ACTORS.reviewer,
        decision="approve",
        note="来源年代、权利说明、事实与人物绑定及争议标记均已核对。",
    )
    evidence, evidence_record, _, _ = evidence_workflow.seal_approved_evidence(
        evidence_saved.corpus_id,
        actor=DAYU_ACTORS.publisher,
    )

    presentation = build_dayu_presentation(
        root,
        sealed_by=DAYU_ACTORS.publisher,
    )
    presentation_record = runtime_artifacts.stage_lesson_presentation(
        presentation,
        sealed_by=DAYU_ACTORS.publisher,
    )

    release, published_workflow = workflow.publish_version(
        sealed_course.lesson_id,
        sealed_course.version,
        actor=DAYU_ACTORS.publisher,
        note="发布 L101 大禹治水正式旗舰课：课程、六回合关卡、证据库与导读资源精确绑定。",
        scenario_selections=[
            workflow.ScenarioReleaseSelection(
                scenario_id=scenario.scenario_id,
                scenario_version=scenario.scenario_version,
                scenario_checksum=str(scenario.checksum),
                primary=True,
            )
        ],
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
    resources = workflow.get_published_lesson_resources(
        sealed_course.course_id,
        sealed_course.lesson_id,
    )
    if (
        release.schema_version != "course-release/v3"
        or published_workflow.state != "published"
        or resources.evidence_corpus.checksum != evidence.checksum
        or resources.lesson_presentation.checksum
        != presentation_record.descriptor.checksum
        or scenario_record.descriptor.artifact_id != DAYU_SCENARIO_ID
        or evidence_record.descriptor.artifact_id != DAYU_CORPUS_ID
        or presentation_record.descriptor.artifact_id != DAYU_PRESENTATION_ID
    ):
        raise RuntimeError("Dayu V3 publication postcondition failed.")
    return {
        "status": "published",
        "release_id": release.release_id,
        "release_checksum": release.checksum,
        "content_version": sealed_course.version,
        "content_checksum": sealed_course.checksum,
        "scenario_id": scenario.scenario_id,
        "scenario_checksum": scenario.checksum,
        "evidence_checksum": evidence.checksum,
        "presentation_checksum": presentation_record.descriptor.checksum,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("lesson", choices=("L101",))
    parser.add_argument(
        "--content-root",
        type=Path,
        default=Path("content"),
        help="Content root to materialize (default: repository content/).",
    )
    args = parser.parse_args()
    result = publish_dayu(root=args.content_root.resolve())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
