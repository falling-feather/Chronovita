import shutil
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from services import content, courses
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

        misplaced = content.people_asset_dir() / "other-person.json"
        shutil.copy2(content.people_asset_dir() / "li-hongzhang.json", misplaced)
        with self.assertRaises(content.ContentIntegrityError):
            content.get_person_profile("other-person")
        with self.assertRaises(content.ContentIntegrityError):
            content.list_assets()

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
