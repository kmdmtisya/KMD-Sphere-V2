"""RFC 7807 problem+json error model."""

import logging
from http import HTTPStatus
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.correlation import HEADER_NAME, new_correlation_id

logger = logging.getLogger(__name__)
PROBLEM_BASE = "https://wealthsphere.app/problems"
MEDIA_TYPE = "application/problem+json"


def _cid(request: Request) -> str:
    return str(request.scope.get("state", {}).get("correlation_id") or new_correlation_id())


def problem(
    request: Request,
    status: int,
    slug: str,
    title: str,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    cid = _cid(request)
    body: dict[str, object] = {
        "type": f"{PROBLEM_BASE}/{slug}",
        "title": title,
        "status": status,
        "correlation_id": cid,
    }
    if detail:
        body["detail"] = detail
    if errors:
        body["errors"] = errors
    out_headers = {HEADER_NAME: cid, **(headers or {})}
    return JSONResponse(body, status_code=status, media_type=MEDIA_TYPE, headers=out_headers)


async def _http_exception(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(StarletteHTTPException, exc)
    title = HTTPStatus(exc.status_code).phrase
    slug = title.lower().replace(" ", "-")
    return problem(
        request, exc.status_code, slug, title, str(exc.detail), headers=dict(exc.headers or {})
    )


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    exc = cast(RequestValidationError, exc)
    # Report location and message only: never echo submitted values (they may be sensitive).
    errors = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": str(e["msg"])}
        for e in exc.errors()
    ]
    return problem(request, 422, "validation", "Validation failed", errors=errors)


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    cid = _cid(request)
    logger.error(
        "unhandled exception", exc_info=exc, extra={"correlation_id": cid, "path": request.url.path}
    )
    return problem(
        request, 500, "internal", "Internal Server Error", "An unexpected error occurred."
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(Exception, _unhandled)
