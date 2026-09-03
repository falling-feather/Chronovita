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
SOURCE_PR = 11
SOURCE_COMMIT = "10ad1a351e75f781bf780b6347b048d861f8a8e0"
SOURCE_CHECKSUM = "7a857cf4698e19d76f6fbc997143cb988db91d45b1f75d6b915b8fef3e8fe829"


class TeacherLessonSyncTests(unittest.TestCase):
    def test_published_pr_is_idempotent_and_restores_exact_teacher_draft(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "content"
            shutil.copytree(REPOSITORY_CONTENT, root)
            content.configure(root)
            try:
                compatibility = content.get_sealed_package(LESSON_ID, 3)
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
                    author="content-sync-pr11-author",
                    reviewer="content-sync-pr11-reviewer",
                    publisher="content-sync-pr11-publisher",
                )

                restored = content.get_draft(LESSON_ID)
                exact = content.get_sealed_package(LESSON_ID, 2)
                record = workflow.get_workflow(LESSON_ID)
                self.assertEqual(result["status"], "already-published")
                self.assertEqual(result["release_no"], 9)
                self.assertEqual(result["exact_source_version"], 2)
                self.assertEqual(result["student_source_version"], 3)
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
                    author="content-sync-pr11-author",
                    reviewer="content-sync-pr11-reviewer",
                    publisher="content-sync-pr11-publisher",
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
