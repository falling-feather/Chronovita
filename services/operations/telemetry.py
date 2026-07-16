from __future__ import annotations

import hashlib
import json
import logging
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send


ACCESS_LOGGER = logging.getLogger("chronovita.access")
_REQUEST_ID = ContextVar[str | None]("chronovita_request_id", default=None)
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,100}\Z")
_REQUEST_ID_HEADER = b"x-request-id"


def normalize_request_id(value: str | None) -> str | None:
    candidate = (value or "").strip()
    if candidate and _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return None


def new_request_id() -> str:
    return f"req_{uuid4().hex}"


def current_request_id() -> str | None:
    return _REQUEST_ID.get()


def configure_runtime_logging() -> None:
    """Use the structured access event as the only HTTP access log."""

    ACCESS_LOGGER.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").disabled = True


class RequestTelemetryMiddleware:
    """Attach a stable request ID and emit one data-minimal JSON access event."""

    def __init__(self, app: ASGIApp, *, handle_exceptions: bool = False) -> None:
        self.app = app
        self.handle_exceptions = handle_exceptions

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        supplied = _header(scope, _REQUEST_ID_HEADER)
        request_id = normalize_request_id(supplied) or new_request_id()
        scope.setdefault("state", {})["request_id"] = request_id
        context_token = _REQUEST_ID.set(request_id)
        started = perf_counter()
        status_code = 500
        response_started = False
        error_type: str | None = None

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_started, status_code
            if message["type"] == "http.response.start":
                response_started = True
                status_code = int(message["status"])
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != _REQUEST_ID_HEADER
                ]
                headers.append((_REQUEST_ID_HEADER, request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            error_type = type(exc).__name__
            status_code = 500
            if not self.handle_exceptions or response_started:
                raise
            body = b'{"detail":{"code":"internal_server_error","message":"Unexpected server error."}}'
            await send_with_request_id(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send_with_request_id(
                {
                    "type": "http.response.body",
                    "body": body,
                }
            )
        finally:
            _log_access_event(
                scope,
                request_id=request_id,
                status_code=status_code,
                duration_ms=(perf_counter() - started) * 1000,
                error_type=error_type,
            )
            _REQUEST_ID.reset(context_token)


def request_id_for_state(state: object, supplied: str | None = None) -> str:
    existing = normalize_request_id(getattr(state, "request_id", None))
    if existing is not None:
        return existing
    resolved = normalize_request_id(supplied) or new_request_id()
    setattr(state, "request_id", resolved)
    return resolved


def _log_access_event(
    scope: Scope,
    *,
    request_id: str,
    status_code: int,
    duration_ms: float,
    error_type: str | None,
) -> None:
    route = getattr(scope.get("route"), "path", None) or "<unmatched>"
    event = {
        "client": _client_fingerprint(scope),
        "duration_ms": round(max(duration_ms, 0.0), 3),
        "event": "http.request.completed",
        "method": str(scope.get("method", "")),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "route": route,
        "status_code": status_code,
    }
    if error_type is not None:
        event["error_type"] = error_type
    ACCESS_LOGGER.info(
        json.dumps(
            event,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _client_fingerprint(scope: Scope) -> str:
    client = scope.get("client")
    host = str(client[0]) if client else "unknown"
    agent = _header(scope, b"user-agent")[:200]
    return hashlib.sha256(f"{host}\x1f{agent}".encode("utf-8")).hexdigest()[:24]


def _header(scope: Scope, name: bytes) -> str:
    for header_name, value in scope.get("headers", []):
        if header_name.lower() == name:
            return value.decode("latin-1")
    return ""
