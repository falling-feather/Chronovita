from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Thread, current_thread, local
import unittest
from unittest.mock import patch

from services import content
from services.content import runtime_artifacts, workflow
from services.contracts.evidence_v1 import sign_evidence_contract
from services.contracts.evidence_v2 import EvidenceCorpusV2
from services.contracts.persona_v1 import PersonaPackV1, sign_persona_pack
from services.contracts.release_v2 import CourseReleaseManifestV5
from scripts import publish_flagship_agent_bundle as flagship_publisher


COURSE_ID = "C-prequin-state"
REPOSITORY_CONTENT = Path(__file__).resolve().parents[1] / "content"


def _copy_published_content(target: Path) -> None:
    for name in ("media", "releases", "runtime", "sealed", "workflows"):
        shutil.copytree(REPOSITORY_CONTENT / name, target / name)


def _replacement_bundle(
    resources: workflow.PublishedLessonResources,
) -> tuple[EvidenceCorpusV2, PersonaPackV1]:
    current_corpus = resources.evidence_corpus
    current_pack = resources.persona_pack
    assert isinstance(current_corpus, EvidenceCorpusV2)
    assert isinstance(current_pack, PersonaPackV1)

    evidence_payload = current_corpus.model_dump(mode="json")
    evidence_payload.update(
        corpus_version=current_corpus.corpus_version + 1,
        title=f"{current_corpus.title} · 联合重签测试",
        supersedes_checksum=current_corpus.checksum,
        checksum="0" * 64,
    )
    corpus = sign_evidence_contract(
        EvidenceCorpusV2.model_validate(evidence_payload)
    )

    persona_payload = current_pack.model_dump(mode="json")
    persona_payload.update(
        pack_version=current_pack.pack_version + 1,
        evidence_corpus_id=corpus.corpus_id,
        evidence_version=corpus.corpus_version,
        evidence_checksum=corpus.checksum,
        checksum="0" * 64,
    )
    pack = sign_persona_pack(PersonaPackV1.model_validate(persona_payload))
    return corpus, pack


def _selection(
    corpus: EvidenceCorpusV2,
    pack: PersonaPackV1,
) -> workflow.EvidencePersonaBundleReleaseSelection:
    return workflow.EvidencePersonaBundleReleaseSelection(
        lesson_id=corpus.lesson_id,
        corpus_id=corpus.corpus_id,
        corpus_version=corpus.corpus_version,
        corpus_checksum=corpus.checksum,
        evidence_schema_version="evidence-corpus/v2",
        pack_id=pack.pack_id,
        pack_version=pack.pack_version,
        pack_checksum=pack.checksum,
    )


def _active_bundle(
    lesson_id: str,
) -> tuple[EvidenceCorpusV2, PersonaPackV1]:
    resources = workflow.get_published_lesson_resources(COURSE_ID, lesson_id)
    assert isinstance(resources.evidence_corpus, EvidenceCorpusV2)
    assert isinstance(resources.persona_pack, PersonaPackV1)
    return resources.evidence_corpus, resources.persona_pack


