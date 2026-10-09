"""Correlation IDs: accepted from X-Correlation-ID when well-formed, otherwise generated."""

import re
import uuid
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HEADER_NAME = "X-Correlation-ID"
_VALID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def get_correlation_id() -> str | None:
    return correlation_id_var.get()


class CorrelationIdMiddleware:
    """Pure ASGI middleware so the ID is also available to exception handlers via scope state."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = MutableHeaders(scope=scope).get(HEADER_NAME)
        cid = incoming if incoming and _VALID.match(incoming) else new_correlation_id()
        scope.setdefault("state", {})["correlation_id"] = cid
        token = correlation_id_var.set(cid)

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[HEADER_NAME] = cid
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            correlation_id_var.reset(token)
