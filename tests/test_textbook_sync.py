import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from services import content, courses
from services.courses.textbooks import load_textbooks, text_checksum


class TextbookSyncTests(unittest.TestCase):
    def test_snapshot_replaces_whole_course_without_runtime_release(self):
        original = content.content_root()
        books = load_textbooks()
        with TemporaryDirectory() as folder:
            try:
                content.configure(Path(folder))
                for book in books.values():
                    content._atomic_write_json(
                        Path(folder) / "textbooks" / f"{book.course_id}.json",
                        book.model_dump(mode="json"),
                    )
                course = courses.get_course("C-prequin-thought")
                expected = books["C-prequin-thought"].lessons
                self.assertEqual([x.id for x in course.lessons], [x.lesson_id for x in expected])
                self.assertEqual(course.summary.lesson_count, len(expected))
                for book in books.values():
                    for lesson in book.lessons:
                        shown = courses.get_lesson(lesson.lesson_id)
                        self.assertEqual(shown.body, lesson.body)
                        self.assertEqual(shown.title, lesson.title)
                        self.assertEqual(shown.num, lesson.lesson_no)
                self.assertEqual(list((Path(folder) / "releases").rglob("*.json")), [])
            finally:
                content.configure(original)

    def test_text_fingerprint_ignores_provenance_but_detects_text_changes(self):
        payload = next(iter(load_textbooks().values())).model_dump(mode="json")
        before = text_checksum(payload)
        payload.update(source_pr=999, source_commit="a" * 40)
        self.assertEqual(text_checksum(payload), before)
        payload["lessons"][0]["body"][0] += "新增正文"
        self.assertNotEqual(text_checksum(payload), before)

    def test_catalog_does_not_keep_routes_for_reassigned_lesson_ids(self):
        for summary in courses.list_courses():
            for lesson in courses.get_course(summary.id).lessons:
                self.assertEqual(courses.get_lesson(lesson.id).course_id, summary.id)

    def test_current_textbooks_have_expected_order_and_preserve_inline_marks(self):
        books = load_textbooks()
        state = books["C-prequin-state"]
        self.assertEqual([x.lesson_id for x in state.lessons],
                         ["L101", "L102", "L103", "L104", "L105"])
        self.assertEqual(state.lessons[2].title, "西周分封与宗法")
        self.assertTrue(any("【" in p for p in state.lessons[1].body))


if __name__ == "__main__":
    unittest.main()
