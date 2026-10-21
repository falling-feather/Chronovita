import tempfile
import unittest
from pathlib import Path
from services import persistence
from services.classroom_tasks import ClassroomTaskConflict, list_tasks, load_task, save_task, validate_task_submission
from services.contracts.classroom_v1 import ClassroomTaskRequestV1


class ClassroomTaskTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        persistence.init_engine(sqlite_path=str(Path(self.directory.name) / 'classroom.db'))

    def tearDown(self):
        persistence.close_engine()
        self.directory.cleanup()

    def test_revisions_idempotence_and_exact_submission_binding(self):
        request = ClassroomTaskRequestV1(client_task_id='test-task', course_id='C-prequin-state', lesson_id='L101',
            title='治水与协作', prompt='引用一条材料，解释你会怎样组织治水。')
        task = save_task(request, teacher_id='teacher1', teacher_display_name='教师')
        self.assertEqual(save_task(request, teacher_id='teacher1', teacher_display_name='教师'), task)
        self.assertEqual(len(list_tasks(lesson_id='L101')), 1)
        validate_task_submission(task, course_id='C-prequin-state', lesson_id='L101')
        with self.assertRaises(ValueError):
            validate_task_submission(task, course_id='C-prequin-state', lesson_id='L105')
        revised = request.model_copy(update={'status':'closed', 'expected_checksum':task.checksum})
        closed = save_task(revised, teacher_id='teacher1', teacher_display_name='教师')
        self.assertEqual(closed.revision, 2)
        self.assertEqual(load_task(task.task_id, task.checksum), task)
        with self.assertRaises(ClassroomTaskConflict):
            save_task(request.model_copy(update={'prompt':'另一项任务'}), teacher_id='teacher1', teacher_display_name='教师')
        with self.assertRaises(ValueError):
            validate_task_submission(closed, course_id='C-prequin-state', lesson_id='L101')
