"""Bind the two classroom activities to the supplied teacher texts, preserving history."""
# ruff: noqa: E402 -- standalone CLI bootstraps the repository import path.
from __future__ import annotations

import argparse
import json
import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import content
from services.content import runtime_artifacts, workflow
from services.courses.textbooks import load_textbooks
from services.contracts.evidence_v1 import sign_evidence_contract
from services.contracts.evidence_v2 import EvidenceCorpusV2
from services.contracts.persona_v1 import PersonaPackV1, sign_persona_pack
from services.contracts.release_v2 import CourseReleaseItemV5
from services.contracts.v1 import ScenarioTemplateV1, calculate_contract_checksum, course_package_from_legacy

COURSE_ID = "C-prequin-state"
AUTHOR = "teaching-alignment-author"
REVIEWER = "teaching-alignment-technical-reviewer"
PUBLISHER = "teaching-alignment-admin"


def refresh_persona_scope(root: Path) -> dict:
    """Publish labelled teaching notes without expanding first-person testimony."""
    original = content.content_root()
    content.configure(root)
    try:
        active = workflow.get_current_release(COURSE_ID)
        selections = []
        for item in active.items:
            resources = workflow.get_published_lesson_resources(COURSE_ID, item.lesson_id)
            pack = resources.persona_pack
            data = pack.model_dump(mode="json")
            changed = False
            people = {person.person_id: person.name for person in resources.course_package.people}
            for profile in data["profiles"]:
                if people[profile["person_id"]] != "商鞅":
                    continue
                slots = {slot.slot_id for slot in resources.evidence_corpus.answer_slots
                         if slot.status == "supported" and slot.slot_id in {
                             "shangyang-slot-01-overview", "shangyang-slot-02-identity",
                             "shangyang-slot-03-chronology", "shangyang-slot-04-moving-wood",
                             "shangyang-slot-05-military-merit", "shangyang-slot-06-agriculture-war",
                             "shangyang-slot-07-collective-liability", "shangyang-slot-08-county-administration",
                             "shangyang-slot-09-land-system", "shangyang-slot-11-fangsheng",
                             "shangyang-slot-13-book-of-lord-shang", "shangyang-slot-15-evaluation"}}
                passages = {passage_id for slot in resources.evidence_corpus.answer_slots
                            if slot.slot_id in slots for passage_id in slot.passage_ids}
                uses = {entry["passage_id"]: entry for entry in profile["evidence_uses"]}
                for passage_id in passages:
                    uses.setdefault(passage_id, {"passage_id": passage_id, "mode": "historian_note"})
                revised_slots = sorted(set(profile["focus_answer_slot_ids"]) | slots)
                revised_uses = [uses[key] for key in sorted(uses)]
                changed = revised_slots != profile["focus_answer_slot_ids"] or revised_uses != profile["evidence_uses"]
                profile.update(focus_answer_slot_ids=revised_slots, evidence_uses=revised_uses)
            if changed:
                data.update(pack_version=pack.pack_version + 1, sealed_at=datetime.now(timezone.utc).isoformat(),
                            sealed_by=REVIEWER, checksum="0" * 64)
                descriptor = runtime_artifacts.stage_persona_pack(sign_persona_pack(PersonaPackV1.model_validate(data))).descriptor
            else:
                descriptor = item.persona_pack
            selections.append(workflow.PersonaBundleReleaseSelection(lesson_id=item.lesson_id,
                pack_id=descriptor.artifact_id, pack_version=descriptor.version, pack_checksum=descriptor.checksum))
        release = workflow.publish_persona_bundle_v1(COURSE_ID, selections, actor=PUBLISHER,
            note="补齐商鞅对改革措施的教学说明；新增材料仅作后人解释，不放宽人物原话或亲历边界。")
        return {"release_id": release.release_id, "lessons": [item.lesson_id for item in release.items]}
    finally:
        content.configure(original)


def signed_scenario(payload: dict) -> ScenarioTemplateV1:
    payload["checksum"] = "0" * 64
    model = ScenarioTemplateV1.model_validate(payload)
    payload["checksum"] = calculate_contract_checksum(model)
    return ScenarioTemplateV1.model_validate(payload)


