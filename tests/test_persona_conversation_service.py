from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from services import content
from services.content import workflow
from services.contracts.evidence_v1 import RagAnswerV1
from services.persistence.schema import ensure_current_schema
from services.persona_conversation import (
    PersonaConversationCoordinator,
    PersonaConversationStore,
    PersonaConversationTurnInputV1,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class _FixedRagService:
    def __init__(self, answer: RagAnswerV1) -> None:
        self.answer = answer

    async def ask(self, *_args, **_kwargs) -> RagAnswerV1:
        return self.answer


class PersonaConversationCoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addAsyncCleanup(self._cleanup)
        self.previous_content_root = content.content_root()
        content.configure(REPO_ROOT / "content")
        database_path = Path(self.temp_dir.name) / "conversation.sqlite3"
        self.engine = create_engine(
            URL.create("sqlite", database=str(database_path)),
            future=True,
        )
        ensure_current_schema(self.engine)
        self.store = PersonaConversationStore(self.engine)

    async def _cleanup(self) -> None:
        self.engine.dispose()
        content.configure(self.previous_content_root)
        self.temp_dir.cleanup()

    async def test_concurrent_same_message_replays_first_committed_answer(self) -> None:
        resources = workflow.get_published_lesson_resources(
            "C-prequin-state",
            "L101",
        )
        person_id = "person-7c4825d9"
        losing_answer = _insufficient_answer(
            resources,
            person_id=person_id,
            body="稍后完成但没有被提交的回答。",
        )
        coordinator = PersonaConversationCoordinator(
            self.store,
            _FixedRagService(losing_answer),
        )
        conversation = coordinator.create_conversation(
            owner_user_id="usr_student_001",
            course_id=resources.course_id,
            lesson_id=resources.lesson_id,
            person_id=person_id,
        )

        original_append = self.store.append_turn

        def finish_competing_request_first(
            conversation_id: str,
            *,
            owner_user_id: str,
            expected_revision: int,
            turn: PersonaConversationTurnInputV1,
        ):
            winner = PersonaConversationTurnInputV1(
                client_message_id=turn.client_message_id,
                question=turn.question,
                answer_snapshot="先完成并已经提交的回答。",
                route_target="refuse",
                route_reason="insufficient_or_disallowed_question",
                answer_source="insufficient_evidence",
                uncertainty="high",
                retrieved_passage_ids=(),
            )
            original_append(
                conversation_id,
                owner_user_id=owner_user_id,
                expected_revision=expected_revision,
                turn=winner,
            )
            return original_append(
                conversation_id,
                owner_user_id=owner_user_id,
                expected_revision=expected_revision,
                turn=turn,
            )

        with patch.object(
            self.store,
            "append_turn",
            side_effect=finish_competing_request_first,
        ):
            result = await coordinator.send_message(
                conversation.conversation_id,
                owner_user_id=conversation.owner_user_id,
                client_message_id="same-browser-message",
                expected_revision=1,
                question="这个问题有证据吗？",
            )

        self.assertTrue(result.reused)
        self.assertFalse(result.continuity_applied)
        self.assertEqual(result.answer.body, "先完成并已经提交的回答。")
        self.assertEqual(result.conversation.revision, 2)
        self.assertEqual(len(result.conversation.turns), 1)


def _insufficient_answer(
    resources,
    *,
    person_id: str,
    body: str,
) -> RagAnswerV1:
    return RagAnswerV1(
        answer_source="insufficient_evidence",
        retrieval_mode="lexical",
        body=body,
        persona_mode="person",
        person_id=person_id,
        role_disclaimer="角色化教学表达，不是史料原话。",
        citations=(),
        retrieved_passage_ids=(),
        course_id=resources.course_id,
        lesson_id=resources.lesson_id,
        release_id=resources.release_id,
        release_no=resources.release_no,
        release_checksum=resources.release_checksum,
        evidence_corpus_id=resources.evidence_corpus.corpus_id,
        evidence_version=resources.evidence_corpus.corpus_version,
        evidence_checksum=resources.evidence_corpus.checksum,
        uncertainty="high",
    )


if __name__ == "__main__":
    unittest.main()
