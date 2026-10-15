"""/api/v1/operator (P14-T17, DEC-34): role-gated, read-only, aggregate, audited."""

import uuid
from collections.abc import AsyncIterator

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from tests import auth_helpers as ah
from tests.authz_harness import TestUser, make_user
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
PATHS = ("/api/v1/operator/status", "/api/v1/operator/audit")


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


@pytest.fixture(scope="module")
async def db(migrated_settings: Settings) -> AsyncIterator[asyncpg.Connection]:  # noqa: F811
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    yield conn
    await conn.close()


async def support_user(http: httpx.AsyncClient) -> TestUser:
    subject = f"support-{uuid.uuid4()}"
    token = ah.token(
        subject,
        email=f"{subject}@example.test",
        realm_access={"roles": ["user", "support"]},
    )
    headers = ah.bearer(token)
    me = await http.get("/api/v1/me", headers=headers)
    assert me.status_code == 200, me.text
    return TestUser("support", subject, token, headers, me.json()["id"])


async def test_without_a_token_it_is_unauthorised(http: httpx.AsyncClient) -> None:
    for path in PATHS:
        assert (await http.get(path)).status_code == 401


async def test_a_user_without_the_role_is_refused_and_the_attempt_is_audited(
    http: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    user = await make_user(http, "curious")
    for path in PATHS:
        r = await http.get(path, headers=user.headers)
        assert r.status_code == 403, (path, r.text)
        assert "audit" not in r.text.lower() or "support" in r.text.lower()
    rows = await db.fetch(
        "SELECT outcome FROM audit_events WHERE action = 'operator.access.denied' "
        "AND actor_user_id = $1",
        uuid.UUID(user.id),
    )
    assert len(rows) == 2 and {r["outcome"] for r in rows} == {"denied"}


async def test_the_role_comes_from_the_verified_token_not_the_request(
    http: httpx.AsyncClient,
) -> None:
    user = await make_user(http, "claims-a-role")
    forged = {**user.headers, "X-Roles": "support", "X-User-Role": "support"}
    assert (await http.get("/api/v1/operator/status", headers=forged)).status_code == 403
    assert (
        await http.get("/api/v1/operator/status?role=support", headers=user.headers)
    ).status_code == 403


async def test_status_is_aggregate_and_names_no_account(
    http: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    other = await make_user(http, "private-person")
    ops = await support_user(http)
    r = await http.get("/api/v1/operator/status", headers=ops.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["users"]["active"] >= 2 and set(body["users"]) >= {"active", "disabled"}
    assert body["environment"] and body["features"]["forex"] in ("on", "off")
    assert body["window_hours"] == 24 and body["notice"]
    text = r.text
    for secret in (other.id, other.subject, f"{other.name}@example.test", other.token):
        assert secret not in text
    assert "@" not in text  # no email address anywhere
    audited = await db.fetchval(
        "SELECT count(*) FROM audit_events WHERE action = 'operator.status.viewed' "
        "AND actor_user_id = $1",
        uuid.UUID(ops.id),
    )
    assert audited == 1


async def test_the_audit_view_shows_what_happened_without_who_or_which_record(
    http: httpx.AsyncClient, db: asyncpg.Connection
) -> None:
    victim = await make_user(http, "audited-person")
    pid = (
        await http.post(
            "/api/v1/portfolios",
            headers=victim.headers,
            json={"name": "Secret holdings", "base_currency": "USD"},
        )
    ).json()["id"]
    ops = await support_user(http)
    r = await http.get("/api/v1/operator/audit?limit=200", headers=ops.headers)
    assert r.status_code == 200, r.text
    items = r.json()
    assert items and len(items) <= 200
    assert set(items[0]) == {
        "occurred_at",
        "action",
        "outcome",
        "actor_type",
        "resource_type",
        "channel",
        "correlation_id",
    }
    for secret in (victim.id, victim.subject, pid, "Secret holdings"):
        assert secret not in r.text
    assert any(i["action"].startswith("portfolio.") for i in items)

    denied = await http.get("/api/v1/operator/audit?outcome=denied", headers=ops.headers)
    assert all(i["outcome"] == "denied" for i in denied.json())
    prefixed = await http.get("/api/v1/operator/audit?action_prefix=operator.", headers=ops.headers)
    assert prefixed.json() and all(i["action"].startswith("operator.") for i in prefixed.json())
    assert (
        await db.fetchval(
            "SELECT count(*) FROM audit_events WHERE action = 'operator.audit.viewed' "
            "AND actor_user_id = $1",
            uuid.UUID(ops.id),
        )
        == 3
    )


async def test_inputs_are_validated(http: httpx.AsyncClient) -> None:
    ops = await support_user(http)
    for query in (
        "limit=0",
        "limit=201",
        "outcome=maybe",
        "action_prefix=%25",
        "action_prefix=A;DROP",
    ):
        r = await http.get(f"/api/v1/operator/audit?{query}", headers=ops.headers)
        assert r.status_code == 422, (query, r.status_code)


async def test_the_views_are_read_only(http: httpx.AsyncClient) -> None:
    ops = await support_user(http)
    for path in PATHS:
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            r = await http.request(method, path, headers=ops.headers)
            assert r.status_code == 405, (method, path, r.status_code)
