"""OpenAPI response declarations shared by every protected router."""

from typing import Any

UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    401: {"description": "Missing, invalid or expired access token"},
    429: {
        "description": "Rate limit exceeded (docs/security.md, API protection)",
        "headers": {
            "Retry-After": {
                "description": "Seconds to wait before retrying",
                "schema": {"type": "integer", "minimum": 1},
            }
        },
    },
}


def not_found(what: str) -> dict[int | str, dict[str, Any]]:
    """404 for a resource that does not exist or is not the caller's (ADR-0011)."""
    return {404: {"description": f"No such {what} for this user"}}


def invalid(what: str) -> dict[int | str, dict[str, Any]]:
    return {422: {"description": f"Invalid {what}"}}


def conflict(what: str) -> dict[int | str, dict[str, Any]]:
    return {409: {"description": what}}
