"""Cross-user (IDOR) test harness, reused by every module that stores user data (ADR-0011).

How to use it in a module's tests:

    from tests.authz_harness import TwoUsers, assert_hidden_from, two_users  # noqa: F401

    async def test_bob_cannot_read_alices_portfolio(http, two_users: TwoUsers) -> None:
        created = await http.post("/api/v1/portfolios", headers=two_users.alice.headers, json=...)
        await assert_hidden_from(
            http, two_users.bob, "GET", f"/api/v1/portfolios/{created.json()['id']}"
        )

Then add the route to `IDOR_TESTS` in tests/idor_registry.py, naming the test that covers it.
`tests/test_idor_coverage.py` fails if any route with an id in its path is missing from there.
"""

import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from tests import auth_helpers as ah


@dataclass(frozen=True)
class TestUser:
    __test__ = False  # not a pytest test class

    name: str
    subject: str
    token: str
    headers: dict[str, str]
    id: str


@dataclass(frozen=True)
class TwoUsers:
    __test__ = False

    alice: TestUser
    bob: TestUser


async def make_user(http: httpx.AsyncClient, name: str) -> TestUser:
    subject = f"{name}-{uuid.uuid4()}"
    token = ah.token(subject, email=f"{name}@example.test")
    headers = ah.bearer(token)
    me = await http.get("/api/v1/me", headers=headers)
    assert me.status_code == 200, me.text
    return TestUser(name, subject, token, headers, me.json()["id"])


@pytest.fixture
async def two_users(http: httpx.AsyncClient) -> TwoUsers:
    """Two independent, provisioned users. Requires an `http` fixture (an ASGI client)."""
    return TwoUsers(await make_user(http, "alice"), await make_user(http, "bob"))


def _strip(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if k != "correlation_id"}


async def assert_hidden_from(
    http: httpx.AsyncClient,
    other: TestUser,
    method: str,
    path: str,
    json: dict[str, Any] | None = None,
) -> None:
    """`other` gets a 404 for someone else's resource, indistinguishable from a resource that does
    not exist (same status and body), so ids cannot be probed."""
    response = await http.request(method, path, headers=other.headers, json=json)
    assert response.status_code == 404, f"{method} {path} as {other.name}: {response.text}"

    # The same request for an id that certainly does not exist must look identical.
    segments = path.rstrip("/").split("/")
    for i in range(len(segments) - 1, -1, -1):
        try:
            uuid.UUID(segments[i])
        except ValueError:
            continue
        segments[i] = str(uuid.uuid4())
        break
    else:
        raise AssertionError(f"{path} has no id to substitute")
    missing = await http.request(method, "/".join(segments), headers=other.headers, json=json)
    assert missing.status_code == 404
    assert _strip(response.json()) == _strip(missing.json()), "a hidden resource must look missing"
