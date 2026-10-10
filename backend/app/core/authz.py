"""Authorization helpers. Every module that stores user data uses these, so ownership is enforced
the same way everywhere (ADR-0011).

Rules:
1. **Scope the query, don't filter the result.** Repositories load user-owned rows with
   `owned_by(...)`, so another user's row is never read into memory at all.
2. **Not yours == does not exist.** A resource that belongs to someone else answers 404, exactly
   like one that does not exist, so ids cannot be probed (`ResourceNotFoundError`).
3. **403 only for a visible resource and a missing permission** (for example, a read-only member of
   a shared portfolio trying to edit it: `PermissionDeniedError`).
"""

import uuid
from typing import Any, Protocol

from sqlalchemy import Select, select


class ResourceNotFoundError(Exception):
    """The resource does not exist *or* is not the caller's. Always HTTP 404."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class PermissionDeniedError(Exception):
    """The caller can see the resource but may not perform this action. HTTP 403."""


class Owned(Protocol):
    id: Any
    user_id: Any


def owned_by[T: Owned](model: type[T], user_id: uuid.UUID) -> Select[T]:
    """`SELECT model WHERE model.user_id = :user_id`: how every query for user data starts."""
    return select(model).where(model.user_id == user_id)


def require_found[T](resource: T | None, kind: str) -> T:
    """Turns a missing (or not-owned, already filtered out) resource into a 404."""
    if resource is None:
        raise ResourceNotFoundError(kind)
    return resource


def require_role(roles: frozenset[str], role: str) -> None:
    if role not in roles:
        raise PermissionDeniedError(role)
