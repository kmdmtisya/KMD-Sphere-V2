"""RFC 7807 problem+json error model."""

import logging
from http import HTTPStatus
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import Scope

from app.core.auth import AuthenticationError
from app.core.authz import PermissionDeniedError, ResourceNotFoundError
from app.core.correlation import HEADER_NAME, new_correlation_id

logger = logging.getLogger(__name__)


class InvalidValueError(ValueError):
    """A well-formed request whose values break a business rule (answered with 422)."""


class ConflictError(Exception):
    """The request conflicts with the resource's current state (answered with 409)."""


PROBLEM_BASE = "https://wealthsphere.app/problems"
MEDIA_TYPE = "application/problem+json"


def _scope_cid(scope: Scope) -> str:
    return str(scope.get("state", {}).get("correlation_id") or new_correlation_id())


def _cid(request: Request) -> str:
    return _scope_cid(request.scope)


def problem(
    request: Request,
    status: int,
    slug: str,
    title: str,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return problem_response(request.scope, status, slug, title, detail, errors, headers)


def problem_response(
    scope: Scope,
    status: int,
    slug: str,
    title: str,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """A problem+json response; also usable as an ASGI app by middleware."""
    cid = _scope_cid(scope)
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


async def _authentication(request: Request, exc: Exception) -> JSONResponse:
    # One answer for every failure: callers learn nothing about why a token was rejected.
    logger.info(
        "authentication failed",
        extra={"reason": str(exc), "path": request.url.path, "correlation_id": _cid(request)},
    )
    return problem(
        request,
        401,
        "unauthenticated",
        "Unauthorized",
        "A valid access token is required.",
        headers={"WWW-Authenticate": 'Bearer realm="wealthsphere", error="invalid_token"'},
    )


async def _not_found(request: Request, exc: Exception) -> JSONResponse:
    # Identical for "does not exist" and "belongs to someone else" (ADR-0011).
    return problem(request, 404, "not-found", "Not Found", "The requested resource was not found.")


async def _forbidden(request: Request, exc: Exception) -> JSONResponse:
    return problem(
        request, 403, "forbidden", "Forbidden", "You do not have permission for this action."
    )


async def _invalid_value(request: Request, exc: Exception) -> JSONResponse:
    return problem(request, 422, "validation", "Validation failed", str(exc))


async def _conflict(request: Request, exc: Exception) -> JSONResponse:
    return problem(request, 409, "conflict", "Conflict", str(exc))


async def _fx_unavailable(request: Request, exc: Exception) -> JSONResponse:
    return problem(request, 404, "fx-rate-unavailable", "FX rate unavailable", str(exc))


async def _rate_limited(request: Request, exc: Exception) -> JSONResponse:
    from app.core.ratelimit import RateLimitedError, too_many_requests

    return too_many_requests(request.scope, cast(RateLimitedError, exc).retry_after)


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    cid = _cid(request)
    logger.error(
        "unhandled exception", exc_info=exc, extra={"correlation_id": cid, "path": request.url.path}
    )
    return problem(
        request, 500, "internal", "Internal Server Error", "An unexpected error occurred."
    )


def register_exception_handlers(app: FastAPI) -> None:
    from app.core.ratelimit import RateLimitedError
    from app.modules.identity.service import InvalidProfileChangeError
    from app.modules.market_data.fx import FxRateUnavailable

    app.add_exception_handler(StarletteHTTPException, _http_exception)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(AuthenticationError, _authentication)
    app.add_exception_handler(InvalidProfileChangeError, _invalid_value)
    app.add_exception_handler(InvalidValueError, _invalid_value)
    app.add_exception_handler(ConflictError, _conflict)
    app.add_exception_handler(FxRateUnavailable, _fx_unavailable)
    app.add_exception_handler(ResourceNotFoundError, _not_found)
    app.add_exception_handler(PermissionDeniedError, _forbidden)
    app.add_exception_handler(RateLimitedError, _rate_limited)
    app.add_exception_handler(Exception, _unhandled)
