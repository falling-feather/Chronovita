from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, insert, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from services.content import content_root, workflow
from services.game_runtime import RuntimeCommandV1
from services.game_runtime.catalog import ScenarioCatalogRepository
from services.game_runtime.dialogue import (
    GLOBAL_RULE_NODE_ID,
    DialogueProjectionService,
)
from services.game_runtime.dialogue_models import (
    ScenarioDialogueReleaseIdentityV1,
    ScenarioNpcDialogueV1,
    dialogue_record_checksum,
)
from services.game_runtime.store import (
    GameRuntimeStore,
    GameSessionReleaseIdentityV1,
    StoredDialogueIntegrityError,
    encode_stored_dialogue,
    game_npc_dialogues_table,
)
from services.persistence.schema import ensure_current_schema

BASE_TIME = datetime(2026, 8, 31, 8, 0, tzinfo=timezone.utc)


class GameDialoguePersistenceTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.repository = ScenarioCatalogRepository(
            content_root=content_root(),
            catalog_path="scenarios/catalog.v1.json",
        )

    async def _case(self, lesson_id: str = "L101"):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        ensure_current_schema(engine)
        self.addCleanup(engine.dispose)
        store = GameRuntimeStore(engine)

        resources = workflow.get_published_lesson_resources(
            "C-prequin-state",
            lesson_id,
        )
        pack = resources.persona_pack
        assert pack is not None
        scenario = self.repository.get_active_record(pack.scenario_id).engine
        session = scenario.start_session(
            session_id=f"persist-{lesson_id.lower()}-session",
            user_id="dialogue-persistence-student",
            started_at=BASE_TIME,
        )
        pre_node = session.current_node_id or GLOBAL_RULE_NODE_ID
        action_id = session.available_action_ids[0]
        result = scenario.apply_action(
            session,
            RuntimeCommandV1(
                client_action_id=f"persist-{lesson_id.lower()}-turn-001",
                raw_input=scenario.available_actions(session)[0].label,
                action_id=action_id,
                action_source="fixed",
                expected_revision=session.revision,
                occurred_at=BASE_TIME + timedelta(minutes=1),
            ),
        )
        projection_pin = ScenarioDialogueReleaseIdentityV1(
            release_id=resources.release_id,
            release_no=resources.release_no,
            release_checksum=resources.release_checksum,
        )
        dialogue = await DialogueProjectionService(
            resources,
            projection_pin,
        ).project(
            settled_session=result.session,
            turn=result.turn,
            pre_settlement_node_id=pre_node,
            action_id=action_id,
        )
        storage_pin = GameSessionReleaseIdentityV1.model_validate(
            projection_pin.model_dump(mode="python"),
            strict=True,
        )
        store.create_session(session, release_identity=storage_pin)
        return engine, store, session, result.session, dialogue, storage_pin

    async def test_compare_and_swap_persists_session_and_dialogue_atomically(self):
        _engine, store, initial, settled, dialogue, pin = await self._case()
        current = store.load_session(initial.session_id)

        store.compare_and_swap(current, settled, dialogue=dialogue)

        loaded_session = store.load_session(initial.session_id)
        loaded_dialogue = store.load_dialogue(initial.session_id, dialogue.turn_id)
        self.assertEqual(loaded_session.session, settled)
        self.assertEqual(loaded_session.envelope.release_identity, pin)
        self.assertEqual(loaded_dialogue.dialogue, dialogue)
        self.assertEqual(
            tuple(item.dialogue for item in store.load_dialogues(initial.session_id)),
            (dialogue,),
        )
        self.assertEqual(
            json.loads(loaded_dialogue.raw_data),
            dialogue.model_dump(mode="json"),
        )

    async def test_session_and_turn_pair_is_unique_and_failed_cas_rolls_back(self):
        engine, store, initial, settled, dialogue, _pin = await self._case()
        current = store.load_session(initial.session_id)
        conflicting = _dialogue_copy(
            dialogue,
            turn_id="persist-conflicting-turn",
        )
        with engine.begin() as connection:
            connection.execute(
                insert(game_npc_dialogues_table).values(
                    turn_id=conflicting.turn_id,
                    session_id=conflicting.session_id,
                    turn_no=conflicting.turn_no,
                    data=encode_stored_dialogue(conflicting),
                    updated_at=settled.updated_at,
                )
            )

        with self.assertRaises(StoredDialogueIntegrityError):
            store.compare_and_swap(current, settled, dialogue=dialogue)

        self.assertEqual(store.load_session(initial.session_id).session, initial)
        self.assertEqual(
            store.load_dialogue(initial.session_id, conflicting.turn_id).dialogue,
            conflicting,
        )
        with engine.begin() as connection:
            with self.assertRaises(IntegrityError):
                connection.execute(
                    insert(game_npc_dialogues_table).values(
                        turn_id="another-conflicting-turn",
                        session_id=dialogue.session_id,
                        turn_no=dialogue.turn_no,
                        data=encode_stored_dialogue(dialogue),
                        updated_at=settled.updated_at,
                    )
                )

    async def test_wrong_session_release_and_turn_identities_are_rejected(self):
        _engine, store, initial, settled, dialogue, _pin = await self._case("L103")
        corruptions = (
            {"session_id": "different-session"},
            {"release_id": "different-release"},
            {"turn_id": "different-turn"},
        )
        for updates in corruptions:
            with self.subTest(updates=updates):
                current = store.load_session(initial.session_id)
                invalid = _dialogue_copy(dialogue, **updates)
                with self.assertRaises(StoredDialogueIntegrityError):
                    store.compare_and_swap(current, settled, dialogue=invalid)
                self.assertEqual(
                    store.load_session(initial.session_id).session,
                    initial,
                )
                self.assertEqual(store.load_dialogues(initial.session_id), ())

    async def test_tampered_stored_dialogue_checksum_fails_closed(self):
        engine, store, initial, settled, dialogue, _pin = await self._case()
        current = store.load_session(initial.session_id)
        store.compare_and_swap(current, settled, dialogue=dialogue)
        payload = dialogue.model_dump(mode="json")
        payload["text"] = "数据库中被篡改且未重新签名的台词。"
        tampered_raw = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with engine.begin() as connection:
            connection.execute(
                update(game_npc_dialogues_table)
                .where(game_npc_dialogues_table.c.turn_id == dialogue.turn_id)
                .values(data=tampered_raw)
            )

        with self.assertRaisesRegex(
            StoredDialogueIntegrityError,
            "checksum|invalid persisted",
        ):
            store.load_dialogue(initial.session_id, dialogue.turn_id)


def _dialogue_copy(
    dialogue: ScenarioNpcDialogueV1,
    **updates,
) -> ScenarioNpcDialogueV1:
    payload = dialogue.model_dump(mode="python")
    payload.update(updates)
    payload["output_checksum"] = dialogue_record_checksum(payload)
    return ScenarioNpcDialogueV1.model_validate(payload, strict=True)


if __name__ == "__main__":
    unittest.main()
