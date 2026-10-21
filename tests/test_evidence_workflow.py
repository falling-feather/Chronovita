from __future__ import annotations

import hashlib
import shutil
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier, Thread

from services import content
from services.content import evidence_workflow, runtime_artifacts, workflow
from services.content_history import build_course_archive
from services.contracts.evidence_v1 import (
    EvidencePassageV1,
    EvidenceSourceV1,
    LessonPresentationV1,
    sign_evidence_contract,
)


class EvidenceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-evidence-workflow-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)
        content.configure(self.tmp_root)
        self.lesson = content.save_draft(
            self._course_draft(),
            saved_by="author-a",
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass
        content.configure()

    def test_evidence_lifecycle_enforces_cas_and_independent_review(self):
        draft, record = evidence_workflow.save_evidence_draft(
            self._evidence_draft(),
            saved_by="author-a",
        )
        self.assertEqual(draft.revision, 1)
        self.assertEqual(record.state, "draft")

        with self.assertRaises(evidence_workflow.EvidenceDraftConflict):
            evidence_workflow.save_evidence_draft(
                self._evidence_draft(),
                saved_by="author-a",
            )

        record, report = evidence_workflow.validate_evidence_draft(
            draft.corpus_id,
            actor="author-a",
        )
        self.assertTrue(report.valid)
        self.assertEqual(
            [item.severity for item in report.issues],
            ["warning", "warning"],
        )
        record = evidence_workflow.submit_evidence_for_review(
            draft.corpus_id,
            actor="author-a",
        )
        self.assertEqual(record.state, "in_review")
        with self.assertRaises(evidence_workflow.EvidenceInvalidTransition):
            evidence_workflow.review_evidence_draft(
                draft.corpus_id,
                actor="author-a",
                decision="approve",
            )

        approved = evidence_workflow.review_evidence_draft(
            draft.corpus_id,
            actor="reviewer-b",
            decision="approve",
        )
        self.assertEqual(approved.state, "approved")
        corpus, staged, sealed, idempotent = (
            evidence_workflow.seal_approved_evidence(
                draft.corpus_id,
                actor="publisher-c",
            )
        )
        self.assertFalse(idempotent)
        self.assertEqual(sealed.state, "sealed")
        self.assertEqual(staged.descriptor.checksum, corpus.checksum)

        repeated = evidence_workflow.seal_approved_evidence(
            draft.corpus_id,
            actor="publisher-c",
        )
        self.assertTrue(repeated[3])
        self.assertEqual(repeated[0], corpus)

    def test_parallel_evidence_save_has_one_cas_winner(self):
        draft, _ = evidence_workflow.save_evidence_draft(
            self._evidence_draft(),
            saved_by="author-a",
        )
        first = draft.model_copy(update={"title": "First update"})
        second = draft.model_copy(update={"title": "Second update"})
        barrier = Barrier(2)
        results: list[str] = []

        def save(candidate):
            barrier.wait()
            try:
                evidence_workflow.save_evidence_draft(
                    candidate,
                    saved_by="author-a",
                )
                results.append("saved")
            except evidence_workflow.EvidenceDraftConflict:
                results.append("conflict")

        threads = [Thread(target=save, args=(item,)) for item in (first, second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(results, ["saved", "conflict"])
        self.assertEqual(
            evidence_workflow.get_evidence_draft(draft.corpus_id).revision,
            2,
        )

    def test_v3_publish_preserves_supplements_and_rolls_back_exactly(self):
        corpus = self._sealed_evidence()
        presentation = self._presentation(version=1, marker=b"version-one")
        self._seal_course(version_text="Version one")

        release_v1, _ = workflow.publish_version(
            self.lesson.lesson_id,
            1,
            actor="publisher-c",
            evidence_selection=workflow.EvidenceReleaseSelection(
                corpus_id=corpus.corpus_id,
                corpus_version=corpus.corpus_version,
                corpus_checksum=corpus.checksum,
            ),
            presentation_selection=workflow.PresentationReleaseSelection(
                presentation_id=presentation.presentation_id,
                presentation_version=presentation.presentation_version,
                presentation_checksum=presentation.checksum,
            ),
        )
        self.assertEqual(release_v1.schema_version, "course-release/v3")
        resources = workflow.get_published_lesson_resources(
            self.lesson.course_id,
            self.lesson.lesson_id,
        )
        self.assertEqual(resources.evidence_corpus, corpus)
        self.assertEqual(resources.lesson_presentation, presentation)

        draft = content.get_draft(self.lesson.lesson_id)
        draft.body[0] = "Version two"
        content.save_draft(draft, saved_by="author-a")
        self._review_and_seal_course()
        release_v2, _ = workflow.publish_version(
            self.lesson.lesson_id,
            2,
            actor="publisher-c",
        )
        self.assertEqual(release_v2.schema_version, "course-release/v3")
        self.assertEqual(
            release_v2.items[0].lesson_presentation,
            release_v1.items[0].lesson_presentation,
        )

        presentation_v2 = self._presentation(version=2, marker=b"version-two")
        release_v3, _ = workflow.publish_version(
            self.lesson.lesson_id,
            2,
            actor="publisher-c",
            evidence_selection=workflow.EvidenceReleaseSelection(
                corpus_id=corpus.corpus_id,
                corpus_version=corpus.corpus_version,
                corpus_checksum=corpus.checksum,
            ),
            presentation_selection=workflow.PresentationReleaseSelection(
                presentation_id=presentation_v2.presentation_id,
                presentation_version=presentation_v2.presentation_version,
                presentation_checksum=presentation_v2.checksum,
            ),
        )
        self.assertNotEqual(
            release_v3.items[0].lesson_presentation.checksum,
            release_v1.items[0].lesson_presentation.checksum,
        )

        rolled_back = workflow.rollback_release(
            self.lesson.course_id,
            actor="publisher-c",
            target_release_id=release_v1.release_id,
        )
        self.assertEqual(rolled_back.schema_version, "course-release/v3")
        self.assertEqual(
            rolled_back.items[0].lesson_presentation,
            release_v1.items[0].lesson_presentation,
        )

    def test_corrupt_evidence_blocks_read_without_changing_active_pointer(self):
        corpus = self._sealed_evidence()
        presentation = self._presentation(version=1, marker=b"asset")
        self._seal_course(version_text="Version one")
        release, _ = workflow.publish_version(
            self.lesson.lesson_id,
            1,
            actor="publisher-c",
            evidence_selection=workflow.EvidenceReleaseSelection(
                corpus_id=corpus.corpus_id,
                corpus_version=1,
                corpus_checksum=corpus.checksum,
            ),
            presentation_selection=workflow.PresentationReleaseSelection(
                presentation_id=presentation.presentation_id,
                presentation_version=1,
                presentation_checksum=presentation.checksum,
            ),
        )
        evidence_path = self.tmp_root / Path(
            release.items[0].evidence_corpus.path
        )
        evidence_path.write_text("{}", encoding="utf-8")
        with self.assertRaises(content.ContentIntegrityError):
            workflow.get_published_lesson_resources(
                self.lesson.course_id,
                self.lesson.lesson_id,
            )
        pointer = workflow.get_current_release(self.lesson.course_id)
        self.assertEqual(pointer.release_id, release.release_id)

    def test_presentation_stage_uses_server_actor_and_media_tamper_fails_closed(self):
        corpus = self._sealed_evidence()
        presentation = self._presentation(
            version=1,
            marker=b"identity",
            sealed_by="client-claimed-actor",
            stage=False,
        )
        record = runtime_artifacts.stage_lesson_presentation(
            presentation,
            sealed_by="authenticated-publisher",
        )
        staged = runtime_artifacts.load_release_presentation(record.descriptor)
        self.assertEqual(staged.sealed_by, "authenticated-publisher")
        self.assertNotEqual(staged.checksum, presentation.checksum)

        self._seal_course(version_text="Media integrity")
        release, _ = workflow.publish_version(
            self.lesson.lesson_id,
            1,
            actor="publisher-c",
            evidence_selection=workflow.EvidenceReleaseSelection(
                corpus_id=corpus.corpus_id,
                corpus_version=1,
                corpus_checksum=corpus.checksum,
            ),
            presentation_selection=workflow.PresentationReleaseSelection(
                presentation_id=staged.presentation_id,
                presentation_version=1,
                presentation_checksum=staged.checksum,
            ),
        )
        video_path = self.tmp_root / Path(staged.video_path)
        video_path.write_bytes(b"tampered-video")
        with self.assertRaises(content.ContentIntegrityError):
            workflow.get_published_lesson_resources(
                self.lesson.course_id,
                self.lesson.lesson_id,
            )
        pointer = workflow.get_current_release(self.lesson.course_id)
        self.assertEqual(pointer.release_id, release.release_id)

    def test_parallel_v3_publication_has_one_pointer_winner(self):
        corpus = self._sealed_evidence()
        presentation_v1 = self._presentation(version=1, marker=b"first")
        presentation_v2 = self._presentation(version=2, marker=b"second")
        self._seal_course(version_text="Concurrent release")
        results: list[str] = []

        def publish(presentation):
            try:
                workflow.publish_version(
                    self.lesson.lesson_id,
                    1,
                    actor="publisher-c",
                    evidence_selection=workflow.EvidenceReleaseSelection(
                        corpus_id=corpus.corpus_id,
                        corpus_version=1,
                        corpus_checksum=corpus.checksum,
                    ),
                    presentation_selection=workflow.PresentationReleaseSelection(
                        presentation_id=presentation.presentation_id,
                        presentation_version=presentation.presentation_version,
                        presentation_checksum=presentation.checksum,
                    ),
                )
                results.append("published")
            except workflow.ContentConflict:
                results.append("conflict")

        threads = [
            Thread(target=publish, args=(presentation,))
            for presentation in (presentation_v1, presentation_v2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertCountEqual(results, ["published", "conflict"])
        active = workflow.get_current_release(self.lesson.course_id)
        self.assertEqual(active.schema_version, "course-release/v3")
        self.assertEqual(active.release_no, 2)

    def test_v3_archive_includes_exact_supplement_contracts(self):
        corpus = self._sealed_evidence()
        presentation = self._presentation(version=1, marker=b"archive")
        self._seal_course(version_text="Archive release")
        release, _ = workflow.publish_version(
            self.lesson.lesson_id,
            1,
            actor="publisher-c",
            evidence_selection=workflow.EvidenceReleaseSelection(
                corpus_id=corpus.corpus_id,
                corpus_version=1,
                corpus_checksum=corpus.checksum,
            ),
            presentation_selection=workflow.PresentationReleaseSelection(
                presentation_id=presentation.presentation_id,
                presentation_version=1,
                presentation_checksum=presentation.checksum,
            ),
        )
        archive = build_course_archive(
            self.lesson.course_id,
            release.release_id,
        )
        kinds = [item.kind for item in archive.manifest.files]
        self.assertEqual(kinds.count("evidence-corpus"), 1)
        self.assertEqual(kinds.count("lesson-presentation"), 1)
        evidence_file = next(
            item for item in archive.manifest.files if item.kind == "evidence-corpus"
        )
        presentation_file = next(
            item
            for item in archive.manifest.files
            if item.kind == "lesson-presentation"
        )
        self.assertEqual(evidence_file.contract_checksum, corpus.checksum)
        self.assertEqual(
            presentation_file.contract_checksum,
            presentation.checksum,
        )

    def _sealed_evidence(self):
        draft, _ = evidence_workflow.save_evidence_draft(
            self._evidence_draft(),
            saved_by="author-a",
        )
        evidence_workflow.validate_evidence_draft(
            draft.corpus_id,
            actor="author-a",
        )
        evidence_workflow.submit_evidence_for_review(
            draft.corpus_id,
            actor="author-a",
        )
        evidence_workflow.review_evidence_draft(
            draft.corpus_id,
            actor="reviewer-b",
            decision="approve",
        )
        return evidence_workflow.seal_approved_evidence(
            draft.corpus_id,
            actor="publisher-c",
        )[0]

    def _seal_course(self, *, version_text: str):
        draft = content.get_draft(self.lesson.lesson_id)
        draft.body[0] = version_text
        content.save_draft(draft, saved_by="author-a")
        self._review_and_seal_course()

    def _review_and_seal_course(self):
        workflow.validate_draft(self.lesson.lesson_id, actor="author-a")
        workflow.submit_for_review(self.lesson.lesson_id, actor="author-a")
        workflow.approve_draft(self.lesson.lesson_id, actor="reviewer-b")
        workflow.seal_approved_draft(self.lesson.lesson_id, actor="publisher-c")

    def _presentation(
        self,
        *,
        version: int,
        marker: bytes,
        sealed_by: str = "publisher-c",
        stage: bool = True,
    ):
        lesson_root = (
            self.tmp_root
            / "media"
            / "lessons"
            / self.lesson.lesson_id
            / f"v{version:03d}"
        )
        lesson_root.mkdir(parents=True, exist_ok=True)
        assets = {
            "video.mp4": marker + b"-video",
            "poster.webp": marker + b"-poster",
            "transcript.md": marker + b"-transcript",
        }
        for name, raw in assets.items():
            (lesson_root / name).write_bytes(raw)
        now = datetime.now(timezone.utc)
        provisional = LessonPresentationV1(
            presentation_id="presentation-test",
            course_id=self.lesson.course_id,
            lesson_id=self.lesson.lesson_id,
            presentation_version=version,
            title="Test presentation",
            estimated_minutes=39,
            phase_minutes={
                "observe": 9,
                "decide": 14,
                "consult": 7,
                "dossier": 9,
            },
            video_path=(
                f"media/lessons/{self.lesson.lesson_id}/v{version:03d}/video.mp4"
            ),
            poster_path=(
                f"media/lessons/{self.lesson.lesson_id}/v{version:03d}/poster.webp"
            ),
            transcript_path=(
                f"media/lessons/{self.lesson.lesson_id}/v{version:03d}/transcript.md"
            ),
            video_duration_seconds=50,
            video_sha256=hashlib.sha256(assets["video.mp4"]).hexdigest(),
            poster_sha256=hashlib.sha256(assets["poster.webp"]).hexdigest(),
            transcript_sha256=hashlib.sha256(
                assets["transcript.md"]
            ).hexdigest(),
            accessibility_note="Chinese captions and a local transcript are provided.",
            sealed_at=now,
            sealed_by=sealed_by,
            checksum="0" * 64,
        )
        presentation = sign_evidence_contract(provisional)
        if stage:
            runtime_artifacts.stage_lesson_presentation(presentation)
        return presentation

    def _evidence_draft(self):
        package = self._runtime_course()
        source = EvidenceSourceV1(
            source_id="source-test",
            title="Reviewed source",
            kind="research",
            url_or_path="https://example.test/source",
            rights_note="Self-authored summary for classroom use.",
        )
        passage = EvidencePassageV1(
            passage_id="passage-test",
            source_id=source.source_id,
            title="Evidence passage",
            text="A stable excerpt used only for workflow verification.",
            summary="Workflow verification summary.",
            fact_ids=(package.facts[0].fact_id,),
            person_ids=(package.people[0].person_id,),
            keywords=("test",),
            evidence_kind="teaching_explanation",
            certainty="interpretation",
            chronology_note="Modern teaching explanation.",
        )
        return evidence_workflow.EvidenceCorpusDraftV1(
            corpus_id="evidence-test",
            course_id=self.lesson.course_id,
            lesson_id=self.lesson.lesson_id,
            title="Evidence test corpus",
            scope_note="Only for the exact test lesson release.",
            sources=(source,),
            passages=(passage,),
        )

    def _runtime_course(self):
        from services.contracts.v1 import course_package_from_legacy

        return course_package_from_legacy(content.get_draft(self.lesson.lesson_id))

    @staticmethod
    def _course_draft():
        return content.LessonContentPackage(
            lesson_id="lesson-evidence",
            course_id="course-evidence",
            title="Evidence lesson",
            unit="Evidence course",
            course_title="Evidence course",
            era="Test era",
            body=["A reviewed teaching paragraph with enough words for validation."],
            keywords=[
                content.KeywordCard(word="evidence", gloss="A classroom keyword.")
            ],
            people=[
                content.PersonCard(
                    name="Test person",
                    role="Witness",
                    summary="A bounded teaching persona.",
                )
            ],
            facts=["A stable fact statement for evidence binding."],
            source_refs=[
                content.SourceRef(
                    title="Reviewed source",
                    source="Test institution",
                    url_or_path="https://example.test/source",
                    reliability="reviewed",
                )
            ],
            level_goals=["Distinguish evidence from interpretation."],
        )


if __name__ == "__main__":
    unittest.main()
