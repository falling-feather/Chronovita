"""Current teacher identities must work without borrowing old curriculum IDs."""
import tempfile
import unittest
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / 'apps' / 'api'
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from services.content import workflow
from services.contracts.evidence_v1 import RagAskRequestV1
from services.courses import get_lesson
from services.rag.retrieval import HybridEvidenceRetriever
from services.rag.service import RagAnswerService
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from services import content
from services.ai.classifier import ActionClassifierV1
from services.game_runtime.catalog import ScenarioCatalogRepository
from services.game_runtime.service import GameRuntimeService, ScenarioReleasePinV1
from services.game_runtime.store import GameRuntimeStore
from services.persistence.schema import ensure_current_schema


class TeacherFlagshipTests(unittest.IsolatedAsyncioTestCase):
    async def test_current_two_lessons_finish_with_local_proposals_and_dossiers(self):
        class NoExternalClassifier:
            async def complete(self, *_args, **_kwargs):
                raise AssertionError("Reviewed local actions must not require a model")
        with tempfile.TemporaryDirectory() as root:
            database = create_engine(URL.create('sqlite', database=str(Path(root) / 'game.db')))
            ensure_current_schema(database)
            service = GameRuntimeService(ScenarioCatalogRepository(content_root=content.content_root(),
                catalog_path='scenarios/catalog.v1.json'), GameRuntimeStore(database),
                classifier=ActionClassifierV1(completer=NoExternalClassifier()))
            try:
                for lesson_id in ('L101', 'L105'):
                    resources = workflow.get_published_lesson_resources('C-prequin-state', lesson_id)
                    primary = next(item for item in resources.course_package.scenario_refs if item.primary)
                    pin = ScenarioReleasePinV1(release_id=resources.release_id, release_no=resources.release_no,
                        release_checksum=resources.release_checksum, course_id=resources.course_id, lesson_id=lesson_id,
                        course_content_version=resources.course_package.content_version, course_checksum=resources.course_package.checksum,
                        scenario_version=primary.scenario_version, scenario_checksum=primary.checksum)
                    _, session = service.start_session(primary.scenario_id, user_id='current-teaching-student',
                        client_request_id=f'current-{lesson_id}', release_pin=pin)
                    for turn in range(6):
                        if session.status != 'active':
                            break
                        engine = service.repository.get_published_record(primary.scenario_id, primary.scenario_version, primary.checksum,
                            **pin.model_dump(exclude={'scenario_version', 'scenario_checksum'})).engine
                        text = '召集百姓进行商议' if lesson_id == 'L101' and turn == 0 else engine.available_actions(session)[0].label
                        result = await service.apply_free_input(session.session_id, client_action_id=f'proposal-{lesson_id}-{turn}',
                            raw_input=text, expected_revision=session.revision, owner_user_id=session.user_id)
                        self.assertEqual(result.kind, 'advanced', (lesson_id, text, result.reason_code))
                        session = result.result.session
                    self.assertEqual(session.status, 'completed')
                    dossier = service.get_dossier(session.session_id, owner_user_id=session.user_id)
                    self.assertEqual(dossier.lesson_id, lesson_id)
                    self.assertTrue(dossier.key_choices)
                    self.assertTrue(dossier.historical_explanation)
            finally:
                database.dispose()

    async def test_teacher_texts_and_persona_explanations_are_release_bound(self):
        for lesson_id in ("L101", "L105"):
            self.assertEqual(get_lesson(lesson_id).interaction_status, "ready")
        self.assertNotEqual(get_lesson("L103").interaction_status, "ready")
        with tempfile.TemporaryDirectory() as root:
            service = RagAnswerService(HybridEvidenceRetriever(Path(root) / "rag.db"))
            resources = workflow.get_published_lesson_resources("C-prequin-state", "L105")
            for question in ("奖励耕战有什么作用？", "你如何解释奖励耕战的代价？", "你改了哪些制度？"):
                answer = await service.ask(RagAskRequestV1(course_id="C-prequin-state", lesson_id="L105",
                    persona_mode="person", person_id="person-c797c18e", question=question))
                self.assertEqual(answer.answer_source, "extractive", question)
                self.assertTrue(answer.citations, question)
                self.assertEqual(answer.release_checksum, resources.release_checksum)
                self.assertTrue({item.passage_id for item in answer.citations} <= set(answer.retrieved_passage_ids))
            for question in ("你什么时候车裂的？", "用商鞅方升种花要注意什么？"):
                answer = await service.ask(RagAskRequestV1(course_id="C-prequin-state", lesson_id="L105",
                    persona_mode="person", person_id="person-c797c18e", question=question))
                self.assertEqual(answer.answer_source, "insufficient_evidence", question)
                self.assertFalse(answer.citations)
