from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.engine import URL

from apps.api import main as api_main
from services.game_runtime.store import game_npc_dialogues_table
from services.persistence import schema as schema_module
from services.persistence.backup import (
    backup_sqlite_database,
    restore_sqlite_backup,
    verify_sqlite_backup,
)
from services.persistence.schema import (
    ensure_current_schema,
    inspect_schema,
    schema_migrations_table,
)
from services.persona_conversation import (
    PersonaConversationIdentityV1,
    PersonaConversationStore,
    get_persona_conversations,
    new_persona_conversation,
    persona_conversations_table,
    shutdown_persona_conversations,
)

NOW = datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)


class PersonaConversationPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        shutdown_persona_conversations()

    def tearDown(self) -> None:
        shutdown_persona_conversations()
        self.temp_dir.cleanup()

    def test_v4_database_upgrades_with_append_only_persona_and_dialogue_migrations(
        self,
    ) -> None:
        engine = self._engine("upgrade.db")
        try:
            with (
                patch.object(
                    schema_module, "_MIGRATIONS", schema_module._MIGRATIONS[:4]
                ),
                patch.object(schema_module, "LATEST_SCHEMA_VERSION", 4),
            ):
                previous = ensure_current_schema(engine)
            self.assertEqual(previous.current_version, 4)
            self.assertNotIn(
                persona_conversations_table.name,
                inspect(engine).get_table_names(),
            )

            upgraded = ensure_current_schema(engine)

            self.assertEqual(upgraded.current_version, 6)
            self.assertTrue(upgraded.is_current)
            self.assertIn(
                persona_conversations_table.name,
                inspect(engine).get_table_names(),
            )
            self.assertIn(
                game_npc_dialogues_table.name,
                inspect(engine).get_table_names(),
            )
            with engine.connect() as connection:
                row = (
                    connection.execute(
                        select(schema_migrations_table).where(
                            schema_migrations_table.c.version == 5
                        )
                    )
                    .mappings()
                    .one()
                )
            self.assertEqual(row["migration_id"], "persona-conversation-v1")
            self.assertEqual(row["app_version"], "1.0.3")
        finally:
            engine.dispose()

    def test_sqlite_backup_restore_preserves_persona_conversation(self) -> None:
        source = self._path("source.db")
        backup = self._path("backup.db")
        restored = self._path("restored.db")
        engine = self._engine_at(source)
        conversation = new_persona_conversation(
            self._identity(),
            conversation_id="conversation-backup-test",
            created_at=NOW,
        )
        try:
            ensure_current_schema(engine)
            PersonaConversationStore(engine).create_conversation(conversation)
            manifest = backup_sqlite_database(source, backup)
        finally:
            engine.dispose()

        self.assertEqual(verify_sqlite_backup(backup).manifest, manifest)
        restore_sqlite_backup(backup, restored)
        restored_engine = self._engine_at(restored)
        try:
            self.assertTrue(inspect_schema(restored_engine).is_current)
            loaded = PersonaConversationStore(restored_engine).load_conversation(
                conversation.conversation_id,
                owner_user_id=conversation.owner_user_id,
            )
            self.assertEqual(loaded.conversation, conversation)
        finally:
            restored_engine.dispose()

    def test_api_lifespan_registers_and_clears_the_shared_store(self) -> None:
        engine = self._engine("lifespan.db")
        ensure_current_schema(engine)

        async def exercise() -> None:
            async with api_main.lifespan(api_main.app):
                self.assertIs(get_persona_conversations().engine, engine)
            with self.assertRaisesRegex(RuntimeError, "not configured"):
                get_persona_conversations()

        try:
            with (
                patch.object(api_main, "configure_runtime_logging"),
                patch.object(api_main, "validate_runtime_configuration"),
                patch.object(api_main.persistence, "init_engine", return_value=engine),
                patch.object(api_main, "configure_identity"),
                patch.object(api_main, "assert_no_unmapped_student_assets"),
                patch.object(api_main.content, "configure"),
                patch.object(
                    api_main.content_workflow,
                    "recover_pending_release_transactions",
                ),
                patch.object(api_main, "configure_game_runtime"),
                patch.object(api_main, "configure_learning_assets"),
                patch.object(api_main.rag, "configure_rag"),
                patch.object(
                    api_main,
                    "probe_database_readiness",
                    return_value=object(),
                ),
                patch.object(api_main.rag, "shutdown_rag"),
                patch.object(api_main, "shutdown_learning_assets"),
                patch.object(api_main, "shutdown_game_runtime"),
                patch.object(api_main, "shutdown_identity"),
                patch.object(api_main.persistence, "close_engine"),
            ):
                asyncio.run(exercise())
        finally:
            engine.dispose()

    def _path(self, filename: str) -> Path:
        return Path(self.temp_dir.name) / filename

    def _engine(self, filename: str):
        return self._engine_at(self._path(filename))

    @staticmethod
    def _engine_at(path: Path):
        return create_engine(
            URL.create("sqlite", database=str(path)),
            connect_args={"check_same_thread": False},
            future=True,
        )

    @staticmethod
    def _identity() -> PersonaConversationIdentityV1:
        return PersonaConversationIdentityV1(
            owner_user_id="usr_student_001",
            course_id="C-preqin-state",
            lesson_id="L101",
            release_id="release-dayu-007",
            release_no=7,
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


if __name__ == "__main__":
    unittest.main()
