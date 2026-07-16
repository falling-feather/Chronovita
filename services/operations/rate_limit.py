from __future__ import annotations

import hashlib
import json
import math
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable

from starlette.types import ASGIApp, Receive, Scope, Send


LOGIN_PATH = "/api/v1/auth/login"


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    retry_after_seconds: int = 0


@dataclass
class _TokenBucket:
    tokens: float
    updated_at: float


class LoginAttemptLimiter:
    """Bound password verification work with a process-local token bucket."""

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


class LoginRateLimitMiddleware:
    """Rate limit login without reading credentials or trusting forwarded headers."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_attempts: int,
        window_seconds: int,
        max_clients: int,
    ) -> None:
        self.app = app
        self.limiter = LoginAttemptLimiter(
            max_attempts=max_attempts,
            window_seconds=window_seconds,
            max_clients=max_clients,
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not _is_login_request(scope):
            await self.app(scope, receive, send)
            return

        scope.setdefault("state", {})["telemetry_route"] = LOGIN_PATH
        decision = self.limiter.consume(_client_key(scope))
        if decision.allowed:
            await self.app(scope, receive, send)
            return

        body = json.dumps(
            {
                "detail": {
                    "code": "auth_rate_limited",
                    "message": "Too many login attempts. Try again later.",
                }
            },
            separators=(",", ":"),
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                    (
                        b"retry-after",
                        str(decision.retry_after_seconds).encode("ascii"),
                    ),
                    (b"cache-control", b"no-store"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


def _is_login_request(scope: Scope) -> bool:
    return (
        scope["type"] == "http"
        and scope.get("method") == "POST"
        and scope.get("path") == LOGIN_PATH
    )


def _client_key(scope: Scope) -> str:
    client = scope.get("client")
    host = str(client[0]) if client else "unknown"
    return hashlib.sha256(host.encode("utf-8")).hexdigest()


__all__ = [
    "LOGIN_PATH",
    "LoginAttemptLimiter",
    "LoginRateLimitMiddleware",
    "RateLimitDecision",
]
