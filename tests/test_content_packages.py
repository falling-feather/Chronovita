import shutil
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread
from unittest.mock import patch

from pydantic import ValidationError

from services import content, courses
from services.content import runtime_artifacts
from services.content import scenario_authoring
from services.content import workflow


class ContentPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-content-package-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass
        content.configure()

    def test_legacy_sealed_content_requires_explicit_release(self):
        content.configure(self.tmp_root)
        payload = content.content_template()
        payload.lesson_id = "unit-test-lesson"
        payload.course_id = "C-unit-test"
        payload.title = "Unit Test Lesson"
        payload.unit = "Unit Test Course"
        payload.era = "Test Era"
        payload.body = ["The sealed body should be readable by the public course service."]

        draft = content.save_draft(payload)
        sealed = draft.model_copy(deep=True)
        sealed.status = "sealed"
        sealed.version = 1
        sealed.sealed_at = datetime.now(timezone.utc)
        sealed.sealed_by = "legacy-tester"
        sealed.updated_at = sealed.sealed_at
        sealed.checksum = content.package_checksum(sealed)
        sealed = content.LessonContentPackage.model_validate(sealed.model_dump(mode="json"))
        path = content.sealed_dir() / "unit-test-lesson-v001.json"
        content._atomic_write_json(path, sealed.model_dump(mode="json"), overwrite=False)

        self.assertEqual(draft.status, "draft")
        self.assertEqual(sealed.status, "sealed")
        self.assertEqual(sealed.version, 1)
        self.assertTrue(sealed.checksum)
        self.assertTrue(path.exists())

        self.assertIsNone(courses.get_course("C-unit-test"))
        self.assertIsNone(courses.get_lesson("unit-test-lesson"))
        self.assertIsNone(workflow.get_current_release("C-unit-test"))

        release = workflow.bootstrap_legacy_release(
            "C-unit-test",
            [
                workflow.LegacyReleaseSelection(
                    lesson_id="unit-test-lesson",
                    content_version=1,
                )
            ],
            actor="migration-admin",
        )
        course = courses.get_course("C-unit-test")
        lesson = courses.get_lesson("unit-test-lesson")

        self.assertIsNotNone(course)
        self.assertIsNotNone(lesson)
        self.assertEqual(course.summary.lesson_count, 1)
        self.assertEqual(workflow.get_current_release("C-unit-test").release_id, release.release_id)
        self.assertEqual(lesson.content_status, "published")
        self.assertEqual(lesson.body, payload.body)
        self.assertEqual(lesson.release_id, release.release_id)

        with self.assertRaises(workflow.InvalidTransition):
            content.seal_draft(payload.lesson_id, sealed_by="bypass-attempt")

    def test_profile_and_keyword_assets(self):
        content.configure(self.tmp_root)

        person = content.person_template()
        person.asset_id = "li-hongzhang"
        person.name = "李鸿章"
        person.related_lessons = ["L1403"]
        saved_person = content.save_person_profile(person)

        keyword = content.keyword_template()
        keyword.asset_id = "yangwu-yundong"
        keyword.word = "洋务运动"
        keyword.related_people = ["李鸿章"]
        saved_keyword = content.save_keyword_profile(keyword)

        records = content.list_assets()

        self.assertEqual(saved_person.name, "李鸿章")
        self.assertEqual(saved_keyword.word, "洋务运动")
        self.assertEqual(content.get_person_profile("li-hongzhang").related_lessons, ["L1403"])
        self.assertEqual(content.get_keyword_profile("yangwu-yundong").related_people, ["李鸿章"])
        self.assertEqual({record.kind for record in records}, {"person", "keyword"})
        self.assertTrue(content.validate_person_profile("li-hongzhang").valid)
        self.assertTrue(content.validate_keyword_profile("yangwu-yundong").valid)

        sealed_person, person_path, person_reused = content.seal_person_profile(
            "li-hongzhang",
            sealed_by="publisher-a",
        )
        sealed_keyword, keyword_path, keyword_reused = content.seal_keyword_profile(
            "yangwu-yundong",
            sealed_by="publisher-a",
        )
        self.assertFalse(person_reused)
        self.assertFalse(keyword_reused)
        self.assertEqual(sealed_person.version, 1)
        self.assertEqual(sealed_keyword.version, 1)
        self.assertTrue(content.verify_package_checksum(sealed_person))
        self.assertTrue(content.verify_package_checksum(sealed_keyword))
        self.assertTrue(person_path.is_file())
        self.assertTrue(keyword_path.is_file())

        repeated_person = content.seal_person_profile(
            "li-hongzhang",
            sealed_by="publisher-b",
        )
        repeated_keyword = content.seal_keyword_profile(
            "yangwu-yundong",
            sealed_by="publisher-b",
        )
        self.assertTrue(repeated_person[2])
        self.assertTrue(repeated_keyword[2])
        self.assertEqual(repeated_person[0], sealed_person)
        self.assertEqual(repeated_keyword[0], sealed_keyword)

        person.summary = "修改后的人物摘要"
        content.save_person_profile(person)
        revised, _, revised_reused = content.seal_person_profile(
            "li-hongzhang",
            sealed_by="publisher-a",
        )
        self.assertFalse(revised_reused)
        self.assertEqual(revised.version, 2)
        self.assertEqual(
            [item.version for item in content.list_sealed_people("li-hongzhang")],
            [2, 1],
        )

        misplaced = content.people_asset_dir() / "other-person.json"
        shutil.copy2(content.people_asset_dir() / "li-hongzhang.json", misplaced)
        with self.assertRaises(content.ContentIntegrityError):
            content.get_person_profile("other-person")
        with self.assertRaises(content.ContentIntegrityError):
            content.list_assets()

    def test_invalid_content_assets_cannot_be_sealed(self):
        content.configure(self.tmp_root)
        person = content.person_template()
        person.asset_id = "incomplete-person"
        person.summary = ""
        person.persona = ""
        person.boundaries = []
        person.source_refs = []
        content.save_person_profile(person)

        report = content.validate_person_profile(person.asset_id)
        self.assertFalse(report.valid)
        self.assertEqual(
            {item.field for item in report.issues},
            {"summary", "persona", "boundaries", "source_refs"},
        )
        with self.assertRaisesRegex(ValueError, "validation failed"):
            content.seal_person_profile(person.asset_id, sealed_by="publisher")

        keyword = content.keyword_template()
        keyword.asset_id = "incomplete-keyword"
        keyword.gloss = ""
        keyword.examples = []
        keyword.source_refs = []
        content.save_keyword_profile(keyword)

        report = content.validate_keyword_profile(keyword.asset_id)
        self.assertFalse(report.valid)
        self.assertEqual(
            {item.field for item in report.issues},
            {"gloss", "examples", "source_refs"},
        )
        with self.assertRaisesRegex(ValueError, "validation failed"):
            content.seal_keyword_profile(keyword.asset_id, sealed_by="publisher")

    def test_person_seal_and_concurrent_save_are_serialized(self):
        content.configure(self.tmp_root)
        person = content.person_template()
        person.asset_id = "seal-save-race"
        original_summary = person.summary
        content.save_person_profile(person)

        validation_finished = Event()
        release_validation = Event()
        save_started = Event()
        save_finished = Event()
        results: dict[str, object] = {}
        failures: list[BaseException] = []
        original_validate = content.validate_person_profile

        def delayed_validate(asset_id: str):
            report = original_validate(asset_id)
            validation_finished.set()
            if not release_validation.wait(timeout=5):
                raise TimeoutError("test did not release asset validation")
            return report

        def seal() -> None:
            try:
                results["sealed"] = content.seal_person_profile(
                    person.asset_id,
                    sealed_by="publisher",
                )[0]
            except BaseException as exc:
                failures.append(exc)

        def save_invalid_revision() -> None:
            try:
                changed = person.model_copy(deep=True)
                changed.summary = ""
                save_started.set()
                content.save_person_profile(changed)
            except BaseException as exc:
                failures.append(exc)
            finally:
                save_finished.set()

        with patch.object(
            content,
            "validate_person_profile",
            side_effect=delayed_validate,
        ):
            seal_thread = Thread(target=seal)
            seal_thread.start()
            self.assertTrue(validation_finished.wait(timeout=5))

            save_thread = Thread(target=save_invalid_revision)
            save_thread.start()
            self.assertTrue(save_started.wait(timeout=5))
            self.assertFalse(save_finished.wait(timeout=0.2))

            release_validation.set()
            seal_thread.join(timeout=5)
            save_thread.join(timeout=5)

        self.assertFalse(seal_thread.is_alive())
        self.assertFalse(save_thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(results["sealed"].summary, original_summary)
        self.assertEqual(content.get_person_profile(person.asset_id).summary, "")

    def test_draft_asset_paths_reject_sealed_payloads(self):
        content.configure(self.tmp_root)
        person = content.person_template()
        person.asset_id = "sealed-in-draft-person"
        content.save_person_profile(person)
        _, sealed_person_path, _ = content.seal_person_profile(
            person.asset_id,
            sealed_by="publisher",
        )
        shutil.copy2(
            sealed_person_path,
            content.people_asset_dir() / f"{person.asset_id}.json",
        )
        with self.assertRaises(content.ContentIntegrityError):
            content.get_person_profile(person.asset_id)

        keyword = content.keyword_template()
        keyword.asset_id = "sealed-in-draft-keyword"
        content.save_keyword_profile(keyword)
        _, sealed_keyword_path, _ = content.seal_keyword_profile(
            keyword.asset_id,
            sealed_by="publisher",
        )
        shutil.copy2(
            sealed_keyword_path,
            content.keyword_asset_dir() / f"{keyword.asset_id}.json",
        )
        with self.assertRaises(content.ContentIntegrityError):
            content.get_keyword_profile(keyword.asset_id)

    def test_asset_seal_enforces_archive_title_and_size_limits(self):
        content.configure(self.tmp_root)
        person = content.person_template()
        person.asset_id = "oversized-title"
        person.name = "人" * 161
        with self.assertRaises(ValidationError):
            content.save_person_profile(person)

        keyword = content.keyword_template()
        keyword.asset_id = "oversized-file"
        keyword.teacher_notes = "x" * (2 * 1024 * 1024)
        content.save_keyword_profile(keyword)
        with self.assertRaisesRegex(ValueError, "exceeds"):
            content.seal_keyword_profile(
                keyword.asset_id,
                sealed_by="publisher",
            )

        legacy = content.keyword_template()
        legacy.asset_id = "legacy-oversized-seal"
        content.save_keyword_profile(legacy)
        _, legacy_path, _ = content.seal_keyword_profile(
            legacy.asset_id,
            sealed_by="publisher",
        )
        with legacy_path.open("ab") as handle:
            handle.write(b" " * (2 * 1024 * 1024))
        with self.assertRaisesRegex(ValueError, "exceeds"):
            content.seal_keyword_profile(
                legacy.asset_id,
                sealed_by="publisher",
            )

        scenario = scenario_authoring.scenario_draft_template()
        scenario.title = "关" * 161
        report = scenario_authoring.validate_scenario_draft(scenario)
        self.assertFalse(report.valid)
        self.assertIn("title", {item.path for item in report.issues})

        legacy_scenario = scenario_authoring._sealed_contract(
            scenario,
            version=1,
            sealed_by="legacy-publisher",
            sealed_at=datetime.now(timezone.utc),
        )
        descriptor = runtime_artifacts.descriptor_for_scenario(
            legacy_scenario
        )
        legacy_path = content.content_root() / Path(descriptor.path)
        runtime_artifacts._write_immutable_json(
            legacy_path,
            legacy_scenario,
        )
        loaded, loaded_descriptor = (
            runtime_artifacts.load_staged_scenario_path(legacy_path)
        )
        self.assertEqual(loaded.title, scenario.title)
        self.assertEqual(loaded_descriptor, descriptor)
        with self.assertRaisesRegex(ValueError, "title"):
            runtime_artifacts.stage_scenario(legacy_scenario)

    def test_internal_content_paths_reject_trailing_newlines(self):
        content.configure(self.tmp_root)

        for loader in (
            content.get_draft,
            content.get_person_profile,
            content.get_keyword_profile,
        ):
            with self.subTest(loader=loader.__name__):
                with self.assertRaises(ValueError):
                    loader("valid-id\n")

        mutable_payload = content.content_template()
        mutable_payload.lesson_id = "service-boundary"
        mutable_payload.course_id = "invalid-course\n"
        with self.assertRaises(ValueError):
            content.save_draft(mutable_payload, saved_by="author")
        self.assertEqual(list(content.draft_dir().glob("*.json")), [])
        self.assertEqual(list(content.workflow_dir().glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
