from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from starlette.requests import ClientDisconnect


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from routers import auth as auth_router
from routers import practice as practice_router
from settings import settings
from services import saga
from services.auth import (
    AuthServiceConfig,
    configure_identity,
    shutdown_identity,
)
from services.operations import ConcurrentCallLimiter, TokenBucketLimiter
from services.persistence.schema import ensure_current_schema


class PracticeSecurityApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.previous_settings = {
            "auth_mode": settings.auth_mode,
            "auth_session_ttl_seconds": settings.auth_session_ttl_seconds,
            "auth_cookie_name": settings.auth_cookie_name,
            "auth_cookie_secure": settings.auth_cookie_secure,
            "auth_bootstrap_username": settings.auth_bootstrap_username,
            "auth_bootstrap_password": settings.auth_bootstrap_password,
            "auth_bootstrap_display_name": settings.auth_bootstrap_display_name,
            "practice_llm_rate_limit_requests": (
                settings.practice_llm_rate_limit_requests
            ),
            "practice_llm_rate_limit_window_seconds": (
                settings.practice_llm_rate_limit_window_seconds
            ),
            "practice_llm_rate_limit_max_users": (
                settings.practice_llm_rate_limit_max_users
            ),
            "practice_llm_max_concurrent_per_user": (
                settings.practice_llm_max_concurrent_per_user
            ),
            "practice_llm_timeout_seconds": settings.practice_llm_timeout_seconds,
            "practice_llm_max_response_chars": (
                settings.practice_llm_max_response_chars
            ),
            "practice_saga_ttl_seconds": settings.practice_saga_ttl_seconds,
            "practice_saga_max_active_per_user": (
                settings.practice_saga_max_active_per_user
            ),
            "practice_saga_max_active_global": (
                settings.practice_saga_max_active_global
            ),
        }
        settings.auth_mode = "accounts"
        settings.auth_session_ttl_seconds = 3600
        settings.auth_cookie_name = "chronovita_practice_security_session"
        settings.auth_cookie_secure = False
        settings.auth_bootstrap_username = "root.admin"
        settings.auth_bootstrap_password = "Root password 123!"
        settings.auth_bootstrap_display_name = "Root Admin"
        settings.practice_llm_rate_limit_requests = 20
        settings.practice_llm_rate_limit_window_seconds = 60
        settings.practice_llm_rate_limit_max_users = 100
        settings.practice_llm_max_concurrent_per_user = 2
        settings.practice_llm_timeout_seconds = 90
        settings.practice_llm_max_response_chars = 8192
        settings.practice_saga_ttl_seconds = 3600
        settings.practice_saga_max_active_per_user = 1
        settings.practice_saga_max_active_global = 10

        self.previous_rate_limiter = practice_router._PRACTICE_LLM_RATE_LIMITER
        self.previous_concurrency_limiter = (
            practice_router._PRACTICE_LLM_CONCURRENCY_LIMITER
        )
        practice_router._PRACTICE_LLM_RATE_LIMITER = TokenBucketLimiter(
            max_attempts=settings.practice_llm_rate_limit_requests,
            window_seconds=settings.practice_llm_rate_limit_window_seconds,
            max_clients=settings.practice_llm_rate_limit_max_users,
        )
        practice_router._PRACTICE_LLM_CONCURRENCY_LIMITER = (
            ConcurrentCallLimiter(
                max_calls=settings.practice_llm_max_concurrent_per_user,
                max_clients=settings.practice_llm_rate_limit_max_users,
            )
        )
        saga.clear_states()

        database_path = Path(self.temp_dir.name) / "chronovita.db"

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
                        session_ttl_seconds=settings.auth_session_ttl_seconds,
                        bootstrap_username=settings.auth_bootstrap_username,
                        bootstrap_password=settings.auth_bootstrap_password,
                        bootstrap_display_name=settings.auth_bootstrap_display_name,
                    ),
                )
                yield
            finally:
                saga.clear_states()
                shutdown_identity()
                engine.dispose()

        app = FastAPI(lifespan=lifespan)
        app.include_router(auth_router.router, prefix="/api/v1/auth")
        app.include_router(practice_router.router, prefix="/api/v1/practice")
        self.app = app
        self.client = TestClient(app)
        self.client.__enter__()

        admin_token = self._login("root.admin", "Root password 123!")
        self.admin_headers = {"Authorization": f"Bearer {admin_token}"}
        self.client.cookies.clear()
        self.student_a = self._create_user(
            "student.a",
            "Student A password 123!",
            ["student"],
        )
        self.student_b = self._create_user(
            "student.b",
            "Student B password 123!",
            ["student"],
        )
        self._create_user(
            "teacher.one",
            "Teacher password 123!",
            ["teacher"],
        )
        self.student_a_headers = self._login_headers(
            "student.a",
            "Student A password 123!",
        )
        self.student_b_headers = self._login_headers(
            "student.b",
            "Student B password 123!",
        )
        self.teacher_headers = self._login_headers(
            "teacher.one",
            "Teacher password 123!",
        )
        self.lesson_id = saga.list_templates()[0]["lesson_id"]

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)
        saga.clear_states()
        practice_router._PRACTICE_LLM_RATE_LIMITER = self.previous_rate_limiter
        practice_router._PRACTICE_LLM_CONCURRENCY_LIMITER = (
            self.previous_concurrency_limiter
        )
        for key, value in self.previous_settings.items():
            setattr(settings, key, value)

    def test_saga_requires_student_and_hides_cross_owner_resources(self) -> None:
        request = {"lesson_id": self.lesson_id}
        unauthenticated = self.client.post(
            "/api/v1/practice/saga/start",
            json=request,
        )
        self.assertEqual(unauthenticated.status_code, 401, unauthenticated.text)
        forbidden_teacher = self.client.post(
            "/api/v1/practice/saga/start",
            headers=self.teacher_headers,
            json=request,
        )
        self.assertEqual(forbidden_teacher.status_code, 403, forbidden_teacher.text)

        started = self.client.post(
            "/api/v1/practice/saga/start",
            headers=self.student_a_headers,
            json=request,
        )
        self.assertEqual(started.status_code, 200, started.text)
        state = started.json()
        saga_id = state["saga_id"]
        self.assertNotIn("owner_user_id", state)

        cross_owner_get = self.client.get(
            f"/api/v1/practice/saga/{saga_id}",
            headers=self.student_b_headers,
        )
        cross_owner_act = self.client.post(
            f"/api/v1/practice/saga/{saga_id}/act",
            headers=self.student_b_headers,
            json={"action": "尝试推进局势"},
        )
        self.assertEqual(cross_owner_get.status_code, 404, cross_owner_get.text)
        self.assertEqual(cross_owner_act.status_code, 404, cross_owner_act.text)

        owner_get = self.client.get(
            f"/api/v1/practice/saga/{saga_id}",
            headers=self.student_a_headers,
        )
        self.assertEqual(owner_get.status_code, 200, owner_get.text)

        second_active = self.client.post(
            "/api/v1/practice/saga/start",
            headers=self.student_a_headers,
            json=request,
        )
        self.assertEqual(second_active.status_code, 429, second_active.text)
        self.assertEqual(
            second_active.json()["detail"]["code"],
            "saga_capacity_reached",
        )
        self.assertIn("Retry-After", second_active.headers)

        settings.practice_saga_max_active_global = 1
        global_capacity = self.client.post(
            "/api/v1/practice/saga/start",
            headers=self.student_b_headers,
            json=request,
        )
        self.assertEqual(global_capacity.status_code, 429, global_capacity.text)
        self.assertEqual(
            global_capacity.json()["detail"]["code"],
            "saga_capacity_reached",
        )

        async def fake_stream_chat(messages, *, model=None):
            del messages, model
            yield (
                "局势向前推进。"
                '\n[META]{"choices":["继续行动"],"summary_delta":"推进一步",'
                '"entities_delta":[],"flags_delta":{},"ended":false}'
            )

        with patch.object(practice_router.llm, "stream_chat", fake_stream_chat):
            acted = self.client.post(
                f"/api/v1/practice/saga/{saga_id}/act",
                headers=self.student_a_headers,
                json={"action": "尝试推进局势"},
            )
        self.assertEqual(acted.status_code, 200, acted.text)
        self.assertIn("[META]", acted.text)
        advanced = self.client.get(
            f"/api/v1/practice/saga/{saga_id}",
            headers=self.student_a_headers,
        )
        self.assertEqual(advanced.json()["step"], 1)

    def test_ask_is_bounded_authenticated_and_rate_limited(self) -> None:
        calls: list[list[dict]] = []

        async def fake_stream_chat(messages, *, model=None):
            del model
            calls.append(messages)
            yield "受约束回答"

        payload = {
            "persona": "expert",
            "lesson_id": self.lesson_id,
            "lesson_title": "测试课程",
            "user_message": "请解释这段历史。",
            "history": [{"role": "assistant", "content": "可以。"}],
        }
        with patch.object(practice_router.llm, "stream_chat", fake_stream_chat):
            unauthenticated = self.client.post(
                "/api/v1/practice/ask",
                json=payload,
            )
            forbidden_teacher = self.client.post(
                "/api/v1/practice/ask",
                headers=self.teacher_headers,
                json=payload,
            )
            oversized = self.client.post(
                "/api/v1/practice/ask",
                headers=self.student_a_headers,
                json={**payload, "user_message": "x" * 2001},
            )
        self.assertEqual(unauthenticated.status_code, 401, unauthenticated.text)
        self.assertEqual(forbidden_teacher.status_code, 403, forbidden_teacher.text)
        self.assertEqual(oversized.status_code, 422, oversized.text)
        self.assertEqual(calls, [])
        anonymous_info = self.client.get("/api/v1/practice/llm/info")
        student_info = self.client.get(
            "/api/v1/practice/llm/info",
            headers=self.student_a_headers,
        )
        self.assertEqual(anonymous_info.status_code, 401, anonymous_info.text)
        self.assertEqual(student_info.status_code, 200, student_info.text)
        self.assertIn("provider", student_info.json())

        practice_router._PRACTICE_LLM_RATE_LIMITER = TokenBucketLimiter(
            max_attempts=1,
            window_seconds=3600,
            max_clients=100,
        )
        with patch.object(practice_router.llm, "stream_chat", fake_stream_chat):
            accepted = self.client.post(
                "/api/v1/practice/ask",
                headers=self.student_a_headers,
                json=payload,
            )
            limited = self.client.post(
                "/api/v1/practice/ask",
                headers=self.student_a_headers,
                json=payload,
            )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.text, "受约束回答")
        self.assertEqual(len(calls), 1)
        self.assertEqual(limited.status_code, 429, limited.text)
        self.assertEqual(
            limited.json()["detail"]["code"],
            "practice_llm_rate_limited",
        )
        self.assertIn("Retry-After", limited.headers)

    def test_canvas_generation_is_bounded_and_uses_the_llm_quota(self) -> None:
        calls: list[list[dict]] = []

        async def fake_stream_chat(messages, *, model=None):
            del model
            calls.append(messages)
            yield (
                '{"nodes":[{"id":"n1","label":"测试","category":"概念"}],'
                '"edges":[]}'
            )

        payload = {
            "lesson_id": self.lesson_id,
            "lesson_title": "测试课程",
            "abstract": "用于验证知识画板生成边界。",
            "keywords": ["测试"],
            "seed": [],
        }
        with patch.object(practice_router.llm, "stream_chat", fake_stream_chat):
            unauthenticated = self.client.post(
                "/api/v1/practice/canvas/generate",
                json=payload,
            )
            forbidden_teacher = self.client.post(
                "/api/v1/practice/canvas/generate",
                headers=self.teacher_headers,
                json=payload,
            )
            oversized = self.client.post(
                "/api/v1/practice/canvas/generate",
                headers=self.student_a_headers,
                json={**payload, "abstract": "x" * 4001},
            )
        self.assertEqual(unauthenticated.status_code, 401, unauthenticated.text)
        self.assertEqual(forbidden_teacher.status_code, 403, forbidden_teacher.text)
        self.assertEqual(oversized.status_code, 422, oversized.text)
        self.assertEqual(calls, [])

        practice_router._PRACTICE_LLM_RATE_LIMITER = TokenBucketLimiter(
            max_attempts=1,
            window_seconds=3600,
            max_clients=100,
        )
        with patch.object(practice_router.llm, "stream_chat", fake_stream_chat):
            accepted = self.client.post(
                "/api/v1/practice/canvas/generate",
                headers=self.student_a_headers,
                json=payload,
            )
            limited = self.client.post(
                "/api/v1/practice/canvas/generate",
                headers=self.student_a_headers,
                json=payload,
            )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["nodes"][0]["id"], "n1")
        self.assertEqual(len(calls), 1)
        self.assertEqual(limited.status_code, 429, limited.text)
        self.assertEqual(
            limited.json()["detail"]["code"],
            "practice_llm_rate_limited",
        )

        practice_router._PRACTICE_LLM_RATE_LIMITER = TokenBucketLimiter(
            max_attempts=10,
            window_seconds=3600,
            max_clients=100,
        )
        settings.practice_llm_max_response_chars = 1024

        async def oversized_stream_chat(messages, *, model=None):
            del messages, model
            yield "x" * 1025

        with patch.object(
            practice_router.llm,
            "stream_chat",
            oversized_stream_chat,
        ):
            oversized_output = self.client.post(
                "/api/v1/practice/canvas/generate",
                headers=self.student_a_headers,
                json=payload,
            )
        self.assertEqual(oversized_output.status_code, 502, oversized_output.text)
        self.assertEqual(
            oversized_output.json()["detail"]["code"],
            "practice_llm_output_too_large",
        )
        self.assertEqual(
            practice_router._PRACTICE_LLM_CONCURRENCY_LIMITER.tracked_clients,
            0,
        )

    def test_saga_ttl_action_lease_and_concurrency_limiter(self) -> None:
        state = saga.start(
            self.lesson_id,
            owner_user_id=self.student_a["user_id"],
            ttl_seconds=60,
            max_active_per_owner=2,
            max_active_global=10,
        )
        self.assertIsNotNone(state)
        assert state is not None
        lease = saga.begin_act(
            state.saga_id,
            owner_user_id=self.student_a["user_id"],
            ttl_seconds=60,
        )
        self.assertIs(lease, state)
        with self.assertRaises(saga.SagaBusyError):
            saga.begin_act(
                state.saga_id,
                owner_user_id=self.student_a["user_id"],
                ttl_seconds=60,
            )
        saga.release_act(state)

        limiter = ConcurrentCallLimiter(max_calls=1, max_clients=2)
        self.assertTrue(limiter.acquire(self.student_a["user_id"]))
        self.assertFalse(limiter.acquire(self.student_a["user_id"]))
        limiter.release(self.student_a["user_id"])
        self.assertTrue(limiter.acquire(self.student_a["user_id"]))
        limiter.release(self.student_a["user_id"])
        self.assertEqual(limiter.tracked_clients, 0)

        state.last_accessed_at = time.monotonic() - 61
        expired = saga.get(
            state.saga_id,
            owner_user_id=self.student_a["user_id"],
            ttl_seconds=60,
        )
        self.assertIsNone(expired)

    def test_saga_stream_failure_rolls_back_and_releases_action_lease(self) -> None:
        state = saga.start(
            self.lesson_id,
            owner_user_id=self.student_a["user_id"],
            ttl_seconds=60,
            max_active_per_owner=2,
            max_active_global=10,
        )
        self.assertIsNotNone(state)
        assert state is not None
        leased = saga.begin_act(
            state.saga_id,
            owner_user_id=self.student_a["user_id"],
            ttl_seconds=60,
        )
        self.assertIs(leased, state)
        original_history = list(state.history)

        async def failing_stream_chat(messages, *, model=None):
            del messages, model
            yield "尚未提交的叙事片段"
            raise RuntimeError("provider failed")

        async def consume() -> None:
            async for _ in saga.act_stream(
                state,
                "尝试推进局势",
                max_response_chars=8192,
            ):
                pass

        with patch.object(practice_router.llm, "stream_chat", failing_stream_chat):
            with self.assertRaisesRegex(RuntimeError, "provider failed"):
                asyncio.run(consume())

        self.assertEqual(state.history, original_history)
        self.assertFalse(state.in_progress)
        retry = saga.begin_act(
            state.saga_id,
            owner_user_id=self.student_a["user_id"],
            ttl_seconds=60,
        )
        self.assertIs(retry, state)
        saga.release_act(state)

    def test_saga_api_stream_failure_releases_every_lease(self) -> None:
        started = self.client.post(
            "/api/v1/practice/saga/start",
            headers=self.student_a_headers,
            json={"lesson_id": self.lesson_id},
        )
        self.assertEqual(started.status_code, 200, started.text)
        saga_id = started.json()["saga_id"]

        async def failing_stream_chat(messages, *, model=None):
            del messages, model
            yield "尚未提交的叙事片段"
            raise RuntimeError("provider failed")

        with patch.object(practice_router.llm, "stream_chat", failing_stream_chat):
            with self.assertRaisesRegex(RuntimeError, "provider failed"):
                self.client.post(
                    f"/api/v1/practice/saga/{saga_id}/act",
                    headers=self.student_a_headers,
                    json={"action": "尝试推进局势"},
                )

        state = saga.get(
            saga_id,
            owner_user_id=self.student_a["user_id"],
            ttl_seconds=60,
        )
        self.assertIsNotNone(state)
        assert state is not None
        self.assertFalse(state.in_progress)
        self.assertEqual(state.step, 0)
        self.assertEqual(
            [item["role"] for item in state.history],
            ["narrator"],
        )
        self.assertEqual(
            practice_router._PRACTICE_LLM_CONCURRENCY_LIMITER.tracked_clients,
            0,
        )

    def test_saga_disconnect_releases_leases_before_and_after_headers(self) -> None:
        async def fake_stream_chat(messages, *, model=None):
            del messages, model
            yield "这是第一段流式正文。"
            await asyncio.sleep(0)
            yield (
                '\n[META]{"choices":["继续"],"summary_delta":"推进",'
                '"entities_delta":[],"flags_delta":{},"ended":false}'
            )

        async def invoke(saga_id: str, *, fail_on: str) -> None:
            body = json.dumps(
                {"action": "尝试推进局势"},
                ensure_ascii=False,
            ).encode("utf-8")
            received = False

            async def receive():
                nonlocal received
                if not received:
                    received = True
                    return {
                        "type": "http.request",
                        "body": body,
                        "more_body": False,
                    }
                return {"type": "http.disconnect"}

            async def send(message):
                if message["type"] == f"http.response.{fail_on}":
                    raise ConnectionError(f"disconnect during {fail_on}")

            path = f"/api/v1/practice/saga/{saga_id}/act"
            scope = {
                "type": "http",
                "asgi": {"version": "3.0", "spec_version": "2.4"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode("ascii"),
                "query_string": b"",
                "headers": [
                    (b"host", b"testserver"),
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (
                        b"authorization",
                        self.student_a_headers["Authorization"].encode("ascii"),
                    ),
                ],
                "client": ("127.0.0.1", 54321),
                "server": ("testserver", 80),
                "root_path": "",
                "state": {},
            }
            await self.app(scope, receive, send)

        for fail_on in ("start", "body"):
            with self.subTest(fail_on=fail_on):
                saga.clear_states()
                started = self.client.post(
                    "/api/v1/practice/saga/start",
                    headers=self.student_a_headers,
                    json={"lesson_id": self.lesson_id},
                )
                self.assertEqual(started.status_code, 200, started.text)
                saga_id = started.json()["saga_id"]

                with patch.object(
                    practice_router.llm,
                    "stream_chat",
                    fake_stream_chat,
                ):
                    with self.assertRaises(ClientDisconnect):
                        asyncio.run(invoke(saga_id, fail_on=fail_on))

                state = saga.get(
                    saga_id,
                    owner_user_id=self.student_a["user_id"],
                    ttl_seconds=60,
                )
                self.assertIsNotNone(state)
                assert state is not None
                self.assertFalse(state.in_progress)
                self.assertEqual(state.step, 0)
                self.assertEqual(
                    [item["role"] for item in state.history],
                    ["narrator"],
                )
                self.assertEqual(
                    practice_router
                    ._PRACTICE_LLM_CONCURRENCY_LIMITER
                    .tracked_clients,
                    0,
                )

    def test_saga_enforces_output_and_step_limits(self) -> None:
        state = saga.start(
            self.lesson_id,
            owner_user_id=self.student_a["user_id"],
            ttl_seconds=60,
            max_active_per_owner=2,
            max_active_global=10,
        )
        self.assertIsNotNone(state)
        assert state is not None
        state.step = 6
        saga.begin_act(
            state.saga_id,
            owner_user_id=self.student_a["user_id"],
            ttl_seconds=60,
        )

        async def valid_stream_chat(messages, *, model=None):
            del messages, model
            yield (
                "最后一步。"
                '\n[META]{"choices":["不应继续"],"summary_delta":"完成",'
                '"entities_delta":[],"flags_delta":{},"ended":false}'
            )

        async def consume(target, *, max_response_chars: int) -> str:
            chunks = []
            async for chunk in saga.act_stream(
                target,
                "完成最后一步",
                max_response_chars=max_response_chars,
            ):
                chunks.append(chunk)
            return "".join(chunks)

        with patch.object(practice_router.llm, "stream_chat", valid_stream_chat):
            response = asyncio.run(consume(state, max_response_chars=8192))
        self.assertTrue(state.ended)
        self.assertEqual(state.step, 7)
        self.assertEqual(state.choices, [])
        self.assertIn('"ended": true', response)
        with self.assertRaises(saga.SagaEndedError):
            saga.begin_act(
                state.saga_id,
                owner_user_id=self.student_a["user_id"],
                ttl_seconds=60,
            )
        with self.assertRaises(saga.SagaCapacityError) as capacity_error:
            saga.start(
                self.lesson_id,
                owner_user_id=self.student_a["user_id"],
                ttl_seconds=60,
                max_active_per_owner=1,
                max_active_global=10,
            )
        self.assertEqual(capacity_error.exception.scope, "owner")

        bounded = saga.start(
            self.lesson_id,
            owner_user_id=self.student_a["user_id"],
            ttl_seconds=60,
            max_active_per_owner=2,
            max_active_global=10,
        )
        self.assertIsNotNone(bounded)
        assert bounded is not None
        saga.begin_act(
            bounded.saga_id,
            owner_user_id=self.student_a["user_id"],
            ttl_seconds=60,
        )
        original_history = list(bounded.history)

        async def oversized_stream_chat(messages, *, model=None):
            del messages, model
            yield "x" * 1025

        with patch.object(
            practice_router.llm,
            "stream_chat",
            oversized_stream_chat,
        ):
            with self.assertRaisesRegex(RuntimeError, "exceeded the limit"):
                asyncio.run(consume(bounded, max_response_chars=1024))
        self.assertEqual(bounded.history, original_history)
        self.assertEqual(bounded.step, 0)
        self.assertFalse(bounded.in_progress)

        state.last_accessed_at = time.monotonic() - 61
        self.assertIsNone(
            saga.get(
                state.saga_id,
                owner_user_id=self.student_a["user_id"],
                ttl_seconds=60,
            )
        )

    def test_malformed_saga_meta_falls_back_to_a_consistent_state(self) -> None:
        state = saga.start(
            self.lesson_id,
            owner_user_id=self.student_a["user_id"],
            ttl_seconds=60,
            max_active_per_owner=2,
            max_active_global=10,
        )
        self.assertIsNotNone(state)
        assert state is not None
        saga.begin_act(
            state.saga_id,
            owner_user_id=self.student_a["user_id"],
            ttl_seconds=60,
        )

        async def malformed_stream_chat(messages, *, model=None):
            del messages, model
            yield (
                "模型仍返回了可展示叙事。"
                '\n[META]{"choices":["继续"],"summary_delta":"不应写入",'
                '"entities_delta":["not-an-object"],'
                '"flags_delta":{"unsafe":"value"},"ended":false}'
            )

        async def consume() -> str:
            chunks = []
            async for chunk in saga.act_stream(
                state,
                "尝试推进局势",
                max_response_chars=8192,
            ):
                chunks.append(chunk)
            return "".join(chunks)

        with patch.object(
            practice_router.llm,
            "stream_chat",
            malformed_stream_chat,
        ):
            response = asyncio.run(consume())

        self.assertEqual(state.step, 1)
        self.assertFalse(state.in_progress)
        self.assertEqual(
            [item["role"] for item in state.history],
            ["narrator", "player", "narrator"],
        )
        self.assertEqual(state.summary, "")
        self.assertEqual(state.entities, {})
        self.assertEqual(state.flags, {})
        self.assertEqual(state.choices, [])
        self.assertIn('"step": 1', response)

    def _create_user(
        self,
        username: str,
        password: str,
        roles: list[str],
    ) -> dict:
        response = self.client.post(
            "/api/v1/auth/users",
            headers=self.admin_headers,
            json={
                "username": username,
                "password": password,
                "display_name": username,
                "roles": roles,
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def _login_headers(self, username: str, password: str) -> dict[str, str]:
        token = self._login(username, password)
        self.client.cookies.clear()
        return {"Authorization": f"Bearer {token}"}

    def _login(self, username: str, password: str) -> str:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": username, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["access_token"]


if __name__ == "__main__":
    unittest.main()
