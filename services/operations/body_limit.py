from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _RequestBodyTooLarge(Exception):
    pass


class RequestBodyLimitMiddleware:
    """Reject oversized request bodies before route parsing or authentication."""

    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        if max_body_bytes < 1:
            raise ValueError("max_body_bytes must be positive")
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if _declared_body_too_large(scope, self.max_body_bytes):
            await _send_too_large(send)
            return

        received_bytes = 0
        response_started = False

        async def receive_limited() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_bytes:
                    raise _RequestBodyTooLarge
            return message

        async def track_response(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive_limited, track_response)
        except _RequestBodyTooLarge:
            if response_started:
                raise
            await _send_too_large(send)


def _declared_body_too_large(scope: Scope, max_body_bytes: int) -> bool:
    for name, raw_value in scope.get("headers", []):
        if name.lower() != b"content-length":
            continue
        try:
            declared = int(raw_value.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            continue
        if declared > max_body_bytes:
            return True
    return False


async def _send_too_large(send: Send) -> None:
    body = (
        b'{"detail":{"code":"request_body_too_large",'
        b'"message":"The request body exceeded the allowed size."}}'
    )
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


__all__ = ["RequestBodyLimitMiddleware"]
