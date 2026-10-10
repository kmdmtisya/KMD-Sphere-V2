"""Risk profiles: the first user-owned resource, proving the authorization framework end to end."""

import uuid
from collections.abc import AsyncIterator

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, assert_hidden_from, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
BASE = "/api/v1/risk-profiles"


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    application = create_app(migrated_settings, readiness_checks={}, token_verifier=ah.verifier())
    yield application
    await application.state.db.dispose()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _create(http: httpx.AsyncClient, headers: dict[str, str], tolerance: str) -> str:
    r = await http.post(
        BASE, headers=headers, json={"risk_tolerance": tolerance, "horizon_years": 10}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


# ---------------------------------------------------------------------------- owner can


async def test_owner_creates_lists_reads_and_updates(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    alice = two_users.alice
    pid = await _create(http, alice.headers, "balanced")
    listed = await http.get(BASE, headers=alice.headers)
    assert [p["id"] for p in listed.json()] == [pid]
    got = await http.get(f"{BASE}/{pid}", headers=alice.headers)
    assert got.json()["risk_tolerance"] == "balanced"
    assert got.json()["source"] == "self_assessment"
    changed = await http.patch(
        f"{BASE}/{pid}", headers=alice.headers, json={"risk_tolerance": "growth"}
    )
    assert changed.status_code == 200
    assert changed.json()["risk_tolerance"] == "growth"
    assert changed.json()["horizon_years"] == 10


# ------------------------------------------------------------------------- others cannot


async def test_bob_cannot_read_alices_risk_profile(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await _create(http, two_users.alice.headers, "conservative")
    await assert_hidden_from(http, two_users.bob, "GET", f"{BASE}/{pid}")


async def test_bob_cannot_change_alices_risk_profile(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    migrated_settings: Settings,  # noqa: F811
) -> None:
    pid = await _create(http, two_users.alice.headers, "conservative")
    await assert_hidden_from(
        http, two_users.bob, "PATCH", f"{BASE}/{pid}", json={"risk_tolerance": "aggressive"}
    )
    # Alice's data is untouched, checked directly in the database.
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    try:
        tolerance = await conn.fetchval(
            "SELECT risk_tolerance FROM risk_profiles WHERE id = $1", uuid.UUID(pid)
        )
    finally:
        await conn.close()
    assert tolerance == "conservative"


async def test_bobs_list_never_contains_alices_profiles(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    alice_ids = {await _create(http, two_users.alice.headers, "growth") for _ in range(3)}
    bob_id = await _create(http, two_users.bob.headers, "balanced")
    bob_list = {p["id"] for p in (await http.get(BASE, headers=two_users.bob.headers)).json()}
    assert bob_list == {bob_id}
    assert not alice_ids & bob_list


async def test_unauthenticated_requests_are_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await _create(http, two_users.alice.headers, "growth")
    for method, path in [("GET", BASE), ("GET", f"{BASE}/{pid}"), ("PATCH", f"{BASE}/{pid}")]:
        r = await http.request(method, path, json={"risk_tolerance": "growth"})
        assert r.status_code == 401, (method, path)


# ------------------------------------------------------------------------------ validation


@pytest.mark.parametrize(
    "body",
    [
        {"risk_tolerance": "yolo"},
        {"risk_tolerance": "growth", "horizon_years": -1},
        {"risk_tolerance": "growth", "horizon_years": 101},
        {"risk_tolerance": "growth", "user_id": str(uuid.uuid4())},
        {},
    ],
)
async def test_invalid_create_bodies_are_rejected(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    body: dict[str, object],
) -> None:
    r = await http.post(BASE, headers=two_users.alice.headers, json=body)
    assert r.status_code == 422, body


async def test_a_client_cannot_assign_ownership(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    """There is no way to name an owner: user_id is rejected as an unknown field (above), and the
    owner is always the authenticated user."""
    pid = await _create(http, two_users.bob.headers, "balanced")
    assert (await http.get(f"{BASE}/{pid}", headers=two_users.bob.headers)).status_code == 200
    assert (await http.get(f"{BASE}/{pid}", headers=two_users.alice.headers)).status_code == 404


async def test_malformed_ids_are_rejected(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    r = await http.get(f"{BASE}/not-a-uuid", headers=two_users.alice.headers)
    assert r.status_code == 422


async def test_risk_tolerance_cannot_be_cleared(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await _create(http, two_users.alice.headers, "growth")
    r = await http.patch(
        f"{BASE}/{pid}", headers=two_users.alice.headers, json={"risk_tolerance": None}
    )
    assert r.status_code == 422
