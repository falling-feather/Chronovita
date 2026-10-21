from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.engine import URL

from services.persona_conversation import (
    MAX_CONVERSATION_RECORD_BYTES,
    MAX_CONVERSATION_TURNS,
    PersonaConversationIdentityV1,
    PersonaConversationIntegrityError,
    PersonaConversationLimitReached,
    PersonaConversationNotFound,
    PersonaConversationStore,
    PersonaConversationTurnInputV1,
    PersonaConversationWriteConflict,
    PersonaMessageIdConflict,
    new_persona_conversation,
    persona_conversations_table,
)

NOW = datetime(2026, 8, 31, 9, 0, tzinfo=timezone.utc)


class PersonaConversationStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "persona-conversations.db"
        self.engine = self._engine()
        persona_conversations_table.create(self.engine)
        self.store = PersonaConversationStore(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_exact_artifact_identity_survives_a_new_store_instance(self):
        conversation = self._create()

        restarted_engine = self._engine()
        try:
            restarted = PersonaConversationStore(restarted_engine)
            record = restarted.load_conversation(
                conversation.conversation_id,
                owner_user_id=conversation.owner_user_id,
            )
        finally:
            restarted_engine.dispose()

        self.assertEqual(record.conversation, conversation)
        self.assertEqual(record.conversation.identity(), self._identity())
        raw = json.loads(record.raw_data)
        self.assertEqual(raw["release_id"], "release-dayu-006")
        self.assertEqual(raw["release_no"], 6)
        self.assertEqual(raw["release_checksum"], "a" * 64)
        self.assertEqual(raw["persona_pack_id"], "persona-dayu-v1")
        self.assertEqual(raw["persona_pack_version"], 1)
        self.assertEqual(raw["persona_pack_checksum"], "b" * 64)
        self.assertEqual(raw["evidence_corpus_id"], "evidence-dayu-v2")
        self.assertEqual(raw["evidence_version"], 2)
        self.assertEqual(raw["evidence_checksum"], "c" * 64)

    def test_owner_scope_is_mandatory_and_hides_foreign_conversations(self):
        conversation = self._create()

        with self.assertRaisesRegex(PersonaConversationNotFound, "resource not found"):
            self.store.load_conversation(
                conversation.conversation_id,
                owner_user_id="usr_other",
            )
        with self.assertRaises(PersonaConversationNotFound):
            self.store.append_turn(
                conversation.conversation_id,
                owner_user_id="usr_other",
                expected_revision=1,
                turn=self._turn("msg-001"),
                occurred_at=NOW + timedelta(seconds=1),
            )

    def test_append_is_revision_cas_and_records_the_answered_revision(self):
        conversation = self._create()
        first = self.store.append_turn(
            conversation.conversation_id,
            owner_user_id=conversation.owner_user_id,
            expected_revision=1,
            turn=self._turn("msg-001"),
            occurred_at=NOW + timedelta(seconds=1),
        )

        self.assertFalse(first.reused)
        self.assertEqual(first.conversation.revision, 2)
        self.assertEqual(first.turn.turn_no, 1)
        self.assertEqual(first.turn.based_on_revision, 1)
        with self.assertRaises(PersonaConversationWriteConflict):
            self.store.append_turn(
                conversation.conversation_id,
                owner_user_id=conversation.owner_user_id,
                expected_revision=1,
                turn=self._turn("msg-stale"),
                occurred_at=NOW + timedelta(seconds=2),
            )
        stored = self.store.load_conversation(
            conversation.conversation_id,
            owner_user_id=conversation.owner_user_id,
        ).conversation
        self.assertEqual(stored.revision, 2)
        self.assertEqual([item.client_message_id for item in stored.turns], ["msg-001"])

    def test_client_message_id_retry_reuses_only_identical_content(self):
        conversation = self._create()
        turn = self._turn("msg-idempotent")
        first = self.store.append_turn(
            conversation.conversation_id,
            owner_user_id=conversation.owner_user_id,
            expected_revision=1,
            turn=turn,
            occurred_at=NOW + timedelta(seconds=1),
        )
        retry = self.store.append_turn(
            conversation.conversation_id,
            owner_user_id=conversation.owner_user_id,
            expected_revision=1,
            turn=turn,
            occurred_at=NOW + timedelta(hours=1),
        )

        self.assertTrue(retry.reused)
        self.assertEqual(retry.turn, first.turn)
        self.assertEqual(retry.conversation.revision, 2)
        with self.engine.connect() as connection:
            stored_count = connection.execute(
                select(func.count()).select_from(persona_conversations_table)
            ).scalar_one()
        self.assertEqual(stored_count, 1)

        changed = turn.model_copy(update={"answer_snapshot": "不同的回答快照。"})
        with self.assertRaisesRegex(
            PersonaMessageIdConflict,
            "already used for different content",
        ):
            self.store.append_turn(
                conversation.conversation_id,
                owner_user_id=conversation.owner_user_id,
                expected_revision=2,
                turn=changed,
                occurred_at=NOW + timedelta(seconds=2),
            )

    def test_recent_context_is_six_turns_and_never_unions_old_evidence(self):
        conversation = self._create()
        for turn_no in range(1, 9):
            self.store.append_turn(
                conversation.conversation_id,
                owner_user_id=conversation.owner_user_id,
                expected_revision=turn_no,
                turn=self._turn(
                    f"msg-{turn_no:03d}",
                    passage_id=f"old-passage-{turn_no:02d}",
                ),
                occurred_at=NOW + timedelta(seconds=turn_no),
            )

        context = self.store.load_recent_context(
            conversation.conversation_id,
            owner_user_id=conversation.owner_user_id,
            current_allowed_passage_ids=("fresh-passage-01",),
        )

        self.assertEqual(
            [item.turn_no for item in context.recent_turns],
            [3, 4, 5, 6, 7, 8],
        )
        self.assertEqual(
            context.current_allowed_passage_ids,
            ("fresh-passage-01",),
        )
        self.assertEqual(context.evidence_allowlist_source, "current_request_only")
        remembered = {
            passage_id
            for item in context.recent_turns
            for passage_id in item.passage_ids
        }
        self.assertTrue(remembered)
        self.assertTrue(remembered.isdisjoint(context.current_allowed_passage_ids))

    def test_turn_storage_is_a_narrow_audit_snapshot_without_evidence_text(self):
        conversation = self._create()
        with self.assertRaises(ValidationError):
            PersonaConversationTurnInputV1(
                **self._turn("msg-extra").model_dump(mode="python"),
                evidence_text="forbidden source body",
            )

        self.store.append_turn(
            conversation.conversation_id,
            owner_user_id=conversation.owner_user_id,
            expected_revision=1,
            turn=self._turn("msg-001"),
            occurred_at=NOW + timedelta(seconds=1),
        )
        raw = self._raw(conversation.conversation_id)
        stored_turn = json.loads(raw)["turns"][0]
        self.assertEqual(
            set(stored_turn),
            {
                "answer_snapshot",
                "answer_source",
                "based_on_revision",
                "boundary_ids",
                "client_message_id",
                "occurred_at",
                "passage_ids",
                "question",
                "retrieval_mode",
                "retrieved_passage_ids",
                "route_reason",
                "route_target",
                "slot_ids",
                "source_payload_checksum",
                "turn_no",
                "uncertainty",
            },
        )
        for forbidden in (
            "citation",
            "excerpt",
            "evidence_text",
            "locator",
            "source_title",
        ):
            self.assertNotIn(forbidden, raw)

    def test_checksum_tampering_and_column_identity_drift_fail_closed(self):
        conversation = self._create()
        raw = json.loads(self._raw(conversation.conversation_id))
        raw["lesson_id"] = "lesson-other"
        raw["checksum"] = _checksum(raw)
        self._replace_raw(conversation.conversation_id, _canonical_json(raw))

        with self.assertRaisesRegex(
            PersonaConversationIntegrityError,
            "storage identity mismatch",
        ):
            self.store.load_conversation(
                conversation.conversation_id,
                owner_user_id=conversation.owner_user_id,
            )

    def test_malformed_duplicate_and_oversized_records_fail_closed(self):
        conversation = self._create()
        valid_raw = self._raw(conversation.conversation_id)
        payload = json.loads(valid_raw)
        payload["release_no"] = 7
        self._replace_raw(conversation.conversation_id, _canonical_json(payload))
        with self.assertRaises(PersonaConversationIntegrityError):
            self._load(conversation)

        duplicate = valid_raw.replace(
            '"conversation_id":"conversation-test",',
            '"conversation_id":"conversation-test",'
            '"conversation_id":"conversation-test",',
            1,
        )
        self._replace_raw(conversation.conversation_id, duplicate)
        with self.assertRaises(PersonaConversationIntegrityError):
            self._load(conversation)

        self._replace_raw(
            conversation.conversation_id,
            "x" * (MAX_CONVERSATION_RECORD_BYTES + 1),
        )
        with self.assertRaisesRegex(
            PersonaConversationIntegrityError,
            "exceeds",
        ):
            self._load(conversation)

    def test_conversation_is_bounded_to_twenty_four_reasonably_sized_turns(self):
        conversation = self._create()
        for turn_no in range(1, MAX_CONVERSATION_TURNS + 1):
            self.store.append_turn(
                conversation.conversation_id,
                owner_user_id=conversation.owner_user_id,
                expected_revision=turn_no,
                turn=self._turn(f"msg-{turn_no:03d}"),
                occurred_at=NOW + timedelta(seconds=turn_no),
            )
        with self.assertRaises(PersonaConversationLimitReached):
            self.store.append_turn(
                conversation.conversation_id,
                owner_user_id=conversation.owner_user_id,
                expected_revision=MAX_CONVERSATION_TURNS + 1,
                turn=self._turn("msg-over-limit"),
                occurred_at=NOW + timedelta(minutes=1),
            )
        with self.assertRaises(ValidationError):
            self._turn("msg-answer-too-long").model_copy(
                update={"answer_snapshot": "答" * 2_001}
            ).__class__.model_validate(
                {
                    **self._turn("msg-answer-too-long").model_dump(mode="json"),
                    "answer_snapshot": "答" * 2_001,
                }
            )

    def _engine(self):
        return create_engine(
            URL.create("sqlite", database=str(self.db_path)),
            connect_args={"check_same_thread": False},
            future=True,
        )

    def _identity(self) -> PersonaConversationIdentityV1:
        return PersonaConversationIdentityV1(
            owner_user_id="usr_student_001",
            course_id="C-preqin-state",
            lesson_id="L101",
            release_id="release-dayu-006",
            release_no=6,
            release_checksum="a" * 64,
            persona_pack_id="persona-dayu-v1",
            persona_pack_version=1,
            persona_pack_checksum="b" * 64,
            evidence_corpus_id="evidence-dayu-v2",
            evidence_version=2,
            evidence_checksum="c" * 64,
            person_id="person-yu",
            channel="consult",
        )

    def _create(self):
        conversation = new_persona_conversation(
            self._identity(),
            conversation_id="conversation-test",
            created_at=NOW,
        )
        self.store.create_conversation(conversation)
        return conversation

    @staticmethod
    def _turn(
        client_message_id: str,
        *,
        passage_id: str = "passage-dayu-01",
    ) -> PersonaConversationTurnInputV1:
        return PersonaConversationTurnInputV1(
            client_message_id=client_message_id,
            question="治水为什么要疏导？",
            answer_snapshot="这是用于延续对话的非权威回答快照。",
            route_target="local_template",
            route_reason="grounded_local_answer",
            answer_source="extractive",
            uncertainty="medium",
            slot_ids=("slot-method",),
            boundary_ids=("boundary-source-layer",),
            passage_ids=(passage_id,),
            retrieved_passage_ids=(passage_id,),
        )

    def _load(self, conversation):
        return self.store.load_conversation(
            conversation.conversation_id,
            owner_user_id=conversation.owner_user_id,
        )

    def _raw(self, conversation_id: str) -> str:
        with self.engine.connect() as connection:
            return connection.execute(
                select(persona_conversations_table.c.data).where(
                    persona_conversations_table.c.conversation_id == conversation_id
                )
            ).scalar_one()

    def _replace_raw(self, conversation_id: str, raw_data: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(persona_conversations_table)
                .where(persona_conversations_table.c.conversation_id == conversation_id)
                .values(data=raw_data)
            )


def _checksum(payload: dict) -> str:
    checked = dict(payload)
    checked["checksum"] = None
    return hashlib.sha256(_canonical_json(checked).encode("utf-8")).hexdigest()


def _canonical_json(payload: object) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


if __name__ == "__main__":
    unittest.main()
