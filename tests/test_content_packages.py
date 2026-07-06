import shutil
import unittest
import uuid
from pathlib import Path

from services import content, courses


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

    def test_draft_seal_and_course_read(self):
        content.configure(self.tmp_root)
        payload = content.content_template()
        payload.lesson_id = "unit-test-lesson"
        payload.course_id = "C-unit-test"
        payload.title = "Unit Test Lesson"
        payload.unit = "Unit Test Course"
        payload.era = "Test Era"
        payload.body = ["The sealed body should be readable by the public course service."]

        draft = content.save_draft(payload)
        sealed, path = content.seal_draft(payload.lesson_id, sealed_by="tester")

        self.assertEqual(draft.status, "draft")
        self.assertEqual(sealed.status, "sealed")
        self.assertEqual(sealed.version, 1)
        self.assertTrue(sealed.checksum)
        self.assertTrue(path.exists())

        course = courses.get_course("C-unit-test")
        lesson = courses.get_lesson("unit-test-lesson")

        self.assertIsNotNone(course)
        self.assertIsNotNone(lesson)
        self.assertEqual(course.summary.lesson_count, 1)
        self.assertEqual(lesson.content_status, "sealed")
        self.assertEqual(lesson.body, payload.body)

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


if __name__ == "__main__":
    unittest.main()
