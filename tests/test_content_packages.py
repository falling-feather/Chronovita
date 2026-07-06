import tempfile
import unittest

from services import content, courses


class ContentPackageTests(unittest.TestCase):
    def test_draft_seal_and_course_read(self):
        with tempfile.TemporaryDirectory() as root:
            content.configure(root)
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
