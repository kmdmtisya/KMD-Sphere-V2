"""Portfolios (P05-T03): CRUD, archive, validation, conflicts, audit and cross-user isolation."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from app.modules.portfolio import service as portfolio_service
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, assert_hidden_from, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
BASE = "/api/v1/portfolios"


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


async def create(http: httpx.AsyncClient, headers: dict[str, str], **body: Any) -> dict[str, Any]:
    payload = {"name": f"Portfolio {uuid.uuid4().hex[:6]}", "base_currency": "USD", **body}
    r = await http.post(BASE, headers=headers, json=payload)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def events(db: asyncpg.Connection, resource_id: str) -> list[str]:
    rows = await db.fetch(
        "SELECT action FROM audit_events WHERE resource_id = $1 ORDER BY occurred_at, action",
        resource_id,
    )
    return [r["action"] for r in rows]


# ---------------------------------------------------------------------------- owner can


async def test_create_read_list_update_and_archive(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    created = await create(
        http, h, name="  Retirement  ", base_currency="KES", description=" Long term "
    )
    assert created["name"] == "Retirement"
    assert created["description"] == "Long term"
    assert created["portfolio_type"] == "personal"
    assert created["archived_at"] is None
    pid = created["id"]

    got = await http.get(f"{BASE}/{pid}", headers=h)
    assert got.json() == created

    changed = await http.patch(
        f"{BASE}/{pid}", headers=h, json={"name": "Pension", "portfolio_type": "retirement"}
    )
    assert changed.status_code == 200
    assert changed.json()["name"] == "Pension"
    assert changed.json()["portfolio_type"] == "retirement"
    assert changed.json()["base_currency"] == "KES"
    assert changed.json()["updated_at"] >= created["updated_at"]

    cleared = await http.patch(f"{BASE}/{pid}", headers=h, json={"description": None})
    assert cleared.json()["description"] is None

    archived = await http.post(f"{BASE}/{pid}/archive", headers=h)
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    again = await http.post(f"{BASE}/{pid}/archive", headers=h)
    assert again.json()["archived_at"] == archived.json()["archived_at"]  # idempotent

    active = [p["id"] for p in (await http.get(BASE, headers=h)).json()]
    everything = [
        p["id"] for p in (await http.get(BASE, headers=h, params={"include_archived": True})).json()
    ]
    assert pid not in active
    assert pid in everything
    assert await events(db, pid) == [
        "portfolio.portfolio.created",
        "portfolio.portfolio.updated",
        "portfolio.portfolio.updated",
        "portfolio.portfolio.archived",
    ]


async def test_list_is_oldest_first(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    ids = [(await create(http, h))["id"] for _ in range(3)]
    listed = [p["id"] for p in (await http.get(BASE, headers=h)).json()]
    assert [i for i in listed if i in ids] == ids


async def test_an_archived_portfolio_cannot_change(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = (await create(http, h))["id"]
    await http.post(f"{BASE}/{pid}/archive", headers=h)
    r = await http.patch(f"{BASE}/{pid}", headers=h, json={"name": "Renamed"})
    assert r.status_code == 409
    assert r.json()["type"].endswith("/conflict")


async def test_an_empty_patch_changes_nothing_and_writes_no_event(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    created = await create(http, h)
    r = await http.patch(f"{BASE}/{created['id']}", headers=h, json={})
    assert r.status_code == 200
    assert r.json() == created
    assert await events(db, created["id"]) == ["portfolio.portfolio.created"]


# ----------------------------------------------------------------------------- conflicts


async def test_names_are_unique_per_user(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    name = f"Growth {uuid.uuid4().hex[:6]}"
    first = await create(http, two_users.alice.headers, name=name)
    dup = await http.post(
        BASE, headers=two_users.alice.headers, json={"name": name, "base_currency": "USD"}
    )
    assert dup.status_code == 409
    other = await create(http, two_users.alice.headers)
    rename = await http.patch(
        f"{BASE}/{other['id']}", headers=two_users.alice.headers, json={"name": name}
    )
    assert rename.status_code == 409
    # Another user may use the same name.
    await create(http, two_users.bob.headers, name=name)
    assert first["name"] == name


async def test_the_portfolio_limit(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    h = two_users.bob.headers
    existing = len((await http.get(BASE, headers=h, params={"include_archived": True})).json())
    monkeypatch.setattr(portfolio_service, "MAX_PORTFOLIOS_PER_USER", existing + 1)
    await create(http, h)
    r = await http.post(BASE, headers=h, json={"name": "One too many", "base_currency": "USD"})
    assert r.status_code == 409


# ---------------------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "body",
    [
        {"name": "x", "base_currency": "usd"},
        {"name": "x", "base_currency": "US"},
        {"name": "   ", "base_currency": "USD"},
        {"name": "x" * 101, "base_currency": "USD"},
        {"name": "x", "base_currency": "USD", "portfolio_type": "hedge_fund"},
        {"name": "x", "base_currency": "USD", "user_id": str(uuid.uuid4())},
        {"name": "x", "base_currency": "USD", "description": "d" * 501},
        {"base_currency": "USD"},
        {"name": "x"},
    ],
)
async def test_invalid_portfolios_are_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    body: dict[str, Any],
) -> None:
    r = await http.post(BASE, headers=two_users.alice.headers, json=body)
    assert r.status_code == 422, (body, r.text)


@pytest.mark.parametrize(
    "change",
    [
        {"base_currency": "EUR"},
        {"name": None},
        {"portfolio_type": None},
        {"name": " "},
        {"archived_at": None},
        {"user_id": str(uuid.uuid4())},
    ],
)
async def test_invalid_changes_are_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    change: dict[str, Any],
) -> None:
    pid = (await create(http, two_users.alice.headers))["id"]
    r = await http.patch(f"{BASE}/{pid}", headers=two_users.alice.headers, json=change)
    assert r.status_code == 422, (change, r.text)


# ------------------------------------------------------------------------- others cannot


async def test_bob_cannot_read_alices_portfolio(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = (await create(http, two_users.alice.headers))["id"]
    await assert_hidden_from(http, two_users.bob, "GET", f"{BASE}/{pid}")
    bob_list = await http.get(BASE, headers=two_users.bob.headers, params={"include_archived": 1})
    assert pid not in {p["id"] for p in bob_list.json()}


async def test_bob_cannot_change_alices_portfolio(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    created = await create(http, two_users.alice.headers)
    pid = created["id"]
    await assert_hidden_from(http, two_users.bob, "PATCH", f"{BASE}/{pid}", json={"name": "Mine"})
    row = await db.fetchrow("SELECT name FROM portfolios WHERE id = $1", uuid.UUID(pid))
    assert row is not None and row["name"] == created["name"]
    assert await events(db, pid) == ["portfolio.portfolio.created"]


async def test_bob_cannot_archive_alices_portfolio(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    pid = (await create(http, two_users.alice.headers))["id"]
    await assert_hidden_from(http, two_users.bob, "POST", f"{BASE}/{pid}/archive")
    assert (
        await db.fetchval("SELECT archived_at FROM portfolios WHERE id = $1", uuid.UUID(pid))
        is None
    )


# ----------------------------------------------------------- repository (second line of defence)


async def test_the_repository_update_never_touches_another_users_or_an_archived_portfolio(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    app: FastAPI,
) -> None:
    from app.modules.portfolio.repository import PortfolioRepository

    pid = uuid.UUID((await create(http, two_users.alice.headers))["id"])
    archived = uuid.UUID((await create(http, two_users.alice.headers))["id"])
    await http.post(f"{BASE}/{archived}/archive", headers=two_users.alice.headers)
    alice, bob = uuid.UUID(two_users.alice.id), uuid.UUID(two_users.bob.id)
    async with app.state.db.session_factory() as session:
        repo = PortfolioRepository(session)
        assert await repo.update(bob, pid, {"name": "Stolen"}) is False
        assert await repo.get(bob, pid) is None
        assert await repo.update(alice, archived, {"name": "Changed"}) is False
        assert await repo.update(alice, pid, {"name": f"Fine {uuid.uuid4().hex[:4]}"}) is True
        await session.rollback()
