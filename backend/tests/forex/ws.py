"""A minimal in-process WebSocket client for ASGI apps. It runs the app on the test's own event
loop (unlike Starlette's TestClient, which uses a thread and another loop), so WebSocket tests can
share the app's database engine."""

import asyncio
import contextlib
import json
from types import TracebackType
from typing import Any

from fastapi import FastAPI


class Closed(Exception):
    def __init__(self, code: int, reason: str) -> None:
        super().__init__(f"{code} {reason}")
        self.code = code
        self.reason = reason


class AsgiWebSocket:
    def __init__(self, app: FastAPI, path: str = "/api/v1/forex/stream") -> None:
        self._app = app
        self._path = path
        self._to_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._from_app: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "AsgiWebSocket":
        scope = {
            "type": "websocket",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "scheme": "ws",
            "http_version": "1.1",
            "path": self._path,
            "raw_path": self._path.encode(),
            "root_path": "",
            "query_string": b"",
            "headers": [(b"host", b"test")],
            "client": ("127.0.0.1", 50000),
            "server": ("test", 80),
            "subprotocols": [],
        }
        self._task = asyncio.create_task(
            self._app(scope, self._to_app.get, self._from_app.put)  # type: ignore[arg-type]
        )
        await self._to_app.put({"type": "websocket.connect"})
        accepted = await self._next(5)
        assert accepted["type"] == "websocket.accept", accepted
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._to_app.put({"type": "websocket.disconnect", "code": 1000})
        if self._task is not None:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(self._task, 5)

    async def _next(self, seconds: float) -> dict[str, Any]:
        return await asyncio.wait_for(self._from_app.get(), seconds)

    async def send(self, message: dict[str, Any] | str) -> None:
        text = message if isinstance(message, str) else json.dumps(message)
        await self._to_app.put({"type": "websocket.receive", "text": text})

    async def receive(self, seconds: float = 5) -> dict[str, Any]:
        """The next frame; raises `Closed` when the server closed the socket."""
        message = await self._next(seconds)
        if message["type"] == "websocket.close":
            raise Closed(message.get("code", 1000), message.get("reason", ""))
        assert message["type"] == "websocket.send", message
        frame: dict[str, Any] = json.loads(message["text"])
        return frame

    async def receive_type(self, kind: str, seconds: float = 5) -> dict[str, Any]:
        """The next frame of type `kind`, skipping heartbeats and status frames."""
        while True:
            frame = await self.receive(seconds)
            if frame["type"] == kind:
                return frame
            assert frame["type"] in ("heartbeat", "status"), frame

    async def closed_with(self, seconds: float = 5) -> int:
        while True:
            try:
                await self.receive(seconds)
            except Closed as closed:
                return closed.code
