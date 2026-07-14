import json
import shutil
import unittest
import uuid
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from pydantic import ValidationError

from services import content, courses
from services.content import workflow


class ContentWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-content-workflow-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)
        content.configure(self.tmp_root)

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass
        content.configure()

    def test_review_publish_second_version_and_rollback(self):
        draft = content.save_draft(self._package("workflow-lesson", "C-workflow", "Version one"), saved_by="author")
        self.assertEqual(workflow.get_workflow(draft.lesson_id).state, "draft")

        validated = workflow.validate_draft(draft.lesson_id, actor="author")
        self.assertEqual(validated.state, "validated")
        self.assertTrue(validated.validation.valid)
        self.assertIsNone(workflow.get_current_release(draft.course_id))

        submitted = workflow.submit_for_review(draft.lesson_id, actor="author")
        self.assertEqual(submitted.state, "in_review")
        returned = workflow.request_changes(
            draft.lesson_id,
            actor="reviewer",
            note="Clarify the opening paragraph.",
        )
        self.assertEqual(returned.state, "changes_requested")

        draft.body[0] = "Version one, revised after review."
        content.save_draft(draft, saved_by="author")
        self.assertEqual(workflow.get_workflow(draft.lesson_id).state, "draft")
        workflow.validate_draft(draft.lesson_id, actor="author")
        workflow.submit_for_review(draft.lesson_id, actor="author")
        approved = workflow.approve_draft(draft.lesson_id, actor="reviewer")
        self.assertEqual(approved.state, "approved")

        sealed_v1, _, sealed_record = workflow.seal_approved_draft(
            draft.lesson_id,
            actor="reviewer",
        )
        self.assertEqual(sealed_v1.version, 1)
        self.assertEqual(sealed_record.state, "sealed")
        self.assertEqual(workflow.load_published_packages(), [])
        self.assertIsNone(courses.get_lesson(draft.lesson_id))

        release_v1, published_v1 = workflow.publish_version(
            draft.lesson_id,
            1,
            actor="publisher",
            note="First classroom release.",
        )
        self.assertEqual(release_v1.release_no, 2)
        self.assertEqual(published_v1.state, "published")
        public_v1 = workflow.load_published_packages()
        self.assertEqual(len(public_v1), 1)
        self.assertEqual(public_v1[0].content_version, 1)
        self.assertEqual(public_v1[0].body[0], "Version one, revised after review.")
        self.assertEqual(courses.get_lesson(draft.lesson_id).content_status, "published")

        draft_v2 = content.get_draft(draft.lesson_id)
        draft_v2.body[0] = "Version two remains invisible until publish."
        content.save_draft(draft_v2, saved_by="author")
        workflow.validate_draft(draft.lesson_id, actor="author")
        workflow.submit_for_review(draft.lesson_id, actor="author")
        workflow.approve_draft(draft.lesson_id, actor="reviewer")
        sealed_v2, _, _ = workflow.seal_approved_draft(draft.lesson_id, actor="reviewer")
        self.assertEqual(sealed_v2.version, 2)
        self.assertEqual(workflow.load_published_packages()[0].content_version, 1)
        self.assertEqual(courses.get_lesson(draft.lesson_id).body[0], "Version one, revised after review.")

        release_v2, _ = workflow.publish_version(
            draft.lesson_id,
            2,
            actor="publisher",
        )
        self.assertEqual(release_v2.release_no, 3)
        self.assertEqual(workflow.load_published_packages()[0].content_version, 2)

        rollback = workflow.rollback_release(
            draft.course_id,
            actor="publisher",
            target_release_id=release_v1.release_id,
            note="Restore the reviewed first version.",
        )
        self.assertEqual(rollback.operation, "rollback")
        self.assertEqual(rollback.restored_from_release_id, release_v1.release_id)
        restored = workflow.load_published_packages()[0]
        self.assertEqual(restored.content_version, 1)
        self.assertEqual(courses.get_lesson(draft.lesson_id).content_version, 1)
        self.assertEqual(len(workflow.list_releases(draft.course_id)), 4)

        record = workflow.get_workflow(draft.lesson_id)
        self.assertEqual(record.state, "sealed")
        self.assertEqual(record.sealed_version, 2)
        self.assertEqual(record.published_version, 1)

        content.configure(self.tmp_root)
        self.assertEqual(workflow.load_published_packages()[0].content_version, 1)

    def test_invalid_or_stale_draft_cannot_advance(self):
        invalid = self._package("invalid-lesson", "C-invalid", "Body")
        invalid.body = []
        invalid.keywords = []
        invalid.people = []
        invalid.facts = []
        invalid.source_refs = []
        content.save_draft(invalid, saved_by="author")

        record = workflow.validate_draft(invalid.lesson_id, actor="author")
        self.assertEqual(record.state, "draft")
        self.assertFalse(record.validation.valid)
        self.assertGreaterEqual(
            len([issue for issue in record.validation.issues if issue.severity == "error"]),
            5,
        )
        with self.assertRaises(workflow.InvalidTransition):
            workflow.submit_for_review(invalid.lesson_id, actor="author")
        with self.assertRaises(workflow.InvalidTransition):
            workflow.seal_approved_draft(invalid.lesson_id, actor="reviewer")
        with self.assertRaises(workflow.InvalidTransition):
            content.seal_draft(invalid.lesson_id, sealed_by="reviewer")

        valid = content.save_draft(
            self._package("stale-approval", "C-invalid", "Approved body"),
            saved_by="author",
        )
        workflow.validate_draft(valid.lesson_id, actor="author")
        workflow.submit_for_review(valid.lesson_id, actor="author")
        workflow.approve_draft(valid.lesson_id, actor="reviewer")
        valid.body[0] = "Changed after approval"
        content.save_draft(valid, saved_by="author")
        with self.assertRaises(workflow.InvalidTransition):
            workflow.seal_approved_draft(valid.lesson_id, actor="reviewer")

    def test_seal_rechecks_approved_fingerprint_inside_content_lock(self):
        draft = content.save_draft(
            self._package("seal-race", "C-seal-race", "Approved body"),
            saved_by="author",
        )
        workflow.validate_draft(draft.lesson_id, actor="author")
        workflow.submit_for_review(draft.lesson_id, actor="author")
        approved = workflow.approve_draft(draft.lesson_id, actor="reviewer")
        original_seal = content._seal_draft_unchecked

        def replace_draft_before_seal(*args, **kwargs):
            changed = content.get_draft(draft.lesson_id)
            changed.body[0] = "Unapproved replacement"
            content.save_draft(changed, saved_by="concurrent-author")
            return original_seal(*args, **kwargs)

        with patch.object(
            content,
            "_seal_draft_unchecked",
            side_effect=replace_draft_before_seal,
        ):
            with self.assertRaises(workflow.ContentConflict):
                workflow.seal_approved_draft(draft.lesson_id, actor="reviewer")

        self.assertEqual(workflow.get_workflow(draft.lesson_id).state, "draft")
        self.assertNotEqual(
            content.draft_fingerprint(content.get_draft(draft.lesson_id)),
            approved.draft_fingerprint,
        )
        self.assertEqual(content.list_sealed(), [])

    def test_identical_save_preserves_approval_and_content_change_resets_it(self):
        draft = content.save_draft(
            self._package("repeat-save", "C-repeat-save", "Stable content"),
            saved_by="author",
        )
        workflow.validate_draft(draft.lesson_id, actor="author")
        workflow.submit_for_review(draft.lesson_id, actor="author")
        approved = workflow.approve_draft(draft.lesson_id, actor="reviewer")

        same_content = content.get_draft(draft.lesson_id)
        saved_again = content.save_draft(same_content, saved_by="author")
        preserved = workflow.get_workflow(draft.lesson_id)
        self.assertEqual(preserved.state, "approved")
        self.assertEqual(preserved.draft_fingerprint, approved.draft_fingerprint)
        self.assertEqual(saved_again.updated_at, content.get_draft(draft.lesson_id).updated_at)

        saved_again.body[0] = "Substantive revision"
        content.save_draft(saved_again, saved_by="author")
        reset = workflow.get_workflow(draft.lesson_id)
        self.assertEqual(reset.state, "draft")
        self.assertIsNone(reset.validation)

    def test_parallel_saves_keep_draft_and_workflow_fingerprint_aligned(self):
        first = self._package("parallel-save", "C-parallel-save", "First writer")
        second = self._package("parallel-save", "C-parallel-save", "Second writer")
        first_at_audit = Event()
        release_first = Event()
        second_done = Event()
        errors: list[BaseException] = []
        original_record = workflow.record_draft_saved

        def delayed_record(draft, *, actor):
            if draft.body[0] == "First writer":
                first_at_audit.set()
                if not release_first.wait(2):
                    raise TimeoutError("parallel save test did not release first writer")
            return original_record(draft, actor=actor)

        def save(payload, actor, done=None):
            try:
                content.save_draft(payload, saved_by=actor)
            except BaseException as exc:
                errors.append(exc)
            finally:
                if done:
                    done.set()

        with patch.object(workflow, "record_draft_saved", side_effect=delayed_record):
            first_thread = Thread(target=save, args=(first, "first-author"))
            first_thread.start()
            self.assertTrue(first_at_audit.wait(1))

            second_thread = Thread(
                target=save,
                args=(second, "second-author", second_done),
            )
            second_thread.start()
            self.assertFalse(second_done.wait(0.1))
            release_first.set()
            first_thread.join(2)
            second_thread.join(2)

        self.assertEqual(errors, [])
        final_draft = content.get_draft("parallel-save")
        final_workflow = workflow.get_workflow("parallel-save")
        self.assertEqual(final_draft.body[0], "Second writer")
        self.assertEqual(
            final_workflow.draft_fingerprint,
            content.draft_fingerprint(final_draft),
        )

    def test_release_is_course_scoped_and_tampering_fails_closed(self):
        first_release = self._publish("lesson-a", "C-course-a", "Course A body")
        second_release = self._publish("lesson-b", "C-course-b", "Course B body")
        self.assertEqual(
            {package.course_id for package in workflow.load_published_packages()},
            {"C-course-a", "C-course-b"},
        )

        workflow.rollback_release(
            "C-course-a",
            actor="publisher",
            target_release_id=first_release.parent_release_id,
        )
        remaining = workflow.load_published_packages()
        self.assertEqual([package.course_id for package in remaining], ["C-course-b"])
        self.assertEqual(workflow.get_current_release("C-course-b").release_id, second_release.release_id)

        source_path = content.sealed_dir() / "lesson-b-v001.json"
        raw = json.loads(source_path.read_text(encoding="utf-8"))
        raw["title"] = "Tampered title"
        source_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        with self.assertRaises(content.ContentIntegrityError):
            workflow.load_published_packages()

    def test_signed_metadata_must_match_its_canonical_path(self):
        release = self._publish("path-lesson", "C-path", "Canonical content")

        pointer_path = content.release_dir() / "active" / "C-path.json"
        misplaced_pointer = content.release_dir() / "active" / "C-other.json"
        shutil.copy2(pointer_path, misplaced_pointer)
        with self.assertRaises(content.ContentIntegrityError):
            workflow.load_published_packages()
        misplaced_pointer.unlink()

        manifest_path = (
            content.release_dir()
            / "manifests"
            / "C-path"
            / f"{release.release_id}.json"
        )
        misplaced_manifest_dir = content.release_dir() / "manifests" / "C-other"
        misplaced_manifest_dir.mkdir(parents=True)
        shutil.copy2(manifest_path, misplaced_manifest_dir / manifest_path.name)
        with self.assertRaises(content.ContentIntegrityError):
            workflow.list_releases()

        source_workflow = content.workflow_dir() / "path-lesson.json"
        shutil.copy2(source_workflow, content.workflow_dir() / "other-lesson.json")
        with self.assertRaises(content.ContentIntegrityError):
            workflow.get_workflow("other-lesson")
        with self.assertRaises(content.ContentIntegrityError):
            workflow.rollback_release(
                "C-path",
                actor="publisher",
                target_release_id=release.parent_release_id,
            )

        draft = content.get_draft("path-lesson")
        misplaced_draft = content.draft_dir() / "other-draft.json"
        misplaced_draft.write_text(
            json.dumps(draft.model_dump(mode="json"), ensure_ascii=False),
            encoding="utf-8",
        )
        with self.assertRaises(content.ContentIntegrityError):
            content.get_draft("other-draft")

    def test_sealed_content_requires_explicit_whitelisted_bootstrap(self):
        draft = content.save_draft(
            self._package("legacy-lesson", "C-legacy", "Legacy reviewed body"),
            saved_by="author",
        )
        workflow.validate_draft(draft.lesson_id, actor="author")
        workflow.submit_for_review(draft.lesson_id, actor="author")
        workflow.approve_draft(draft.lesson_id, actor="reviewer")
        workflow.seal_approved_draft(draft.lesson_id, actor="reviewer")
        (content.workflow_dir() / f"{draft.lesson_id}.json").unlink()

        self.assertEqual(workflow.load_published_packages(), [])
        self.assertIsNone(courses.get_lesson(draft.lesson_id))

        release = workflow.bootstrap_legacy_release(
            draft.course_id,
            [
                workflow.LegacyReleaseSelection(
                    lesson_id=draft.lesson_id,
                    content_version=1,
                )
            ],
            actor="migration-admin",
            note="Approved one-time migration.",
        )
        self.assertEqual(release.operation, "bootstrap")
        self.assertEqual(release.release_no, 1)
        self.assertEqual(release.created_by, "migration-admin")
        self.assertEqual(courses.get_lesson(draft.lesson_id).body[0], "Legacy reviewed body")

    def test_course_release_updates_every_lesson_workflow_projection(self):
        release_a = self._publish("shared-a", "C-shared", "First lesson")
        release_b = self._publish("shared-b", "C-shared", "Second lesson")

        record_a = workflow.get_workflow("shared-a")
        record_b = workflow.get_workflow("shared-b")
        self.assertEqual(record_a.published_release_id, release_b.release_id)
        self.assertEqual(record_b.published_release_id, release_b.release_id)
        self.assertEqual(record_a.state, "published")
        self.assertEqual(record_b.state, "published")

        rollback = workflow.rollback_release(
            "C-shared",
            actor="publisher",
            target_release_id=release_a.release_id,
        )
        record_a = workflow.get_workflow("shared-a")
        record_b = workflow.get_workflow("shared-b")
        self.assertEqual(record_a.published_release_id, rollback.release_id)
        self.assertIsNone(record_b.published_release_id)
        self.assertEqual(record_b.state, "sealed")

    def test_interrupted_projection_is_recovered_before_process_exit(self):
        release_v1 = self._publish("interrupt-lesson", "C-interrupt", "Version one")
        self._seal_next_version("interrupt-lesson", "Version two")
        before_record = workflow.get_workflow("interrupt-lesson")
        before_history = workflow.list_releases("C-interrupt")

        with patch.object(
            workflow,
            "_write_workflow",
            side_effect=SystemExit("injected process exit"),
        ):
            with self.assertRaises(SystemExit):
                workflow.publish_version("interrupt-lesson", 2, actor="publisher")

        self.assertEqual(
            workflow.get_current_release("C-interrupt").release_id,
            release_v1.release_id,
        )
        self.assertEqual(workflow.get_workflow("interrupt-lesson"), before_record)
        self.assertEqual(workflow.list_releases("C-interrupt"), before_history)
        self.assertEqual(list((content.release_dir() / "transactions").glob("*.json")), [])

    def test_persisted_release_transaction_is_recovered_on_startup(self):
        release_v1 = self._publish("restart-lesson", "C-restart", "Version one")
        self._seal_next_version("restart-lesson", "Version two")
        before_record = workflow.get_workflow("restart-lesson")

        with patch.object(
            workflow,
            "_write_workflow",
            side_effect=SystemExit("injected process exit"),
        ), patch.object(
            workflow,
            "_recover_release_transaction",
            side_effect=SystemExit("simulate hard process termination"),
        ):
            with self.assertRaises(SystemExit):
                workflow.publish_version("restart-lesson", 2, actor="publisher")

        transactions = list((content.release_dir() / "transactions").glob("*.json"))
        self.assertEqual(len(transactions), 1)
        workflow.recover_pending_release_transactions()

        self.assertEqual(
            workflow.get_current_release("C-restart").release_id,
            release_v1.release_id,
        )
        self.assertEqual(workflow.get_workflow("restart-lesson"), before_record)
        self.assertEqual(list((content.release_dir() / "transactions").glob("*.json")), [])

    def test_uncommitted_manifest_is_not_exposed_as_release_history(self):
        current = self._publish("orphan-lesson", "C-orphan", "Published body")
        orphan, _ = workflow._write_release_manifest(
            course_id="C-orphan",
            operation="publish",
            items=current.items,
            actor="interrupted-publisher",
            note="Manifest written before an interrupted commit.",
            parent=current,
        )

        self.assertNotIn(
            orphan.release_id,
            {release.release_id for release in workflow.list_releases("C-orphan")},
        )
        with self.assertRaises(workflow.ContentNotFound):
            workflow.get_release("C-orphan", orphan.release_id)

    def test_rollback_revalidates_historical_artifacts_before_activation(self):
        release_v1 = self._publish("rollback-check", "C-rollback-check", "Version one")
        self._seal_next_version("rollback-check", "Version two")
        release_v2, _ = workflow.publish_version(
            "rollback-check",
            2,
            actor="publisher",
        )
        package_path = content.package_dir() / "rollback-check-v001.json"
        raw = json.loads(package_path.read_text(encoding="utf-8"))
        raw["title"] = "Tampered historical package"
        package_path.write_text(json.dumps(raw), encoding="utf-8")

        with self.assertRaises(content.ContentIntegrityError):
            workflow.rollback_release(
                "C-rollback-check",
                actor="publisher",
                target_release_id=release_v1.release_id,
            )

        self.assertEqual(
            workflow.get_current_release("C-rollback-check").release_id,
            release_v2.release_id,
        )

    def test_cross_course_duplicate_lesson_id_is_rejected_before_activation(self):
        draft = content.save_draft(
            self._package("global-lesson", "C-global-a", "Legacy version"),
            saved_by="author",
        )
        workflow.validate_draft(draft.lesson_id, actor="author")
        workflow.submit_for_review(draft.lesson_id, actor="author")
        workflow.approve_draft(draft.lesson_id, actor="reviewer")
        workflow.seal_approved_draft(draft.lesson_id, actor="reviewer")
        (content.workflow_dir() / "global-lesson.json").unlink()
        release_a = workflow.bootstrap_legacy_release(
            "C-global-a",
            [workflow.LegacyReleaseSelection(lesson_id="global-lesson", content_version=1)],
            actor="migrator",
        )

        draft.course_id = "C-global-b"
        draft.body[0] = "New course version"
        content.save_draft(draft, saved_by="author")
        workflow.validate_draft(draft.lesson_id, actor="author")
        workflow.submit_for_review(draft.lesson_id, actor="author")
        workflow.approve_draft(draft.lesson_id, actor="reviewer")
        workflow.seal_approved_draft(draft.lesson_id, actor="reviewer")

        with self.assertRaises(workflow.ContentConflict):
            workflow.publish_version("global-lesson", 2, actor="publisher")

        self.assertEqual(
            workflow.get_current_release("C-global-a").release_id,
            release_a.release_id,
        )
        self.assertIsNone(workflow.get_current_release("C-global-b"))
        published = workflow.load_published_packages()
        self.assertEqual([(item.course_id, item.lesson_id) for item in published], [
            ("C-global-a", "global-lesson")
        ])

    def test_missing_active_source_is_reported_as_integrity_failure(self):
        self._publish("missing-source", "C-missing-source", "Published body")
        (content.sealed_dir() / "missing-source-v001.json").unlink()

        with self.assertRaises(content.ContentIntegrityError):
            workflow.load_published_packages()

    def test_public_pointer_does_not_move_when_workflow_projection_fails(self):
        release_v1 = self._publish("atomic-lesson", "C-atomic", "Version one")
        self._seal_next_version("atomic-lesson", "Version two")
        before_record = workflow.get_workflow("atomic-lesson")
        before_history = workflow.list_releases("C-atomic")

        with patch.object(workflow, "_write_workflow", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                workflow.publish_version("atomic-lesson", 2, actor="publisher")

        self.assertEqual(
            workflow.get_current_release("C-atomic").release_id,
            release_v1.release_id,
        )
        self.assertEqual(workflow.get_workflow("atomic-lesson"), before_record)
        self.assertEqual(workflow.list_releases("C-atomic"), before_history)
        self.assertEqual(courses.get_lesson("atomic-lesson").body[0], "Version one")

    def test_failed_first_publish_removes_uncommitted_baseline_and_release(self):
        draft = content.save_draft(
            self._package("first-atomic", "C-first-atomic", "First version"),
            saved_by="author",
        )
        workflow.validate_draft(draft.lesson_id, actor="author")
        workflow.submit_for_review(draft.lesson_id, actor="author")
        workflow.approve_draft(draft.lesson_id, actor="reviewer")
        workflow.seal_approved_draft(draft.lesson_id, actor="reviewer")

        with patch.object(workflow, "_write_workflow", side_effect=OSError("injected")):
            with self.assertRaises(OSError):
                workflow.publish_version(draft.lesson_id, 1, actor="publisher")

        self.assertIsNone(workflow.get_current_release(draft.course_id))
        self.assertEqual(workflow.list_releases(draft.course_id), [])
        self.assertIsNone(courses.get_lesson(draft.lesson_id))

    def test_public_pointer_does_not_move_when_atomic_activation_fails(self):
        release_v1 = self._publish("pointer-lesson", "C-pointer", "Version one")
        self._seal_next_version("pointer-lesson", "Version two")
        before_record = workflow.get_workflow("pointer-lesson")
        pointer_path = content.release_dir() / "active" / "C-pointer.json"
        original_write = content._atomic_write_json

        def fail_active_pointer(path, payload, **kwargs):
            if Path(path).resolve() == pointer_path.resolve():
                raise OSError("injected pointer failure")
            return original_write(path, payload, **kwargs)

        with patch.object(content, "_atomic_write_json", side_effect=fail_active_pointer):
            with self.assertRaises(OSError):
                workflow.publish_version("pointer-lesson", 2, actor="publisher")

        self.assertEqual(
            workflow.get_current_release("C-pointer").release_id,
            release_v1.release_id,
        )
        self.assertEqual(workflow.get_workflow("pointer-lesson"), before_record)
        self.assertEqual(courses.get_lesson("pointer-lesson").body[0], "Version one")

    def test_manifest_pointer_and_canonical_package_tampering_fail_closed(self):
        release = self._publish("tamper-lesson", "C-tamper", "Trusted content")
        pointer_path = content.release_dir() / "active" / "C-tamper.json"
        manifest_path = (
            content.release_dir()
            / "manifests"
            / "C-tamper"
            / f"{release.release_id}.json"
        )
        package_path = content.package_dir() / "tamper-lesson-v001.json"

        for path, field, value in (
            (pointer_path, "generation", 999),
            (manifest_path, "note", "tampered"),
            (package_path, "title", "tampered"),
        ):
            original = path.read_text(encoding="utf-8")
            raw = json.loads(original)
            raw[field] = value
            path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(content.ContentIntegrityError):
                workflow.load_published_packages()
            path.write_text(original, encoding="utf-8")

    def test_content_models_reject_unknown_fields(self):
        raw = self._package("strict-content", "C-strict", "Body").model_dump(mode="json")
        raw["titel"] = "typo"
        with self.assertRaises(ValidationError):
            content.LessonContentPackage.model_validate(raw)

    def _publish(self, lesson_id: str, course_id: str, body: str):
        content.save_draft(self._package(lesson_id, course_id, body), saved_by="author")
        workflow.validate_draft(lesson_id, actor="author")
        workflow.submit_for_review(lesson_id, actor="author")
        workflow.approve_draft(lesson_id, actor="reviewer")
        workflow.seal_approved_draft(lesson_id, actor="reviewer")
        release, _ = workflow.publish_version(lesson_id, 1, actor="publisher")
        return release

    def _seal_next_version(self, lesson_id: str, body: str):
        draft = content.get_draft(lesson_id)
        draft.body[0] = body
        content.save_draft(draft, saved_by="author")
        workflow.validate_draft(lesson_id, actor="author")
        workflow.submit_for_review(lesson_id, actor="author")
        workflow.approve_draft(lesson_id, actor="reviewer")
        workflow.seal_approved_draft(lesson_id, actor="reviewer")

    @staticmethod
    def _package(lesson_id: str, course_id: str, body: str):
        package = content.content_template()
        package.lesson_id = lesson_id
        package.course_id = course_id
        package.course_title = f"Course {course_id}"
        package.title = f"Lesson {lesson_id}"
        package.unit = f"Unit {course_id}"
        package.era = "Test era"
        package.body = [body, "Second paragraph.", "Third paragraph."]
        return package


if __name__ == "__main__":
    unittest.main()
