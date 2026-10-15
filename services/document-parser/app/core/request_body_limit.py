from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


# Document jobs carry metadata and configuration, never the document bytes.
# Bounding request bodies also bounds the caller-controlled BSON payloads that
# the job repository stores with PyMongo.
MAX_REQUEST_BODY_BYTES = 8 * 1024 * 1024


class RequestBodyLimitMiddleware:
    def __init__(
        self, app: Callable[..., Awaitable[None]], max_bytes: int = MAX_REQUEST_BODY_BYTES
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[..., Awaitable[dict[str, Any]]],
        send: Callable[..., Awaitable[None]],
    ) -> None:
        if scope["type"] != "http" or scope.get("method", "POST").upper() not in {
            "POST",
            "PUT",
            "PATCH",
        }:
            await self.app(scope, receive, send)
            return

        for name, value in scope.get("headers", []):
            if name.lower() != b"content-length":
                continue
            try:
                declared_size = int(value)
            except ValueError:
                break
            if declared_size > self.max_bytes:
                await self._reject(send)
                return
            break

        # Inspect the bounded body before the framework parses it. Exceptions
        # raised from receive() may be converted into a generic 400 by FastAPI.
        buffered: list[dict[str, Any]] = []
        received_bytes = 0
        while True:
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_bytes:
                    await self._reject(send)
                    return
            buffered.append(message)
            if message["type"] != "http.request" or not message.get("more_body", False):
                break

        pending = iter(buffered)

        async def replay_receive() -> dict[str, Any]:
            try:
                return next(pending)
            except StopIteration:
                return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(send: Callable[..., Awaitable[None]]) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"text/plain; charset=utf-8")],
            }
        )
        await send({"type": "http.response.body", "body": b"Request body too large"})
