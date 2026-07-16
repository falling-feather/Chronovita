from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from starlette.middleware.trustedhost import TrustedHostMiddleware


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.operations import (
    LOGIN_PATH,
    LoginAttemptLimiter,
    LoginRateLimitMiddleware,
    RequestTelemetryMiddleware,
)


class LoginAttemptLimiterTests(unittest.TestCase):
    def test_token_bucket_refills_and_keeps_bounded_client_state(self):
        now = [0.0]
        limiter = LoginAttemptLimiter(
            max_attempts=2,
            window_seconds=10,
            max_clients=2,
            clock=lambda: now[0],
        )

        self.assertTrue(limiter.consume("client-a").allowed)
        self.assertTrue(limiter.consume("client-a").allowed)
        limited = limiter.consume("client-a")
        self.assertFalse(limited.allowed)
        self.assertEqual(limited.retry_after_seconds, 5)

        now[0] = 5.0
        self.assertTrue(limiter.consume("client-a").allowed)
        limiter.consume("client-b")
        limiter.consume("client-c")
        self.assertEqual(limiter.tracked_clients, 2)


class RuntimeSecurityMiddlewareTests(unittest.TestCase):
    def setUp(self):
        self.handled_payloads: list[dict] = []
        app = FastAPI()
        app.add_middleware(
            LoginRateLimitMiddleware,
            max_attempts=2,
            window_seconds=60,
            max_clients=8,
        )
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["testserver"],
            www_redirect=False,
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["https://teacher.example.test"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "Retry-After"],
        )
        app.add_middleware(RequestTelemetryMiddleware)

        @app.post(LOGIN_PATH)
        async def login(request: Request):
            payload = await request.json()
            self.handled_payloads.append(payload)
            return {"accepted": True}

        @app.post("/api/v1/other")
        async def other():
            return {"accepted": True}

        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_login_limit_does_not_read_credentials_and_returns_correlated_429(self):
        headers = {
            "Origin": "https://teacher.example.test",
            "X-Request-ID": "login-limit-test",
        }
        payload = {
            "username": "teacher.one",
            "password": "password-must-not-enter-logs",
        }

        self.assertEqual(
            self.client.post(LOGIN_PATH, json=payload, headers=headers).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(LOGIN_PATH, json=payload, headers=headers).status_code,
            200,
        )
        with self.assertLogs("chronovita.access", level="INFO") as captured:
            limited = self.client.post(LOGIN_PATH, json=payload, headers=headers)

        self.assertEqual(limited.status_code, 429, limited.text)
        self.assertEqual(
            limited.json(),
            {
                "detail": {
                    "code": "auth_rate_limited",
                    "message": "Too many login attempts. Try again later.",
                }
            },
        )
        self.assertEqual(limited.headers["X-Request-ID"], "login-limit-test")
        self.assertGreaterEqual(int(limited.headers["Retry-After"]), 1)
        self.assertEqual(
            limited.headers["access-control-allow-origin"],
            "https://teacher.example.test",
        )
        self.assertEqual(len(self.handled_payloads), 2)

        event = json.loads(captured.records[-1].message)
        self.assertEqual(event["route"], LOGIN_PATH)
        self.assertEqual(event["status_code"], 429)
        self.assertNotIn(payload["password"], captured.output[0])

    def test_non_login_route_is_not_limited(self):
        responses = [self.client.post("/api/v1/other") for _ in range(4)]
        self.assertEqual([response.status_code for response in responses], [200] * 4)

    def test_untrusted_host_is_rejected_before_login_handler(self):
        rejected = self.client.post(
            LOGIN_PATH,
            json={"username": "teacher", "password": "secret"},
            headers={"Host": "attacker.example.test"},
        )

        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertRegex(rejected.headers["X-Request-ID"], r"^req_[0-9a-f]{32}$")
        self.assertEqual(self.handled_payloads, [])


if __name__ == "__main__":
    unittest.main()