class EvidencePersonaBundleReleaseTests(unittest.TestCase):
    def test_changed_lesson_and_exact_replay_activate_once_and_rerun_idempotently(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _copy_published_content(root)
            content.configure(root)
            try:
                previous = workflow.get_current_release(COURSE_ID)
                self.assertIsInstance(previous, CourseReleaseManifestV5)
                assert isinstance(previous, CourseReleaseManifestV5)
                before_manifests = tuple(workflow.list_releases(COURSE_ID))

                dayu = _replacement_bundle(
                    workflow.get_published_lesson_resources(COURSE_ID, "L101")
                )
                shangyang = _active_bundle("L103")
                runtime_artifacts.stage_evidence_corpus(dayu[0])
                runtime_artifacts.stage_persona_pack(dayu[1])
                selections = (
                    _selection(*dayu),
                    _selection(*shangyang),
                )

                published = workflow.publish_evidence_persona_bundle_v1(
                    COURSE_ID,
                    selections,
                    actor="content-publisher-admin",
                    note="联合重签并原子发布。",
                )

                self.assertIsInstance(published, CourseReleaseManifestV5)
                self.assertEqual(published.release_no, previous.release_no + 1)
                self.assertEqual(published.parent_release_id, previous.release_id)
                self.assertEqual(
                    workflow.get_published_lesson_resources(
                        COURSE_ID, "L101"
                    ).evidence_corpus,
                    dayu[0],
                )
                self.assertEqual(
                    workflow.get_published_lesson_resources(
                        COURSE_ID, "L101"
                    ).persona_pack,
                    dayu[1],
                )
                self.assertEqual(_active_bundle("L103"), shangyang)

                pointer_path = root / "releases" / "active" / f"{COURSE_ID}.json"
                pointer_after_publish = pointer_path.read_bytes()
                replay = workflow.publish_evidence_persona_bundle_v1(
                    COURSE_ID,
                    selections,
                    actor="content-publisher-admin",
                )
                self.assertEqual(replay, published)
                self.assertEqual(pointer_path.read_bytes(), pointer_after_publish)
                self.assertEqual(
                    len(workflow.list_releases(COURSE_ID)),
                    len(before_manifests) + 1,
                )
            finally:
                content.configure()

    def test_incomplete_unsorted_stale_or_mismatched_bundle_never_moves_pointer(
        self,
    ) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _copy_published_content(root)
            content.configure(root)
            try:
                dayu = _replacement_bundle(
                    workflow.get_published_lesson_resources(COURSE_ID, "L101")
                )
                shangyang = _active_bundle("L103")
                runtime_artifacts.stage_evidence_corpus(dayu[0])
                runtime_artifacts.stage_persona_pack(dayu[1])
                selections = (_selection(*dayu), _selection(*shangyang))
                pointer_path = root / "releases" / "active" / f"{COURSE_ID}.json"
                before_pointer = pointer_path.read_bytes()
                before_manifests = tuple(workflow.list_releases(COURSE_ID))

                with self.assertRaisesRegex(
                    workflow.ContentValidationFailed, "every lesson"
                ):
                    workflow.publish_evidence_persona_bundle_v1(
                        COURSE_ID,
                        selections[:1],
                        actor="content-publisher-admin",
                    )
                with self.assertRaisesRegex(
                    workflow.ContentValidationFailed, "unique and sorted"
                ):
                    workflow.publish_evidence_persona_bundle_v1(
                        COURSE_ID,
                        tuple(reversed(selections)),
                        actor="content-publisher-admin",
                    )

                stale_payload = dayu[0].model_dump(mode="json")
                stale_payload.update(
                    corpus_version=dayu[0].corpus_version + 1,
                    supersedes_checksum="f" * 64,
                    checksum="0" * 64,
                )
                stale_corpus = sign_evidence_contract(
                    EvidenceCorpusV2.model_validate(stale_payload)
                )
                stale_pack_payload = dayu[1].model_dump(mode="json")
                stale_pack_payload.update(
                    pack_version=dayu[1].pack_version + 1,
                    evidence_version=stale_corpus.corpus_version,
                    evidence_checksum=stale_corpus.checksum,
                    checksum="0" * 64,
                )
                stale_pack = sign_persona_pack(
                    PersonaPackV1.model_validate(stale_pack_payload)
                )
                runtime_artifacts.stage_evidence_corpus(stale_corpus)
                runtime_artifacts.stage_persona_pack(stale_pack)
                with self.assertRaisesRegex(
                    workflow.ContentConflict, "does not supersede"
                ):
                    workflow.publish_evidence_persona_bundle_v1(
                        COURSE_ID,
                        (_selection(stale_corpus, stale_pack), selections[1]),
                        actor="content-publisher-admin",
                    )

                with self.assertRaisesRegex(
                    workflow.ContentValidationFailed, "exact published"
                ):
                    dayu_active_pack = _active_bundle("L101")[1]
                    workflow.publish_evidence_persona_bundle_v1(
                        COURSE_ID,
                        (_selection(dayu[0], dayu_active_pack), selections[1]),
                        actor="content-publisher-admin",
                    )

                self.assertEqual(pointer_path.read_bytes(), before_pointer)
                self.assertEqual(tuple(workflow.list_releases(COURSE_ID)), before_manifests)
            finally:
                content.configure()

    def test_concurrent_joint_publication_has_one_pointer_winner(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _copy_published_content(root)
            content.configure(root)
            try:
                dayu = _replacement_bundle(
                    workflow.get_published_lesson_resources(COURSE_ID, "L101")
                )
                shangyang = _active_bundle("L103")
                runtime_artifacts.stage_evidence_corpus(dayu[0])
                runtime_artifacts.stage_persona_pack(dayu[1])
                selections = (_selection(*dayu), _selection(*shangyang))
                barrier = Barrier(2)
                thread_state = local()
                main_thread = current_thread()
                original_load_pointer = workflow._load_pointer
                results: list[CourseReleaseManifestV5] = []
                errors: list[BaseException] = []

                def synchronized_load_pointer(course_id, required=True):
                    result = original_load_pointer(course_id, required=required)
                    if current_thread() is not main_thread and not getattr(
                        thread_state, "arrived", False
                    ):
                        thread_state.arrived = True
                        barrier.wait(2)
                    return result

                def publish() -> None:
                    try:
                        results.append(
                            workflow.publish_evidence_persona_bundle_v1(
                                COURSE_ID,
                                selections,
                                actor="content-publisher-admin",
                            )
                        )
                    except BaseException as exc:
                        errors.append(exc)

                with patch.object(
                    workflow,
                    "_load_pointer",
                    side_effect=synchronized_load_pointer,
                ):
                    threads = [Thread(target=publish) for _ in range(2)]
                    for thread in threads:
                        thread.start()
                    for thread in threads:
                        thread.join(10)

                self.assertTrue(all(not thread.is_alive() for thread in threads))
                self.assertEqual(len(results), 1)
                self.assertEqual(len(errors), 1)
                self.assertIsInstance(errors[0], workflow.ContentConflict)
                self.assertEqual(
                    workflow.get_current_release(COURSE_ID), results[0]
                )
            finally:
                content.configure()

    def test_flagship_script_returns_structured_idempotent_result(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _copy_published_content(root)
            content.configure(root)
            try:
                pointer = root / "releases/active/C-prequin-state.json"
                pointer_before = pointer.read_bytes()
                release_count_before = len(workflow.list_releases(COURSE_ID))
                result = flagship_publisher.publish_flagship_agent_bundle(root)

                self.assertEqual(
                    result["schema_version"],
                    "flagship-agent-bundle-publication/v1",
                )
                self.assertEqual(result["status"], "already-published")
                self.assertEqual(result["course_id"], COURSE_ID)
                self.assertEqual(
                    [item["lesson_id"] for item in result["artifacts"]],
                    ["L101", "L103"],
                )
                self.assertEqual(
                    result["release"]["release_id"],
                    workflow.get_current_release(COURSE_ID).release_id,
                )
                self.assertEqual(pointer.read_bytes(), pointer_before)
                self.assertEqual(
                    len(workflow.list_releases(COURSE_ID)),
                    release_count_before,
                )
            finally:
                content.configure()


if __name__ == "__main__":
    unittest.main()
