"""Optimistic concurrency for editable records (P14-T18.1).

A record's ETag is derived from its `updated_at`. A client that sends it back as `If-Match` on an
update is saying "change this version"; if the record has changed since (on another device or
channel), the update is refused with 409 rather than silently overwriting the newer edit. A client
that sends no `If-Match` keeps the previous behaviour (last write wins), so existing clients are not
broken. The check is repeated inside the UPDATE statement (`WHERE updated_at = ...`), so two edits
racing in the same instant cannot both succeed.
"""

import hashlib
from datetime import datetime

from app.core.errors import ConflictError

STALE = "This record was changed somewhere else. Reload it and try your change again."


def etag_of(updated_at: datetime) -> str:
    """The ETag header value (strong, quoted) for a record last changed at `updated_at`."""
    return '"' + hashlib.sha256(updated_at.isoformat().encode()).hexdigest()[:24] + '"'


def matches(if_match: str | None, updated_at: datetime) -> bool:
    """True when no precondition was given, it is `*`, or it names the current version."""
    if if_match is None or if_match.strip() == "*":
        return True
    current = etag_of(updated_at)
    candidates = [part.strip().removeprefix("W/") for part in if_match.split(",")]
    return current in candidates


def check(if_match: str | None, updated_at: datetime) -> None:
    """Raises ConflictError (409) when the caller's version is not the current one."""
    if not matches(if_match, updated_at):
        raise ConflictError(STALE)


def expected_version(if_match: str | None, updated_at: datetime) -> datetime | None:
    """The version the UPDATE must still find, or None when the caller sent no precondition."""
    return None if if_match is None or if_match.strip() == "*" else updated_at
