from __future__ import annotations

import io
import json
import logging
import sys
import unittest
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
for import_root in (REPO_ROOT, API_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from services.operations import (
    RequestTelemetryMiddleware,
    current_request_id,
    request_id_for_state,
)
from services.operations.telemetry import ACCESS_LOGGER


class RequestTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        self.previous_level = ACCESS_LOGGER.level
        self.previous_propagate = ACCESS_LOGGER.propagate
        self.previous_disabled = ACCESS_LOGGER.disabled
        ACCESS_LOGGER.addHandler(self.handler)
        ACCESS_LOGGER.setLevel(logging.INFO)
        ACCESS_LOGGER.propagate = False
        ACCESS_LOGGER.disabled = False

        app = FastAPI()
        app.add_middleware(RequestTelemetryMiddleware, handle_exceptions=True)

        @app.post("/records/{record_id}")
        async def record(record_id: str, request: Request):
            first = request_id_for_state(request.state)
            second = request_id_for_state(request.state, "ignored-client-id")
            return JSONResponse(
                {
                    "first": first,
                    "second": second,
                    "context": current_request_id(),
                },
                headers={"X-Request-ID": "downstream-value-must-be-replaced"},
            )

        @app.get("/explode")
        async def explode():
            raise RuntimeError("private-student-text-must-not-leak")

        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        ACCESS_LOGGER.removeHandler(self.handler)
        ACCESS_LOGGER.setLevel(self.previous_level)
        ACCESS_LOGGER.propagate = self.previous_propagate
        ACCESS_LOGGER.disabled = self.previous_disabled

    def test_request_id_and_access_log_are_correlated_and_data_minimal(self):
        request_id = "teacher-request-001"
        secrets = (
            "private-record-id",
            "private-query-answer",
            "private-bearer-token",
            "private-cookie-token",
            "private-student-original-text",
        )
        response = self.client.post(
            f"/records/{secrets[0]}?answer={secrets[1]}",
            headers={
                "X-Request-ID": request_id,
                "Authorization": f"Bearer {secrets[2]}",
                "Cookie": f"chronovita_session={secrets[3]}",
                "User-Agent": "Chronovita telemetry test",
            },
            json={"text": secrets[4]},
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["X-Request-ID"], request_id)
        self.assertEqual(
            response.json(),
            {"first": request_id, "second": request_id, "context": request_id},
        )
        event, raw_log = self._last_event()
        self.assertEqual(event["event"], "http.request.completed")
        self.assertEqual(event["request_id"], request_id)
        self.assertEqual(event["route"], "/records/{record_id}")
        self.assertEqual(event["method"], "POST")
        self.assertEqual(event["status_code"], 200)
        self.assertRegex(event["client"], r"^[0-9a-f]{24}$")
        for secret in secrets:
            self.assertNotIn(secret, raw_log)
        self.assertIsNone(current_request_id())

    def test_invalid_request_id_is_replaced_and_downstream_cannot_override_it(self):
        response = self.client.post(
            "/records/public-id",
            headers={"X-Request-ID": "invalid request id with spaces"},
            json={"text": "safe"},
        )

        generated = response.headers["X-Request-ID"]
        self.assertRegex(generated, r"^req_[0-9a-f]{32}$")
        self.assertNotEqual(generated, "downstream-value-must-be-replaced")
        self.assertEqual(response.json()["first"], generated)
        self.assertEqual(self._last_event()[0]["request_id"], generated)

    def test_unmatched_routes_do_not_log_the_requested_path(self):
        private_path = "private-unmatched-resource"
        response = self.client.get(f"/{private_path}")

        self.assertEqual(response.status_code, 404, response.text)
        event, raw_log = self._last_event()
        self.assertEqual(event["route"], "<unmatched>")
        self.assertEqual(event["status_code"], 404)
        self.assertNotIn(private_path, raw_log)

    def test_unhandled_exception_is_sanitized_without_logging_its_message(self):
        response = self.client.get(
            "/explode",
            headers={"X-Request-ID": "error-request-001"},
        )

        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(response.headers["X-Request-ID"], "error-request-001")
        self.assertEqual(
            response.json()["detail"]["code"],
            "internal_server_error",
        )
        event, raw_log = self._last_event()
        self.assertEqual(event["error_type"], "RuntimeError")
        self.assertEqual(event["status_code"], 500)
        self.assertNotIn("private-student-text-must-not-leak", raw_log)

    def _last_event(self) -> tuple[dict, str]:
        lines = [line for line in self.stream.getvalue().splitlines() if line]
        self.assertTrue(lines)
        return json.loads(lines[-1]), lines[-1]


if __name__ == "__main__":
    unittest.main()
