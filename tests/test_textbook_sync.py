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

    def test_removed_lessons_cannot_resurface_via_direct_lookup(self):
        for lesson_id in ("L402", "L702", "L1504", "L106", "L107"):
            self.assertIsNone(courses.get_lesson(lesson_id), lesson_id)
            self.assertIsNone(courses.get_builtin_lesson(lesson_id), lesson_id)

    def test_reading_people_and_map_are_teacher_authored_not_old_scenario(self):
        lesson = courses.get_lesson("L103")
        self.assertIn("姬发（周武王）", [p["name"] for p in lesson.people])
        self.assertNotIn("商鞅", [p["name"] for p in lesson.people])
        self.assertIn("商鞅", [p["name"] for p in lesson.interaction_people])
        interaction = courses.get_interactive_lesson("L103")
        self.assertEqual(lesson.content_checksum, interaction.content_checksum)
        self.assertEqual(lesson.content_version, interaction.content_version)
        self.assertTrue(lesson.teacher_text_checksum)
        self.assertTrue(lesson.rag_available)
        self.assertFalse(lesson.reading_media_available)
        self.assertEqual(lesson.map_points, [
            p.model_dump(mode="json") for p in load_textbooks()["C-prequin-state"].lessons[2].map_points
        ])

    def test_empty_teacher_catalog_never_falls_back_to_builtin_text(self):
        original = content.content_root()
        with TemporaryDirectory() as folder:
            try:
                content.configure(Path(folder))
                self.assertEqual(courses.list_courses(), [])
                self.assertIsNone(courses.get_lesson("L101"))
            finally:
                content.configure(original)

    def test_course_description_is_derived_from_current_teacher_lessons(self):
        course = courses.get_course("C-qinhan-founding")
        self.assertEqual(course.summary.subtitle, "光武中兴与东汉兴衰")
        self.assertNotIn("文景之治", course.intro)


if __name__ == "__main__":
    unittest.main()
