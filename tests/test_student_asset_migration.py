from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import shutil
import sys
import unittest
import uuid
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, delete, insert, select, update
from sqlalchemy.engine import URL


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from main import app, lifespan
from settings import settings
from services import persistence
from services.auth import AuthService, AuthServiceConfig
from services.auth.models import UserRecord
from services.auth.passwords import hash_password
from services.auth.store import AuthStore, AuthStoreError
from services.contracts.v1 import verify_contract_checksum
from services.game_runtime import RuntimeCommandV1
from services.game_runtime.catalog import ScenarioCatalogRepository
from services.game_runtime.service import GameRuntimeService
from services.game_runtime.store import (
    GameRuntimeStore,
    GameSessionReleaseIdentityV1,
    GameStoreError,
    game_sessions_table,
)
from services.persistence.db import kv_table
from services.persistence.student_assets import (
    StudentAssetMigrationAuthorizationError,
    StudentAssetMigrationConflict,
    StudentAssetMigrationError,
    StudentAssetMigrationIntegrityError,
    UnmappedStudentAssetsError,
    assert_no_unmapped_student_assets,
    find_unmapped_student_assets,
    migrate_legacy_student_assets,
)
from scripts import create_student_account as create_student_cli
from scripts import migrate_student_assets as migration_cli


NOW = datetime(2026, 7, 16, 8, 0, tzinfo=timezone.utc)
ADMIN_ID = f"usr_{'a' * 32}"
STUDENT_ID = f"usr_{'b' * 32}"
REVIEWER_ID = f"usr_{'c' * 32}"
DISABLED_ID = f"usr_{'d' * 32}"
LEGACY_GAME_USER = "local-student"
TEST_PASSWORD = "Migration test password 123!"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)
DAYU_ACTIONS = (
    "survey-terrain",
    "explain-plan",
    "open-channels",
    "allocate-food",
    "open-channels",
)


class StudentAssetMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-student-migration-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)
        self.database_path = self.tmp_root / "chronovita.db"
        self.engine = create_engine(
            URL.create("sqlite", database=str(self.database_path)),
            connect_args={"check_same_thread": False},
            future=True,
        )
        kv_table.metadata.create_all(self.engine)
        self.auth_store = AuthStore(self.engine)
        self.game_store = GameRuntimeStore(self.engine)
        self._create_user(ADMIN_ID, "root.admin", ("admin",))
        self._create_user(STUDENT_ID, "student.one", ("student",))
        self._create_user(REVIEWER_ID, "reviewer.one", ("reviewer",))
        self._create_user(
            DISABLED_ID,
            "student.disabled",
            ("student",),
            enabled=False,
        )
        self.identity = AuthService(
            self.engine,
            AuthServiceConfig(mode="accounts", session_ttl_seconds=300),
        )
        self.admin_session = self.identity.login(
            "root.admin",
            TEST_PASSWORD,
            request_id="test-migration-admin-login",
        )
        self.reviewer_session = self.identity.login(
            "reviewer.one",
            TEST_PASSWORD,
            request_id="test-migration-reviewer-login",
        )

    def tearDown(self):
        self.engine.dispose()
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass

    def test_dry_run_apply_and_idempotent_retry_preserve_asset_identities(self):
        session_id, dossier_id, canvas_raw = self._seed_legacy_assets()
        before = find_unmapped_student_assets(self.engine)
        self.assertEqual(before.counts.total, 4)
        self.assertEqual(before.owner_ids, ("default", LEGACY_GAME_USER))

        planned = self._migrate(apply=False)
        self.assertEqual(planned.status, "planned")
        self.assertEqual(planned.counts.total, 4)
        self.assertIsNone(planned.receipt_checksum)
        self.assertIsNotNone(self._kv_raw("lesson_progress", "default:lesson-migrate"))
        self.assertIsNone(
            self._kv_raw("lesson_progress", f"{STUDENT_ID}:lesson-migrate")
        )
        self.assertEqual(
            self.game_store.load_session(session_id).session.user_id,
            LEGACY_GAME_USER,
        )

        applied = self._migrate(apply=True)
        self.assertEqual(applied.status, "applied")
        self.assertEqual(applied.counts.total, 4)
        self.assertTrue(applied.target_has_student_role)
        self.assertEqual(applied.actor_user_id, ADMIN_ID)
        self.assertEqual(
            applied.actor_session_id,
            self.admin_session.principal.session_id,
        )
        self.assertIsNotNone(applied.receipt_checksum)
        self.assertIsNotNone(applied.applied_at)
        self.assertIsNone(self._kv_raw("lesson_progress", "default:lesson-migrate"))
        progress = json.loads(
            self._kv_raw("lesson_progress", f"{STUDENT_ID}:lesson-migrate")
        )
        self.assertEqual(progress["user_id"], STUDENT_ID)
        self.assertIsNone(self._kv_raw("canvas", "lesson-migrate"))
        self.assertEqual(
            self._kv_raw("canvas", f"{STUDENT_ID}:lesson-migrate"),
            canvas_raw,
        )

        stored_session = self.game_store.load_session(
            session_id,
            owner_user_id=STUDENT_ID,
        ).session
        self.assertEqual(stored_session.session_id, session_id)
        self.assertEqual(stored_session.user_id, STUDENT_ID)
        self.assertEqual(stored_session.dossier_id, dossier_id)
        stored_dossier = self.game_store.load_dossier(dossier_id).dossier
        self.assertEqual(stored_dossier.dossier_id, dossier_id)
        self.assertEqual(stored_dossier.session_id, session_id)
        self.assertEqual(stored_dossier.user_id, STUDENT_ID)
        self.assertTrue(verify_contract_checksum(stored_dossier))
        runtime = GameRuntimeService(
            ScenarioCatalogRepository(
                content_root=REPO_ROOT / "content",
                catalog_path="scenarios/catalog.v1.json",
            ),
            self.game_store,
        )
        replay = runtime.for_owner(STUDENT_ID).replay_session(session_id)
        self.assertEqual(replay.session.user_id, STUDENT_ID)
        self.assertEqual(replay.session.dossier_id, dossier_id)
        assert_no_unmapped_student_assets(self.engine)
        migration_events = [
            event
            for event in self.auth_store.list_audit(limit=100)
            if event.action == "auth.student_assets.migrate"
        ]
        self.assertEqual(len(migration_events), 1)
        self.assertEqual(migration_events[0].actor_user_id, ADMIN_ID)
        self.assertEqual(migration_events[0].resource_id, applied.migration_id)
        self.assertEqual(
            migration_events[0].details["receipt_checksum"],
            applied.receipt_checksum,
        )
        self.assertTrue(self.auth_store.verify_audit_chain())

        retried = self._migrate(apply=True)
        self.assertEqual(retried.status, "already_applied")
        self.assertEqual(retried.receipt_checksum, applied.receipt_checksum)
        self.assertEqual(retried.source_fingerprint, applied.source_fingerprint)

        receipt_key = f"legacy-v1:{LEGACY_GAME_USER}"
        receipt = json.loads(
            self._kv_raw("student_asset_migrations", receipt_key)
        )
        receipt["actor_username"] = "forged.admin"
        with self.engine.begin() as connection:
            connection.execute(
                update(kv_table)
                .where(
                    (kv_table.c.namespace == "student_asset_migrations")
                    & (kv_table.c.key == receipt_key)
                )
                .values(
                    data=json.dumps(
                        receipt,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
            )
        with self.assertRaises(StudentAssetMigrationIntegrityError):
            self._migrate(apply=False)

    def test_existing_target_record_blocks_every_write(self):
        session_id, _, _ = self._seed_legacy_assets()
        self._insert_kv(
            "canvas",
            f"{STUDENT_ID}:lesson-migrate",
            {"schema_version": "canvas/v1", "revision": 1, "nodes": [], "edges": []},
        )
        target_raw = self._kv_raw("canvas", f"{STUDENT_ID}:lesson-migrate")

        with self.assertRaises(StudentAssetMigrationConflict):
            self._migrate(apply=True)

        self.assertIsNotNone(self._kv_raw("lesson_progress", "default:lesson-migrate"))
        self.assertIsNotNone(self._kv_raw("canvas", "lesson-migrate"))
        self.assertEqual(
            self._kv_raw("canvas", f"{STUDENT_ID}:lesson-migrate"),
            target_raw,
        )
        self.assertEqual(
            self.game_store.load_session(session_id).session.user_id,
            LEGACY_GAME_USER,
        )
        self.assertIsNone(
            self._kv_raw("student_asset_migrations", f"legacy-v1:{LEGACY_GAME_USER}")
        )

    def test_active_v1_session_is_upgraded_without_losing_release_identity(self):
        session_id, release_identity = self._seed_legacy_active_v1_session()
        before = find_unmapped_student_assets(self.engine)
        self.assertEqual(before.counts.sessions, 1)
        self.assertEqual(before.counts.dossiers, 0)

        applied = self._migrate(apply=True)
        self.assertEqual(applied.counts.sessions, 1)
        self.assertEqual(applied.counts.dossiers, 0)
        payload = json.loads(self._session_raw(session_id))
        self.assertEqual(payload["schema_version"], "persisted-game-session/v2")
        self.assertEqual(payload["release_identity"], release_identity)
        self.assertEqual(payload["session"]["user_id"], STUDENT_ID)
        self.assertIsNone(payload["session"]["dossier_id"])

        stored = self.game_store.load_session(
            session_id,
            owner_user_id=STUDENT_ID,
        )
        self.assertEqual(
            stored.envelope.release_identity.model_dump(mode="json"),
            release_identity,
        )
        assert_no_unmapped_student_assets(self.engine)

    def test_failure_after_all_asset_updates_rolls_back_the_transaction(self):
        session_id, dossier_id, _ = self._seed_legacy_assets()
        with patch(
            "services.persistence.student_assets._build_receipt",
            side_effect=StudentAssetMigrationIntegrityError("injected receipt failure"),
        ):
            with self.assertRaises(StudentAssetMigrationIntegrityError):
                self._migrate(apply=True)

        self.assertIsNotNone(self._kv_raw("lesson_progress", "default:lesson-migrate"))
        self.assertIsNone(
            self._kv_raw("lesson_progress", f"{STUDENT_ID}:lesson-migrate")
        )
        self.assertIsNotNone(self._kv_raw("canvas", "lesson-migrate"))
        self.assertEqual(
            self.game_store.load_session(session_id).session.user_id,
            LEGACY_GAME_USER,
        )
        self.assertEqual(
            self.game_store.load_dossier(dossier_id).dossier.user_id,
            LEGACY_GAME_USER,
        )

    def test_audit_failure_rolls_back_assets_receipt_and_audit_head(self):
        session_id, dossier_id, _ = self._seed_legacy_assets()
        audit_count = len(self.auth_store.list_audit(limit=100))
        with patch(
            "services.persistence.student_assets.AuthStore.append_audit_in_transaction",
            side_effect=AuthStoreError("injected audit failure"),
        ):
            with self.assertRaises(StudentAssetMigrationError):
                self._migrate(apply=True)

        self.assertIsNotNone(self._kv_raw("lesson_progress", "default:lesson-migrate"))
        self.assertIsNone(
            self._kv_raw("lesson_progress", f"{STUDENT_ID}:lesson-migrate")
        )
        self.assertEqual(
            self.game_store.load_session(session_id).session.user_id,
            LEGACY_GAME_USER,
        )
        self.assertEqual(
            self.game_store.load_dossier(dossier_id).dossier.user_id,
            LEGACY_GAME_USER,
        )
        self.assertIsNone(
            self._kv_raw("student_asset_migrations", f"legacy-v1:{LEGACY_GAME_USER}")
        )
        self.assertEqual(len(self.auth_store.list_audit(limit=100)), audit_count)
        self.assertTrue(self.auth_store.verify_audit_chain())

    def test_game_rewrite_errors_are_closed_into_migration_integrity_errors(self):
        self._seed_legacy_game_only()
        for error in (ValueError("invalid game payload"), GameStoreError("codec failed")):
            with self.subTest(error=type(error).__name__):
                with patch(
                    "services.persistence.student_assets.encode_stored_session",
                    side_effect=error,
                ):
                    with self.assertRaises(StudentAssetMigrationIntegrityError):
                        self._migrate(apply=False)

    def test_orphan_dossier_and_wrong_explicit_source_fail_closed(self):
        session_id, dossier_id, _ = self._seed_legacy_assets()
        with self.engine.begin() as connection:
            connection.execute(delete_from_game_session(session_id))
        with self.assertRaises(StudentAssetMigrationIntegrityError):
            self._migrate(apply=False)
        self.assertEqual(
            self.game_store.load_dossier(dossier_id).dossier.user_id,
            LEGACY_GAME_USER,
        )

        with self.engine.begin() as connection:
            connection.execute(delete_from_game_dossier(dossier_id))
        self._seed_legacy_game_only()
        with self.assertRaises(StudentAssetMigrationIntegrityError):
            migrate_legacy_student_assets(
                self.engine,
                actor=self.admin_session.principal,
                request_id="wrong-source-attempt",
                target_username="student.one",
                source_game_user_id="different-local-user",
                apply=False,
            )

    def test_actor_target_and_unknown_owner_are_validated(self):
        self._seed_legacy_assets()
        with self.assertRaises(StudentAssetMigrationAuthorizationError):
            migrate_legacy_student_assets(
                self.engine,
                actor=self.reviewer_session.principal,
                request_id="reviewer-migration-attempt",
                target_username="student.one",
                source_game_user_id=LEGACY_GAME_USER,
            )
        with self.assertRaises(StudentAssetMigrationAuthorizationError):
            migrate_legacy_student_assets(
                self.engine,
                actor=self.admin_session.principal,
                request_id="disabled-target-attempt",
                target_username="student.disabled",
                source_game_user_id=LEGACY_GAME_USER,
            )
        with self.assertRaises(StudentAssetMigrationAuthorizationError):
            migrate_legacy_student_assets(
                self.engine,
                actor=self.admin_session.principal,
                request_id="admin-target-attempt",
                target_username="root.admin",
                source_game_user_id=LEGACY_GAME_USER,
            )

        self._insert_kv(
            "canvas",
            f"{ADMIN_ID}:lesson-admin-owned",
            {"nodes": [], "edges": []},
        )
        report = find_unmapped_student_assets(self.engine)
        self.assertIn(ADMIN_ID, report.owner_ids)
        with self.assertRaises(StudentAssetMigrationIntegrityError):
            self._migrate(apply=False)

        unknown_id = f"usr_{'f' * 32}"
        self._insert_kv(
            "canvas",
            f"{unknown_id}:lesson-unknown",
            {"nodes": [], "edges": []},
        )
        report = find_unmapped_student_assets(self.engine)
        self.assertIn(unknown_id, report.owner_ids)
        with self.assertRaises(StudentAssetMigrationIntegrityError):
            self._migrate(apply=False)

    def test_revoked_administrator_session_cannot_authorize_migration(self):
        self._seed_legacy_assets()
        self.identity.logout(
            self.admin_session.principal,
            request_id="revoke-migration-test-session",
        )
        with self.assertRaises(StudentAssetMigrationAuthorizationError):
            self._migrate(apply=False)

    def test_cli_returns_structured_json_when_migration_raises_value_error(self):
        stderr = io.StringIO()
        stdout = io.StringIO()
        with patch.dict(
            os.environ,
            {"CHRONO_MIGRATION_ACTOR_PASSWORD": TEST_PASSWORD},
            clear=False,
        ), patch(
            "scripts.migrate_student_assets.migrate_legacy_student_assets",
            side_effect=ValueError("invalid migration input"),
        ), redirect_stderr(stderr), redirect_stdout(stdout):
            result = migration_cli.main(
                [
                    "--database",
                    str(self.database_path),
                    "--actor-username",
                    "root.admin",
                    "--target-username",
                    "student.one",
                    "--source-game-user-id",
                    LEGACY_GAME_USER,
                ]
            )
        self.assertEqual(result, 2)
        self.assertEqual(stdout.getvalue(), "")
        error = json.loads(stderr.getvalue())
        self.assertFalse(error["ok"])
        self.assertEqual(error["code"], "student_asset_command_invalid")

    def _migrate(self, *, apply: bool):
        return migrate_legacy_student_assets(
            self.engine,
            actor=self.admin_session.principal,
            request_id="test-student-asset-migration",
            target_username="student.one",
            source_game_user_id=LEGACY_GAME_USER,
            apply=apply,
            now=NOW,
        )

    def _seed_legacy_assets(self) -> tuple[str, str, str]:
        self._insert_kv(
            "lesson_progress",
            "default:lesson-migrate",
            {
                "user_id": "default",
                "lesson_id": "lesson-migrate",
                "last_layer": "watch",
                "layers": {
                    "watch": True,
                    "practice": False,
                    "ask": False,
                    "create": False,
                },
                "updated_at": NOW.isoformat(),
            },
        )
        canvas = {
            "nodes": [{"id": "student-node", "label": "kept"}],
            "edges": [],
        }
        canvas_raw = self._insert_kv("canvas", "lesson-migrate", canvas)
        session_id, dossier_id = self._seed_legacy_game_only()
        return session_id, dossier_id, canvas_raw

    def _seed_legacy_game_only(self) -> tuple[str, str]:
        service = self._runtime()
        _, session = service.start_session(
            "scenario-dayu-flood-control",
            user_id=LEGACY_GAME_USER,
            client_request_id="migration-fixture",
            now=NOW,
        )
        for revision, action_id in enumerate(DAYU_ACTIONS, start=1):
            session = service.apply_action(
                session.session_id,
                RuntimeCommandV1(
                    client_action_id=f"migration-action-{revision:03d}",
                    action_id=action_id,
                    raw_input=action_id,
                    expected_revision=revision,
                    occurred_at=NOW + timedelta(minutes=revision),
                ),
            ).session
        self.assertIsNotNone(session.dossier_id)
        return session.session_id, session.dossier_id

    def _seed_legacy_active_v1_session(self) -> tuple[str, dict]:
        service = self._runtime()
        _, session = service.start_session(
            "scenario-dayu-flood-control",
            user_id=LEGACY_GAME_USER,
            client_request_id="migration-v1-active-fixture",
            now=NOW,
        )
        stored = self.game_store.load_session(session.session_id)
        self.assertEqual(stored.session.status, "active")
        self.assertIsNone(stored.session.dossier_id)
        release_identity = GameSessionReleaseIdentityV1(
            release_id="release-migration-v1",
            release_no=7,
            release_checksum="a" * 64,
        )
        session_payload = stored.session.model_dump(mode="json")
        session_payload.pop("ai_evidence_version")
        for turn in session_payload["turns"]:
            turn.pop("classification_evidence", None)
            turn.pop("narrative_evidence", None)
        release_payload = release_identity.model_dump(mode="json")
        checksum_payload = {
            "session": session_payload,
            "release_identity": release_payload,
        }
        checksum = hashlib.sha256(
            json.dumps(
                checksum_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        raw = json.dumps(
            {
                "schema_version": "persisted-game-session/v1",
                **checksum_payload,
                "checksum": checksum,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self.engine.begin() as connection:
            connection.execute(
                update(game_sessions_table)
                .where(game_sessions_table.c.session_id == session.session_id)
                .values(data=raw)
            )
        self.assertEqual(
            json.loads(self._session_raw(session.session_id))["schema_version"],
            "persisted-game-session/v1",
        )
        return session.session_id, release_payload

    def _runtime(self) -> GameRuntimeService:
        return GameRuntimeService(
            ScenarioCatalogRepository(
                content_root=REPO_ROOT / "content",
                catalog_path="scenarios/catalog.v1.json",
            ),
            self.game_store,
        )

    def _insert_kv(self, namespace: str, key: str, payload: dict) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.engine.begin() as connection:
            connection.execute(
                insert(kv_table).values(
                    namespace=namespace,
                    key=key,
                    data=raw,
                    updated_at=NOW,
                )
            )
        return raw

    def _kv_raw(self, namespace: str, key: str) -> str | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(kv_table.c.data).where(
                    (kv_table.c.namespace == namespace) & (kv_table.c.key == key)
                )
            ).first()
        return row[0] if row else None

    def _session_raw(self, session_id: str) -> str:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(game_sessions_table.c.data).where(
                    game_sessions_table.c.session_id == session_id
                )
            ).one()
        return row[0]

    def _create_user(
        self,
        user_id: str,
        username: str,
        roles: tuple[str, ...],
        *,
        enabled: bool = True,
    ) -> None:
        self.auth_store.create_user(
            UserRecord(
                user_id=user_id,
                username=username,
                display_name=username,
                password_hash=TEST_PASSWORD_HASH,
                roles=roles,
                enabled=enabled,
                auth_version=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )


class AccountsStartupMigrationGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp_root = Path.cwd() / ".tmp-student-startup-tests" / uuid.uuid4().hex
        self.tmp_root.mkdir(parents=True)
        self.database_path = self.tmp_root / "chronovita.db"
        self.previous = {
            "auth_mode": settings.auth_mode,
            "auth_bootstrap_username": settings.auth_bootstrap_username,
            "auth_bootstrap_password": settings.auth_bootstrap_password,
            "auth_bootstrap_display_name": settings.auth_bootstrap_display_name,
            "content_root": settings.content_root,
            "game_catalog_path": settings.game_catalog_path,
            "sqlite_path": settings.sqlite_path,
        }
        settings.auth_mode = "accounts"
        settings.auth_bootstrap_username = "root.startup"
        settings.auth_bootstrap_password = "Root startup password 123!"
        settings.auth_bootstrap_display_name = "Root Startup"
        settings.content_root = str(REPO_ROOT / "content")
        settings.game_catalog_path = "scenarios/catalog.v1.json"
        settings.sqlite_path = str(self.database_path)
        persistence.close_engine()
        persistence.init_engine(settings.sqlite_path)
        persistence.kv_set(
            "canvas",
            "lesson-unmapped-startup",
            {"nodes": [], "edges": []},
        )
        persistence.close_engine()

    def tearDown(self):
        persistence.close_engine()
        for key, value in self.previous.items():
            setattr(settings, key, value)
        shutil.rmtree(self.tmp_root, ignore_errors=True)
        try:
            self.tmp_root.parent.rmdir()
        except OSError:
            pass

    def test_empty_auth_old_database_can_be_unblocked_and_started(self):
        with self.assertRaises(UnmappedStudentAssetsError) as caught:
            asyncio.run(self._enter_lifespan())
        self.assertEqual(caught.exception.report.counts.canvases, 1)

        created = self._run_cli(
            create_student_cli.main,
            [
                "--database",
                str(self.database_path),
                "--actor-username",
                "root.startup",
                "--username",
                "student.startup",
                "--display-name",
                "Startup Student",
            ],
            {
                "CHRONO_MIGRATION_ACTOR_PASSWORD": settings.auth_bootstrap_password,
                "CHRONO_NEW_STUDENT_PASSWORD": "Student startup password 123!",
            },
        )
        self.assertTrue(created["ok"])
        self.assertEqual(created["user"]["roles"], ["student"])

        migration_args = [
            "--database",
            str(self.database_path),
            "--actor-username",
            "root.startup",
            "--target-username",
            "student.startup",
            "--source-game-user-id",
            LEGACY_GAME_USER,
        ]
        planned = self._run_cli(
            migration_cli.main,
            migration_args,
            {
                "CHRONO_MIGRATION_ACTOR_PASSWORD": settings.auth_bootstrap_password,
            },
        )
        self.assertEqual(planned["status"], "planned")
        self.assertEqual(planned["counts"]["canvases"], 1)
        applied = self._run_cli(
            migration_cli.main,
            [*migration_args, "--apply"],
            {
                "CHRONO_MIGRATION_ACTOR_PASSWORD": settings.auth_bootstrap_password,
            },
        )
        self.assertEqual(applied["status"], "applied")

        asyncio.run(self._enter_lifespan())
        engine = create_engine(
            URL.create("sqlite", database=str(self.database_path)),
            connect_args={"check_same_thread": False},
            future=True,
        )
        try:
            assert_no_unmapped_student_assets(engine)
            with engine.connect() as connection:
                migrated_canvas = connection.execute(
                    select(kv_table.c.data).where(
                        (kv_table.c.namespace == "canvas")
                        & kv_table.c.key.like("usr_%:lesson-unmapped-startup")
                    )
                ).one()
            self.assertEqual(json.loads(migrated_canvas[0]), {"nodes": [], "edges": []})
        finally:
            engine.dispose()

    def _run_cli(self, entrypoint, argv: list[str], environment: dict[str, str]) -> dict:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.dict(os.environ, environment, clear=False), redirect_stdout(
            stdout
        ), redirect_stderr(stderr):
            result = entrypoint(argv)
        self.assertEqual(result, 0, stderr.getvalue())
        self.assertEqual(stderr.getvalue(), "")
        return json.loads(stdout.getvalue())

    @staticmethod
    async def _enter_lifespan() -> None:
        async with lifespan(app):
            pass


def delete_from_game_session(session_id: str):
    from services.game_runtime.store import game_sessions_table

    return delete(game_sessions_table).where(
        game_sessions_table.c.session_id == session_id
    )


def delete_from_game_dossier(dossier_id: str):
    from services.game_runtime.store import game_dossiers_table

    return delete(game_dossiers_table).where(
        game_dossiers_table.c.dossier_id == dossier_id
    )


if __name__ == "__main__":
    unittest.main()
