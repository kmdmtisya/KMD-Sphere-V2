"""/api/v1/me against a real, migrated PostgreSQL: provisioning, profile and preferences."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from tests import auth_helpers as ah
from tests.db_fixtures import migrated_settings  # noqa: F401 (fixture)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]


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


async def count(settings: Settings, sql: str, *args: Any) -> int:
    conn = await asyncpg.connect(settings.database_dsn, timeout=5)
    try:
        return int(await conn.fetchval(sql, *args))
    finally:
        await conn.close()


async def test_first_call_provisions_the_user_and_profile(
    http: httpx.AsyncClient,
    migrated_settings: Settings,  # noqa: F811
) -> None:
    sub = f"sub-{uuid.uuid4()}"
    r = await http.get("/api/v1/me", headers=ah.bearer(ah.token(sub, email="new@example.test")))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "new@example.test"
    assert body["email_verified"] is True
    assert body["base_currency"] == "USD"
    assert body["locale"] == "en"
    assert body["timezone"] == "UTC"
    assert body["preferences"] == {"theme_mode": None, "dashboard_layout": None}
    uuid.UUID(body["id"])
    assert await count(migrated_settings, "SELECT count(*) FROM users WHERE subject=$1", sub) == 1
    assert (
        await count(
            migrated_settings,
            "SELECT count(*) FROM user_profiles p JOIN users u ON u.id = p.user_id"
            " WHERE u.subject = $1",
            sub,
        )
        == 1
    )


async def test_provisioning_is_idempotent(
    http: httpx.AsyncClient,
    migrated_settings: Settings,  # noqa: F811
) -> None:
    sub = f"sub-{uuid.uuid4()}"
    ids = set()
    for _ in range(3):
        r = await http.get("/api/v1/me", headers=ah.bearer(ah.token(sub)))
        ids.add(r.json()["id"])
    assert len(ids) == 1
    assert await count(migrated_settings, "SELECT count(*) FROM users WHERE subject=$1", sub) == 1


async def test_concurrent_first_requests_create_one_user(
    http: httpx.AsyncClient,
    migrated_settings: Settings,  # noqa: F811
) -> None:
    sub = f"sub-{uuid.uuid4()}"
    tok = ah.token(sub)
    responses = await asyncio.gather(
        *(http.get("/api/v1/me", headers=ah.bearer(tok)) for _ in range(8))
    )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert len({r.json()["id"] for r in responses}) == 1
    assert await count(migrated_settings, "SELECT count(*) FROM users WHERE subject=$1", sub) == 1


async def test_email_changes_from_the_identity_provider_are_picked_up(
    http: httpx.AsyncClient,
) -> None:
    sub = f"sub-{uuid.uuid4()}"
    await http.get("/api/v1/me", headers=ah.bearer(ah.token(sub, email="old@example.test")))
    r = await http.get(
        "/api/v1/me",
        headers=ah.bearer(ah.token(sub, email="new@example.test", email_verified=False)),
    )
    assert r.json()["email"] == "new@example.test"
    assert r.json()["email_verified"] is False


async def test_same_subject_from_another_issuer_is_a_different_user(
    http: httpx.AsyncClient,
) -> None:
    sub = f"sub-{uuid.uuid4()}"
    r1 = await http.get("/api/v1/me", headers=ah.bearer(ah.token(sub)))
    assert r1.status_code == 200
    # A token from another issuer is rejected outright (the verifier pins the issuer).
    r2 = await http.get(
        "/api/v1/me", headers=ah.bearer(ah.token(sub, iss="http://other.test/realms/x"))
    )
    assert r2.status_code == 401


async def test_two_users_see_only_their_own_profile(http: httpx.AsyncClient) -> None:
    alice, bob = ah.token(f"alice-{uuid.uuid4()}"), ah.token(f"bob-{uuid.uuid4()}")
    await http.patch(
        "/api/v1/me/preferences", headers=ah.bearer(alice), json={"display_name": "Alice"}
    )
    a = (await http.get("/api/v1/me", headers=ah.bearer(alice))).json()
    b = (await http.get("/api/v1/me", headers=ah.bearer(bob))).json()
    assert a["id"] != b["id"]
    assert a["display_name"] == "Alice"
    assert b["display_name"] is None


async def test_disabled_users_are_refused(
    http: httpx.AsyncClient,
    migrated_settings: Settings,  # noqa: F811
) -> None:
    sub = f"sub-{uuid.uuid4()}"
    await http.get("/api/v1/me", headers=ah.bearer(ah.token(sub)))
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    try:
        await conn.execute("UPDATE users SET status='disabled' WHERE subject=$1", sub)
    finally:
        await conn.close()
    r = await http.get("/api/v1/me", headers=ah.bearer(ah.token(sub)))
    assert r.status_code == 401


# ------------------------------------------------------------------------------ preferences


async def test_preferences_update_merges_and_persists(http: httpx.AsyncClient) -> None:
    tok = ah.token(f"sub-{uuid.uuid4()}")
    r = await http.patch(
        "/api/v1/me/preferences",
        headers=ah.bearer(tok),
        json={
            "theme_mode": "dark",
            "dashboard_layout": {"order": ["metrics", "wealthSummary"], "hidden": ["goals"]},
            "display_name": "Sam",
            "base_currency": "AED",
            "locale": "en_GB",
            "timezone": "Asia/Dubai",
        },
    )
    assert r.status_code == 200, r.text
    r = await http.patch(
        "/api/v1/me/preferences", headers=ah.bearer(tok), json={"theme_mode": "light"}
    )
    me = (await http.get("/api/v1/me", headers=ah.bearer(tok))).json()
    assert me["preferences"]["theme_mode"] == "light"
    assert me["preferences"]["dashboard_layout"] == {
        "order": ["metrics", "wealthSummary"],
        "hidden": ["goals"],
    }
    assert me["display_name"] == "Sam"
    assert me["base_currency"] == "AED"
    assert me["timezone"] == "Asia/Dubai"


async def test_null_clears_a_ui_preference(http: httpx.AsyncClient) -> None:
    tok = ah.token(f"sub-{uuid.uuid4()}")
    await http.patch("/api/v1/me/preferences", headers=ah.bearer(tok), json={"theme_mode": "dark"})
    r = await http.patch(
        "/api/v1/me/preferences", headers=ah.bearer(tok), json={"theme_mode": None}
    )
    assert r.json()["preferences"]["theme_mode"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"base_currency": "usd"},
        {"base_currency": "DOLLARS"},
        {"timezone": "Mars/Olympus"},
        {"theme_mode": "neon"},
        {"locale": "not a locale"},
        {"display_name": ""},
        {"dashboard_layout": {"order": ["metrics", "metrics"]}},
        {"dashboard_layout": {"order": ["unknown"]}},
        {"is_admin": True},
        {"base_currency": None},
    ],
)
async def test_invalid_preferences_are_rejected(
    http: httpx.AsyncClient, body: dict[str, Any]
) -> None:
    tok = ah.token(f"sub-{uuid.uuid4()}")
    r = await http.patch("/api/v1/me/preferences", headers=ah.bearer(tok), json=body)
    assert r.status_code == 422, (body, r.text)
    assert r.headers["content-type"].startswith("application/problem+json")
    # Submitted values are never echoed back.
    for value in body.values():
        if isinstance(value, str) and len(value) > 3:
            assert value not in r.text