def align(root: Path) -> dict:
    original = content.content_root()
    content.configure(root)
    saved_drafts = {}
    try:
        active = workflow.get_current_release(COURSE_ID)
        if {item.lesson_id for item in active.items} == {"L101", "L105"}:
            from services.courses import get_lesson
            if all(get_lesson(key).interaction_status == "ready" for key in ("L101", "L105")):
                return {"status": "already-aligned", "release_id": active.release_id}
        old_resources = {key: workflow.get_published_lesson_resources(COURSE_ID, key) for key in ("L101", "L103")}
        teacher = load_textbooks()[COURSE_ID]
        saved_drafts = {key: content.get_draft(key) for key in ("L101", "L105")}
        items = []
        now = datetime.now(timezone.utc).isoformat()
        for old_id, new_id in (("L101", "L101"), ("L103", "L105")):
            resources = old_resources[old_id]
            text = next(lesson for lesson in teacher.lessons if lesson.lesson_id == new_id)
            source = content.get_sealed_package(old_id, resources.content_version).model_dump(mode="json")
            source.update(lesson_id=new_id, title=text.title, abstract=text.abstract, body=text.body,
                keywords=[keyword.model_dump(mode="json") for keyword in text.keywords], lesson_no=text.lesson_no,
                course_title=teacher.title, era=teacher.era, era_id=teacher.era_id, section=teacher.section,
                teacher_notes=("教师 PR 正文保持原样；互动资料按新课号重签。程序完成结构与绑定验核，教学规则仍待教师最终验收。"))
            draft = content.save_draft(content.LessonContentPackage.model_validate(source), saved_by=AUTHOR)
            workflow.validate_draft(new_id, actor=AUTHOR)
            workflow.submit_for_review(new_id, actor=AUTHOR, note="绑定教师当前正文，不改写教师内容。")
            workflow.approve_draft(new_id, actor=REVIEWER, note="技术审校：身份、校验值与引用关系验核；不代替真人教学审课。")
            sealed, source_path, _ = workflow.seal_approved_draft(new_id, actor=REVIEWER)
            base = course_package_from_legacy(sealed)
            active_item = next(item for item in active.items if item.lesson_id == old_id)
            old_scenario = runtime_artifacts.load_runtime_scenario(next(item for item in active_item.scenarios if item.artifact_id == active_item.primary_scenario_id))
            scenario_data = old_scenario.model_dump(mode="json")
            scenario_data.update(lesson_id=new_id, scenario_version=old_scenario.scenario_version + 1,
                                 updated_at=now, sealed_at=now, sealed_by=REVIEWER)
            if old_id != new_id:
                scenario_data.update(scenario_id="shangyang-l105-institutional-reform", scenario_version=1)
            scenario = signed_scenario(scenario_data)
            runtime_artifacts.stage_scenario(scenario)
            package = runtime_artifacts.bind_course_package(base, ((scenario, True),))
            course_descriptor = runtime_artifacts.materialize_course_package(package)
            corpus_data = resources.evidence_corpus.model_dump(mode="json")
            corpus_data.update(lesson_id=new_id, corpus_version=resources.evidence_corpus.corpus_version + 1,
                               supersedes_checksum=resources.evidence_corpus.checksum, sealed_at=now, sealed_by=REVIEWER, checksum="0" * 64)
            if old_id != new_id:
                corpus_data.update(corpus_id="evidence-shangyang-l105", corpus_version=1)
            corpus = sign_evidence_contract(EvidenceCorpusV2.model_validate(corpus_data))
            runtime_artifacts.stage_evidence_corpus(corpus)
            presentation_data = resources.lesson_presentation.model_dump(mode="json")
            presentation_data.update(lesson_id=new_id, presentation_version=resources.lesson_presentation.presentation_version + 1,
                                     sealed_at=now, sealed_by=REVIEWER, checksum="0" * 64)
            if old_id != new_id:
                presentation_data.update(presentation_id="presentation-shangyang-l105", presentation_version=1)
            media_root = root / "media" / "lessons" / new_id / f"v{presentation_data['presentation_version']:03d}"
            media_root.mkdir(parents=True, exist_ok=True)
            for field in ("video_path", "poster_path", "transcript_path"):
                source_asset = root / presentation_data[field]
                destination = media_root / source_asset.name
                if destination.exists():
                    if destination.read_bytes() != source_asset.read_bytes():
                        raise ValueError("不可覆盖不同的已版本化媒体资料")
                else:
                    shutil.copyfile(source_asset, destination)
                presentation_data[field] = destination.relative_to(root).as_posix()
            presentation = sign_evidence_contract(type(resources.lesson_presentation).model_validate(presentation_data))
            runtime_artifacts.stage_lesson_presentation(presentation)
            persona_data = resources.persona_pack.model_dump(mode="json")
            persona_data.update(lesson_id=new_id, pack_version=resources.persona_pack.pack_version + 1,
                course_content_version=package.content_version, course_checksum=package.checksum,
                scenario_id=scenario.scenario_id, scenario_version=scenario.scenario_version, scenario_checksum=scenario.checksum,
                evidence_corpus_id=corpus.corpus_id, evidence_version=corpus.corpus_version, evidence_checksum=corpus.checksum,
                sealed_at=now, sealed_by=REVIEWER, checksum="0" * 64)
            if old_id != new_id:
                persona_data.update(pack_id="persona-shangyang-l105", pack_version=1)
            pack = sign_persona_pack(PersonaPackV1.model_validate(persona_data))
            runtime_artifacts.stage_persona_pack(pack)
            items.append(CourseReleaseItemV5(lesson_id=new_id, course_id=COURSE_ID, content_version=sealed.version,
                source_path=source_path.relative_to(root).as_posix(), source_checksum=sealed.checksum,
                course_package=course_descriptor, scenarios=(runtime_artifacts.descriptor_for_scenario(scenario),),
                primary_scenario_id=scenario.scenario_id, evidence_corpus=runtime_artifacts.descriptor_for_evidence(corpus),
                lesson_presentation=runtime_artifacts.descriptor_for_presentation(presentation), persona_pack=runtime_artifacts.descriptor_for_persona(pack)))
        release = workflow.publish_teaching_bundle(COURSE_ID, items, actor=PUBLISHER,
            note="L101 大禹与 L105 商鞅按教师新稿完成技术对齐；原 L103 发布保留供历史追溯。教学规则待最终真人验收。")
        return {"status": "aligned", "release_id": release.release_id, "release_no": release.release_no,
                "lessons": [item.lesson_id for item in release.items]}
    finally:
        # Publication uses an isolated sealed projection. Even an interrupted
        # preparation must not leave the teacher editor with replaced metadata.
        for draft in saved_drafts.values():
            if draft is not None:
                content.save_draft(draft, saved_by=AUTHOR)
        content.configure(original)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--content-root", type=Path, default=ROOT / "content")
    parser.add_argument("--refresh-personas", action="store_true")
    args = parser.parse_args()
    print(json.dumps((refresh_persona_scope if args.refresh_personas else align)(args.content_root.resolve()), ensure_ascii=False))
