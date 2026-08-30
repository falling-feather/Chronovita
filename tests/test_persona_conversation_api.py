from __future__ import annotations

import sys
import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from routers import auth as auth_router
from routers import practice as practice_router
from settings import settings

from services import content, rag
from services.auth import AuthServiceConfig, configure_identity, shutdown_identity
from services.content import workflow
from services.persistence.schema import ensure_current_schema
from services.persona_conversation import (
    configure_persona_conversations,
    shutdown_persona_conversations,
)


class PersonaConversationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.previous_content_root = content.content_root()
        self.previous_settings = {
            "auth_mode": settings.auth_mode,
            "auth_session_ttl_seconds": settings.auth_session_ttl_seconds,
            "auth_cookie_name": settings.auth_cookie_name,
            "auth_cookie_secure": settings.auth_cookie_secure,
            "auth_bootstrap_username": settings.auth_bootstrap_username,
            "auth_bootstrap_password": settings.auth_bootstrap_password,
            "auth_bootstrap_display_name": settings.auth_bootstrap_display_name,
            "llm_provider": settings.llm_provider,
            "deepseek_api_key": settings.deepseek_api_key,
        }
        settings.auth_mode = "accounts"
        settings.auth_session_ttl_seconds = 3600
        settings.auth_cookie_name = "chronovita_persona_api_session"
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_username = "root.admin"
        settings.auth_bootstrap_password = "Root password 123!"
        settings.auth_bootstrap_display_name = "Root Admin"
        settings.llm_provider = "mock"
        settings.deepseek_api_key = ""

        database_path = Path(self.temp_dir.name) / "chronovita.db"
        rag_index_path = Path(self.temp_dir.name) / "rag.sqlite3"

        @asynccontextmanager
        async def lifespan(_: FastAPI):
            engine = create_engine(
                URL.create("sqlite", database=str(database_path)),
                future=True,
            )
            try:
                ensure_current_schema(engine)
                configure_identity(
                    engine,
                    AuthServiceConfig(
                        mode="accounts",
                        session_ttl_seconds=3600,
                        bootstrap_username="root.admin",
                        bootstrap_password="Root password 123!",
                        bootstrap_display_name="Root Admin",
                    ),
                )
                configure_persona_conversations(engine)
                content.configure(REPO_ROOT / "content")
                rag.configure_rag(
                    index_path=rag_index_path,
                    model_root=Path(self.temp_dir.name) / "missing-model",
                    vector_enabled=False,
                )
                yield
            finally:
                rag.shutdown_rag()
                shutdown_persona_conversations()
                shutdown_identity()
                engine.dispose()

        app = FastAPI(lifespan=lifespan)
        app.include_router(auth_router.router, prefix="/api/v1/auth")
        app.include_router(practice_router.router, prefix="/api/v1/practice")
        self.client = TestClient(app)
        self.client.__enter__()

        admin_headers = self._login_headers("root.admin", "Root password 123!")
        for username, roles in (
            ("student.one", ["student"]),
            ("student.two", ["student"]),
            ("teacher.one", ["teacher"]),
        ):
            self._create_user(
                admin_headers,
                username=username,
                password=f"{username} Password 123!",
                roles=roles,
            )
        self.student_headers = self._login_headers(
            "student.one",
            "student.one Password 123!",
        )
        self.other_student_headers = self._login_headers(
            "student.two",
            "student.two Password 123!",
        )
        self.teacher_headers = self._login_headers(
            "teacher.one",
            "teacher.one Password 123!",
        )

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        content.configure(self.previous_content_root)
        for key, value in self.previous_settings.items():
            setattr(settings, key, value)

    def test_create_read_and_message_are_pinned_to_current_v5_persona(self) -> None:
        created = self._create_conversation()
        resources = workflow.get_published_lesson_resources(
            "C-prequin-state",
            "L101",
        )
        self.assertEqual(created["revision"], 1)
        self.assertEqual(created["release_no"], 7)
        self.assertEqual(created["release_checksum"], resources.release_checksum)
        self.assertEqual(
            created["persona_pack_checksum"],
            resources.persona_pack.checksum,
        )
        self.assertEqual(
            created["evidence_checksum"],
            resources.evidence_corpus.checksum,
        )
        self.assertEqual(created["channel"], "consult")

        response = self.client.post(
            f"/api/v1/practice/persona/conversations/{created['conversation_id']}/messages",
            headers=self.student_headers,
            json={
                "client_message_id": "message-001",
                "expected_revision": 1,
                "question": "您是谁？",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertFalse(result["reused"])
        self.assertFalse(result["continuity_applied"])
        self.assertEqual(result["conversation"]["revision"], 2)
        self.assertEqual(result["answer"]["person_id"], "person-7c4825d9")
        self.assertEqual(
            result["answer"]["role_disclaimer"],
            "角色化教学表达，不是史料原话。",
        )
        allowed = {
            item.passage_id
            for item in next(
                profile
                for profile in resources.persona_pack.profiles
                if profile.person_id == "person-7c4825d9"
            ).evidence_uses
        }
        self.assertTrue(result["answer"]["citations"])
        self.assertTrue(
            {item["passage_id"] for item in result["answer"]["citations"]}.issubset(
                allowed
            )
        )
        turn = result["conversation"]["turns"][0]
        self.assertEqual(
            turn["passage_ids"],
            [item["passage_id"] for item in result["answer"]["citations"]],
        )

        loaded = self.client.get(
            f"/api/v1/practice/persona/conversations/{created['conversation_id']}",
            headers=self.student_headers,
        )
        self.assertEqual(loaded.status_code, 200, loaded.text)
        self.assertEqual(loaded.json(), result["conversation"])

    def test_follow_up_memory_never_becomes_an_evidence_allowlist(self) -> None:
        created = self._create_conversation()
        first = self._send(
            created["conversation_id"],
            message_id="follow-up-001",
            revision=1,
            question="传世文献为何不能直接当作禹时代的现场记录？",
        )
        second = self._send(
            created["conversation_id"],
            message_id="follow-up-002",
            revision=2,
            question="那为什么呢？",
        )
        self.assertTrue(second["continuity_applied"])
        self.assertEqual(second["conversation"]["revision"], 3)
        second_turn = second["conversation"]["turns"][-1]
        self.assertEqual(
            second_turn["passage_ids"],
            [item["passage_id"] for item in second["answer"]["citations"]],
        )
        if not second["answer"]["citations"]:
            self.assertFalse(
                set(first["conversation"]["turns"][0]["passage_ids"])
                & set(second_turn["passage_ids"])
            )

    def test_shangyang_l103_uses_its_own_published_persona_scope(self) -> None:
        response = self.client.post(
            "/api/v1/practice/persona/conversations",
            headers=self.student_headers,
            json={
                "course_id": "C-prequin-state",
                "lesson_id": "L103",
                "person_id": "person-c797c18e",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        created = response.json()
        result = self._send(
            created["conversation_id"],
            message_id="shangyang-001",
            revision=1,
            question="商鞅方升能说明什么？",
        )
        resources = workflow.get_published_lesson_resources(
            "C-prequin-state",
            "L103",
        )
        allowed = {
            item.passage_id
            for item in next(
                profile
                for profile in resources.persona_pack.profiles
                if profile.person_id == "person-c797c18e"
            ).evidence_uses
        }
        self.assertEqual(result["answer"]["person_id"], "person-c797c18e")
        self.assertTrue(result["answer"]["citations"])
        self.assertTrue(
            {item["passage_id"] for item in result["answer"]["citations"]}.issubset(
                allowed
            )
        )

    def test_owner_rbac_revision_and_message_id_fail_closed(self) -> None:
        teacher = self.client.post(
            "/api/v1/practice/persona/conversations",
            headers=self.teacher_headers,
            json=self._create_payload(),
        )
        self.assertEqual(teacher.status_code, 403, teacher.text)

        created = self._create_conversation()
        foreign = self.client.get(
            f"/api/v1/practice/persona/conversations/{created['conversation_id']}",
            headers=self.other_student_headers,
        )
        self.assertEqual(foreign.status_code, 404, foreign.text)

        first = self._send(
            created["conversation_id"],
            message_id="retry-001",
            revision=1,
            question="您是谁？",
        )
        with patch.object(
            rag.get_rag_service(),
            "ask",
            side_effect=AssertionError("an idempotent retry repeated retrieval"),
        ):
            replay = self._send(
                created["conversation_id"],
                message_id="retry-001",
                revision=1,
                question="您是谁？",
            )
        self.assertFalse(first["reused"])
        self.assertTrue(replay["reused"])
        self.assertEqual(replay["conversation"]["revision"], 2)
        self.assertEqual(replay["answer"]["body"], first["answer"]["body"])
        self.assertEqual(
            replay["answer"]["retrieval_mode"],
            first["answer"]["retrieval_mode"],
        )
        self.assertEqual(
            replay["answer"]["retrieved_passage_ids"],
            first["answer"]["retrieved_passage_ids"],
        )

        reused_for_different_question = self.client.post(
            f"/api/v1/practice/persona/conversations/{created['conversation_id']}/messages",
            headers=self.student_headers,
            json={
                "client_message_id": "retry-001",
                "expected_revision": 2,
                "question": "请改成另一道问题。",
            },
        )
        stale = self.client.post(
            f"/api/v1/practice/persona/conversations/{created['conversation_id']}/messages",
            headers=self.student_headers,
            json={
                "client_message_id": "retry-002",
                "expected_revision": 1,
                "question": "传世文献的边界是什么？",
            },
        )
        self.assertEqual(reused_for_different_question.status_code, 409)
        self.assertEqual(
            reused_for_different_question.json()["detail"]["code"],
            "persona_message_id_conflict",
        )
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(
            stale.json()["detail"]["code"],
            "persona_conversation_write_conflict",
        )

    def test_unknown_person_and_non_v5_release_are_rejected(self) -> None:
        unknown = self.client.post(
            "/api/v1/practice/persona/conversations",
            headers=self.student_headers,
            json={**self._create_payload(), "person_id": "person-not-published"},
        )
        self.assertEqual(unknown.status_code, 404, unknown.text)
        self.assertEqual(
            unknown.json()["detail"]["code"],
            "persona_person_unavailable",
        )

        with patch.object(
            practice_router.content_workflow,
            "get_current_release",
            return_value=None,
        ):
            missing_v5 = self.client.post(
                "/api/v1/practice/persona/conversations",
                headers=self.student_headers,
                json=self._create_payload(),
            )
        self.assertEqual(missing_v5.status_code, 404, missing_v5.text)
        self.assertEqual(
            missing_v5.json()["detail"]["code"],
            "persona_release_unavailable",
        )

    def test_boolean_revision_is_not_coerced_to_one(self) -> None:
        created = self._create_conversation()
        response = self.client.post(
            f"/api/v1/practice/persona/conversations/{created['conversation_id']}/messages",
            headers=self.student_headers,
            json={
                "client_message_id": "boolean-revision",
                "expected_revision": True,
                "question": "您是谁？",
            },
        )
        self.assertEqual(response.status_code, 422, response.text)

    def _create_conversation(self) -> dict:
        response = self.client.post(
            "/api/v1/practice/persona/conversations",
            headers=self.student_headers,
            json=self._create_payload(),
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    @staticmethod
    def _create_payload() -> dict:
        return {
            "course_id": "C-prequin-state",
            "lesson_id": "L101",
            "person_id": "person-7c4825d9",
        }

    def _send(
        self,
        conversation_id: str,
        *,
        message_id: str,
        revision: int,
        question: str,
    ) -> dict:
        response = self.client.post(
            f"/api/v1/practice/persona/conversations/{conversation_id}/messages",
            headers=self.student_headers,
            json={
                "client_message_id": message_id,
                "expected_revision": revision,
                "question": question,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _create_user(
        self,
        admin_headers: dict[str, str],
        *,
        username: str,
        password: str,
        roles: list[str],
    ) -> None:
        response = self.client.post(
            "/api/v1/auth/users",
            headers=admin_headers,
            json={
                "username": username,
                "password": password,
                "display_name": username,
                "roles": roles,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)

    def _login_headers(self, username: str, password: str) -> dict[str, str]:
        self.client.cookies.clear()
        response = self.client.post(
            "/api/v1/auth/token",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.client.cookies.clear()
        return {"Authorization": f"Bearer {response.json()['access_token']}"}


if __name__ == "__main__":
    unittest.main()
