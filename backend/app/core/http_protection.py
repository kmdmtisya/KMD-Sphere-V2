"""HTTP hardening: request body limits and security response headers (P04-T05)."""

from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import problem_response

# Swagger UI (local and staging only) loads its own scripts and styles; everything else is JSON.
_DOCS_PATHS = ("/docs", "/openapi.json")
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
HSTS = "max-age=31536000; includeSubDomains"


def _too_large(scope: Scope, limit: int) -> JSONResponse:
    return problem_response(
        scope,
        413,
        "payload-too-large",
        "Content Too Large",
        f"Request bodies are limited to {limit} bytes.",
    )


class BodySizeLimitMiddleware:
    """Rejects request bodies over `max_bytes` with 413: by Content-Length before the app runs,
    and while streaming for bodies sent without one (chunked)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = MutableHeaders(scope=scope).get("content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > self.max_bytes):
            await _too_large(scope, self.max_bytes)(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # FastAPI re-raises HTTPException from body reading; the handler renders 413.
                    raise HTTPException(
                        413, f"Request bodies are limited to {self.max_bytes} bytes."
                    )
            return message

        await self.app(scope, limited_receive, send)


class SecurityHeadersMiddleware:
    """Adds security headers to every HTTP response (unless a route already set them)."""

    def __init__(self, app: ASGIApp, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = scope.get("path", "").startswith(_DOCS_PATHS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                defaults = {
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                    "Referrer-Policy": "no-referrer",
                    "Cross-Origin-Resource-Policy": "same-origin",
                    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                    # Financial data must not be stored by browsers or shared caches.
                    "Cache-Control": "no-store",
                }
                if not is_docs:
                    defaults["Content-Security-Policy"] = API_CSP
                if self.hsts:
                    defaults["Strict-Transport-Security"] = HSTS
                for name, value in defaults.items():
                    if name not in headers:
                        headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_headers)
