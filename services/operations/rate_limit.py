from __future__ import annotations

import hashlib
import json
import math
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable, Mapping

from starlette.types import ASGIApp, Receive, Scope, Send


LOGIN_PATH = "/api/v1/auth/login"
TOKEN_PATH = "/api/v1/auth/token"
LOGIN_PATHS = frozenset((LOGIN_PATH, TOKEN_PATH))


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int = 0


@dataclass
class _TokenBucket:
    tokens: float
    updated_at: float


class TokenBucketLimiter:
    """Bound calls per key with a process-local token bucket."""

    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: int,
        max_clients: int,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if window_seconds < 1:
            raise ValueError("window_seconds must be positive")
        if max_clients < 1:
            raise ValueError("max_clients must be positive")
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.max_clients = max_clients
        self._clock = clock
        self._refill_rate = max_attempts / window_seconds
        self._buckets: OrderedDict[str, _TokenBucket] = OrderedDict()
        self._lock = Lock()

    def consume(self, client_key: str) -> RateLimitDecision:
        now = self._clock()
        with self._lock:
            bucket = self._buckets.get(client_key)
            if bucket is None:
                self._make_room()
                bucket = _TokenBucket(
                    tokens=float(self.max_attempts),
                    updated_at=now,
                )
                self._buckets[client_key] = bucket
            else:
                elapsed = max(now - bucket.updated_at, 0.0)
                bucket.tokens = min(
                    float(self.max_attempts),
                    bucket.tokens + elapsed * self._refill_rate,
                )
                bucket.updated_at = now
                self._buckets.move_to_end(client_key)

            if bucket.tokens < 1.0:
                retry_after = max(
                    1,
                    math.ceil((1.0 - bucket.tokens) / self._refill_rate),
                )
                return RateLimitDecision(
                    allowed=False,
                    remaining=0,
                    retry_after_seconds=retry_after,
                )

            bucket.tokens -= 1.0
            return RateLimitDecision(
                allowed=True,
                remaining=max(0, math.floor(bucket.tokens)),
            )

    @property
    def tracked_clients(self) -> int:
        with self._lock:
            return len(self._buckets)

    def _make_room(self) -> None:
        while len(self._buckets) >= self.max_clients:
            self._buckets.popitem(last=False)


class LoginAttemptLimiter(TokenBucketLimiter):
    """Bound password verification work with a process-local token bucket."""


class ConcurrentCallLimiter:
    """Bound concurrent calls per key without evicting active leases."""

    def __init__(self, *, max_calls: int, max_clients: int) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be positive")
        if max_clients < 1:
            raise ValueError("max_clients must be positive")
        self.max_calls = max_calls
        self.max_clients = max_clients
        self._active: OrderedDict[str, int] = OrderedDict()
        self._lock = Lock()

    def acquire(self, client_key: str) -> bool:
        with self._lock:
            active = self._active.get(client_key, 0)
            if active >= self.max_calls:
                return False
            if client_key not in self._active and len(self._active) >= self.max_clients:
                return False
            self._active[client_key] = active + 1
            self._active.move_to_end(client_key)
            return True

    def release(self, client_key: str) -> None:
        with self._lock:
            active = self._active.get(client_key)
            if active is None:
                return
            if active <= 1:
                self._active.pop(client_key, None)
                return
            self._active[client_key] = active - 1

    @property
    def tracked_clients(self) -> int:
        with self._lock:
            return len(self._active)


class LoginRateLimitMiddleware:
    """Rate limit login without reading credentials or trusting forwarded headers."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_attempts: int,
        window_seconds: int,
        max_clients: int,
        trusted_cookie_origins: tuple[str, ...] | None = None,
    ) -> None:
        self.app = app
        self.limiter = LoginAttemptLimiter(
            max_attempts=max_attempts,
            window_seconds=window_seconds,
            max_clients=max_clients,
        )
        self.trusted_cookie_origins = (
            frozenset(trusted_cookie_origins)
            if trusted_cookie_origins is not None
            else None
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _is_login_request(scope):
            await self.app(scope, receive, send)
            return

        scope.setdefault("state", {})["telemetry_route"] = scope["path"]
        rejection = _login_request_rejection(
            scope,
            trusted_cookie_origins=self.trusted_cookie_origins,
        )
        if rejection is not None:
            rejection_status, rejection_code, rejection_message = rejection
            await _send_error(
                send,
                status_code=rejection_status,
                code=rejection_code,
                message=rejection_message,
            )
            return

        decision = self.limiter.consume(_client_key(scope))
        if decision.allowed:
            await self.app(scope, receive, send)
            return

        await _send_error(
            send,
            status_code=429,
            code="auth_rate_limited",
            message="Too many login attempts. Try again later.",
            extra_headers={
                "retry-after": str(decision.retry_after_seconds),
            },
        )


def _is_login_request(scope: Scope) -> bool:
    return (
        scope["type"] == "http"
        and scope.get("method") == "POST"
        and scope.get("path") in LOGIN_PATHS
    )


def _client_key(scope: Scope) -> str:
    client = scope.get("client")
    host = str(client[0]) if client else "unknown"
    return hashlib.sha256(host.encode("utf-8")).hexdigest()


def _login_request_rejection(
    scope: Scope,
    *,
    trusted_cookie_origins: frozenset[str] | None,
) -> tuple[int, str, str] | None:
    content_types = _header_values(scope, b"content-type")
    if (
        len(content_types) != 1
        or content_types[0].split(";", 1)[0].strip().lower()
        != "application/json"
    ):
        return (
            415,
            "unsupported_media_type",
            "Login requests require application/json.",
        )
    if scope.get("path") != LOGIN_PATH or trusted_cookie_origins is None:
        return None
    origins = _header_values(scope, b"origin")
    if len(origins) != 1 or origins[0].strip() not in trusted_cookie_origins:
        return (
            403,
            "csrf_origin_rejected",
            "Cookie login requires a trusted Origin.",
        )
    return None


def _header_values(scope: Scope, name: bytes) -> tuple[str, ...]:
    return tuple(
        value.decode("latin-1")
        for header_name, value in scope.get("headers", ())
        if header_name.lower() == name
    )


async def _send_error(
    send: Send,
    *,
    status_code: int,
    code: str,
    message: str,
    extra_headers: Mapping[str, str] | None = None,
) -> None:
    body = json.dumps(
        {"detail": {"code": code, "message": message}},
        separators=(",", ":"),
    ).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
        (b"cache-control", b"no-store"),
    ]
    headers.extend(
        (name.encode("ascii"), value.encode("ascii"))
        for name, value in (extra_headers or {}).items()
    )
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": headers,
        }
    )
    await send({"type": "http.response.body", "body": body})


__all__ = [
    "ConcurrentCallLimiter",
    "LOGIN_PATH",
    "LOGIN_PATHS",
    "LoginAttemptLimiter",
    "LoginRateLimitMiddleware",
    "RateLimitDecision",
    "TOKEN_PATH",
    "TokenBucketLimiter",
]
