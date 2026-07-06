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


if __name__ == "__main__":
    unittest.main()
