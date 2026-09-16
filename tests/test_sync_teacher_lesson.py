from __future__ import annotations

import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.sync_teacher_lesson import (
    COMPATIBILITY_NOTE,
    _as_teacher_draft,
    sync_teacher_lesson,
)
from services import content
from services.content import workflow


REPOSITORY_CONTENT = Path(__file__).resolve().parents[1] / "content"
COURSE_ID = "C-prequin-state"
LESSON_ID = "L101"
SOURCE_PR = 16
SOURCE_COMMIT = "1e19d7167f83e2fe46ecddcd8bd588cc3319216f"
SOURCE_CHECKSUM = "ac7b09fe8f09af7f19d971cbe3f6faa15f4454bfe7ce9787043bfb7f3a0be3fe"


class TeacherLessonSyncTests(unittest.TestCase):
    def test_published_pr_is_idempotent_and_restores_exact_teacher_draft(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "content"
            shutil.copytree(REPOSITORY_CONTENT, root)
            content.configure(root)
            try:
                compatibility = content.get_sealed_package(LESSON_ID, 5)
                self.assertIn(COMPATIBILITY_NOTE, compatibility.teacher_notes)
                content.save_draft(
                    _as_teacher_draft(compatibility),
                    saved_by="interrupted-sync",
                )
                workflow.validate_draft(LESSON_ID, actor="interrupted-sync")
                release_count = len(workflow.list_releases(COURSE_ID))

                result = sync_teacher_lesson(
                    root,
                    lesson_id=LESSON_ID,
                    source_pr=SOURCE_PR,
                    source_commit=SOURCE_COMMIT,
                    source_checksum=SOURCE_CHECKSUM,
                    author="content-sync-pr16-author",
                    reviewer="content-sync-pr16-reviewer",
                    publisher="content-sync-pr16-publisher",
                )

                restored = content.get_draft(LESSON_ID)
                exact = content.get_sealed_package(LESSON_ID, 4)
                record = workflow.get_workflow(LESSON_ID)
                self.assertEqual(result["status"], "already-published")
                self.assertEqual(result["release_no"], 10)
                self.assertEqual(result["exact_source_version"], 4)
                self.assertEqual(result["student_source_version"], 5)
                self.assertEqual(len(workflow.list_releases(COURSE_ID)), release_count)
                self.assertIsNotNone(restored)
                assert restored is not None
                self.assertNotIn(COMPATIBILITY_NOTE, restored.teacher_notes)
                self.assertEqual(restored.people, exact.people)
                self.assertEqual(restored.source_refs, exact.source_refs)
                self.assertIsNotNone(record)
                assert record is not None
                self.assertEqual(record.state, "validated")
                revision = record.revision

                repeated = sync_teacher_lesson(
                    root,
                    lesson_id=LESSON_ID,
                    source_pr=SOURCE_PR,
                    source_commit=SOURCE_COMMIT,
                    source_checksum=SOURCE_CHECKSUM,
                    author="content-sync-pr16-author",
                    reviewer="content-sync-pr16-reviewer",
                    publisher="content-sync-pr16-publisher",
                )

                self.assertEqual(repeated["status"], "already-published")
                self.assertEqual(len(workflow.list_releases(COURSE_ID)), release_count)
                repeated_record = workflow.get_workflow(LESSON_ID)
                self.assertIsNotNone(repeated_record)
                assert repeated_record is not None
                self.assertEqual(repeated_record.revision, revision)
            finally:
                content.configure()


if __name__ == "__main__":
    unittest.main()
