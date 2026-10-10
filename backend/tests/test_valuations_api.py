"""Manual valuations (P05-T07): selection, validation, corrections, audit and isolation."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

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
NOW = datetime.now(UTC).replace(microsecond=0)
T1, T2, T3 = NOW - timedelta(days=60), NOW - timedelta(days=30), NOW - timedelta(days=1)


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


async def setup(http: httpx.AsyncClient, h: dict[str, str]) -> tuple[str, str]:
    """A portfolio and a user-defined property."""
    p = await http.post(
        "/api/v1/portfolios",
        headers=h,
        json={"name": f"V {uuid.uuid4().hex[:8]}", "base_currency": "KES"},
    )
    a = await http.post(
        "/api/v1/assets",
        headers=h,
        json={"asset_class": "real_estate", "name": "Flat", "currency": "KES"},
    )
    return str(p.json()["id"]), str(a.json()["id"])


def url(pid: str, vid: str | None = None) -> str:
    base = f"/api/v1/portfolios/{pid}/valuations"
    return f"{base}/{vid}" if vid else base


def body(asset: str, amount: str, when: datetime, **extra: Any) -> dict[str, Any]:
    return {
        "asset_id": asset,
        "value": {"amount": amount, "currency": "KES"},
        "as_of": when.isoformat(),
        "source": "owner estimate",
        **extra,
    }


async def add(
    http: httpx.AsyncClient, h: dict[str, str], pid: str, b: dict[str, Any]
) -> dict[str, Any]:
    r = await http.post(url(pid), headers=h, json=b)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def actions(db: asyncpg.Connection, vid: str) -> list[str]:
    rows = await db.fetch(
        "SELECT action FROM audit_events WHERE resource_id = $1 ORDER BY occurred_at, action", vid
    )
    return [r["action"] for r in rows]


# ------------------------------------------------------------------------------ selection


async def test_latest_as_of_is_selected_deterministically(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid, flat = await setup(http, h)
    _, house = await setup(http, h)
    for when, amount in ((T2, "8200000.00"), (T1, "8000000.00"), (T3, "8500000.00")):
        await add(http, h, pid, body(flat, amount, when))
    await add(http, h, pid, body(house, "12000000.00", T1))

    latest = (await http.get(f"{url(pid)}/latest", headers=h)).json()
    by_asset = {v["asset_id"]: v for v in latest}
    assert by_asset[flat]["value"] == {"amount": "8500000.00", "currency": "KES"}
    assert by_asset[house]["value"]["amount"] == "12000000.00"

    at = (T2 + timedelta(hours=1)).isoformat()
    then = (await http.get(f"{url(pid)}/latest", headers=h, params={"at": at})).json()
    assert {v["asset_id"]: v["value"]["amount"] for v in then} == {
        flat: "8200000.00",
        house: "12000000.00",
    }
    before = (T1 - timedelta(days=1)).isoformat()
    assert (await http.get(f"{url(pid)}/latest", headers=h, params={"at": before})).json() == []


async def test_one_valuation_per_asset_per_moment(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid, flat = await setup(http, h)
    await add(http, h, pid, body(flat, "1.00", T1))
    dup = await http.post(url(pid), headers=h, json=body(flat, "2.00", T1))
    assert dup.status_code == 409


# ----------------------------------------------------------------------------- validation


@pytest.mark.parametrize(
    "change",
    [
        {"value": {"amount": "-1.00", "currency": "KES"}},
        {"value": {"amount": "1.001", "currency": "KES"}},
        {"value": {"amount": "1.5", "currency": "JPY"}},
        {"value": {"amount": 100, "currency": "KES"}},
        {"as_of": (NOW + timedelta(days=3)).isoformat()},
        {"as_of": "2026-01-01T00:00:00"},
        {"source": "   "},
        {"source": "s" * 65},
        {"asset_id": str(uuid.uuid4())},
        {"currency": "KES"},
    ],
)
async def test_invalid_valuations_are_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    change: dict[str, Any],
) -> None:
    h = two_users.alice.headers
    pid, flat = await setup(http, h)
    r = await http.post(url(pid), headers=h, json={**body(flat, "1.00", T1), **change})
    assert r.status_code == 422, (change, r.text)


async def test_another_users_asset_cannot_be_valued(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    _, bobs_flat = await setup(http, two_users.bob.headers)
    pid, _ = await setup(http, two_users.alice.headers)
    r = await http.post(url(pid), headers=two_users.alice.headers, json=body(bobs_flat, "1.00", T1))
    assert r.status_code == 422
    assert r.json()["detail"] == "asset_id: no such asset"


# ------------------------------------------------------------------- corrections and audit


async def test_corrections_and_deletions_are_audited(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    pid, flat = await setup(http, h)
    older = await add(http, h, pid, body(flat, "7000000.00", T1))
    v = await add(http, h, pid, body(flat, "8000000.00", T2, note="first guess"))
    fixed = await http.patch(
        url(pid, v["id"]),
        headers=h,
        json={"value": {"amount": "8100000.00", "currency": "KES"}, "source": " valuer report "},
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["value"]["amount"] == "8100000.00"
    assert fixed.json()["source"] == "valuer report"
    assert fixed.json()["as_of"] == v["as_of"]
    assert fixed.json()["note"] == "first guess"
    nothing = await http.patch(url(pid, v["id"]), headers=h, json={})
    assert nothing.status_code == 200
    gone = await http.delete(url(pid, v["id"]), headers=h)
    assert gone.status_code == 204
    assert (await http.get(url(pid, v["id"]), headers=h)).status_code == 404
    latest = (await http.get(f"{url(pid)}/latest", headers=h)).json()
    assert [x["id"] for x in latest] == [older["id"]]  # falls back to the previous value
    assert await actions(db, v["id"]) == [
        "transactions.valuation.created",
        "transactions.valuation.updated",
        "transactions.valuation.deleted",
    ]
    event = await db.fetchrow(
        "SELECT details FROM audit_events WHERE resource_id = $1 "
        "AND action = 'transactions.valuation.updated'",
        v["id"],
    )
    assert event is not None and "8100000" not in event["details"]  # amounts are not logged


@pytest.mark.parametrize(
    "change", [{"as_of": T3.isoformat()}, {"asset_id": str(uuid.uuid4())}, {"value": None}]
)
async def test_invalid_corrections_are_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    change: dict[str, Any],
) -> None:
    h = two_users.alice.headers
    pid, flat = await setup(http, h)
    v = await add(http, h, pid, body(flat, "1.00", T1))
    r = await http.patch(url(pid, v["id"]), headers=h, json=change)
    assert r.status_code == 422, (change, r.text)


async def test_an_archived_portfolio_keeps_its_valuations_read_only(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid, flat = await setup(http, h)
    v = await add(http, h, pid, body(flat, "1.00", T1))
    await http.post(f"/api/v1/portfolios/{pid}/archive", headers=h)
    assert (await http.post(url(pid), headers=h, json=body(flat, "2.00", T2))).status_code == 409
    patch = await http.patch(url(pid, v["id"]), headers=h, json={"source": "x"})
    assert patch.status_code == 409
    assert (await http.delete(url(pid, v["id"]), headers=h)).status_code == 409
    assert (await http.get(url(pid, v["id"]), headers=h)).status_code == 200


async def test_listing_is_newest_first_and_paginated(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid, flat = await setup(http, h)
    _, house = await setup(http, h)
    made = []
    for days in (5, 4, 3):
        made.append(await add(http, h, pid, body(flat, "1.00", NOW - timedelta(days=days))))
    await add(http, h, pid, body(house, "1.00", NOW - timedelta(days=10)))
    first = (await http.get(url(pid), headers=h, params={"limit": 2, "asset_id": flat})).json()
    second = (
        await http.get(
            url(pid),
            headers=h,
            params={"limit": 2, "asset_id": flat, "cursor": first["next_cursor"]},
        )
    ).json()
    assert [v["id"] for v in first["items"] + second["items"]] == [m["id"] for m in reversed(made)]
    assert second["next_cursor"] is None
    everything = (await http.get(url(pid), headers=h)).json()["items"]
    assert len(everything) == 4


# ------------------------------------------------------------------------- others cannot


async def _alices(http: httpx.AsyncClient, two: TwoUsers) -> tuple[str, str, str]:
    pid, flat = await setup(http, two.alice.headers)
    v = await add(http, two.alice.headers, pid, body(flat, "1.00", T1))
    return pid, flat, v["id"]


async def test_bob_cannot_add_to_alices_valuations(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid, flat, _ = await _alices(http, two_users)
    await assert_hidden_from(http, two_users.bob, "POST", url(pid), json=body(flat, "9.00", T2))


async def test_bob_cannot_list_alices_valuations(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid, _, _ = await _alices(http, two_users)
    await assert_hidden_from(http, two_users.bob, "GET", url(pid))


async def test_bob_cannot_read_alices_latest_valuations(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid, _, _ = await _alices(http, two_users)
    r = await http.get(f"{url(pid)}/latest", headers=two_users.bob.headers)
    assert r.status_code == 404
    missing = await http.get(f"{url(str(uuid.uuid4()))}/latest", headers=two_users.bob.headers)
    assert r.json()["type"] == missing.json()["type"]


async def test_bob_cannot_read_alices_valuation(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid, _, vid = await _alices(http, two_users)
    await assert_hidden_from(http, two_users.bob, "GET", url(pid, vid))


async def test_bob_cannot_change_alices_valuation(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    pid, _, vid = await _alices(http, two_users)
    await assert_hidden_from(http, two_users.bob, "PATCH", url(pid, vid), json={"source": "bob"})
    assert await db.fetchval("SELECT source FROM valuations WHERE id = $1", uuid.UUID(vid)) == (
        "owner estimate"
    )


async def test_bob_cannot_delete_alices_valuation(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    pid, _, vid = await _alices(http, two_users)
    await assert_hidden_from(http, two_users.bob, "DELETE", url(pid, vid))
    assert await db.fetchval("SELECT count(*) FROM valuations WHERE id = $1", uuid.UUID(vid)) == 1


async def test_latest_only_looks_at_the_portfolio_asked_about(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    """The same asset valued at the same moment in two portfolios stays in its own portfolio."""
    h = two_users.alice.headers
    first, flat = await setup(http, h)
    second, _ = await setup(http, h)
    await add(http, h, first, body(flat, "1.00", T1))
    await add(http, h, second, body(flat, "2.00", T1))
    latest = (await http.get(f"{url(first)}/latest", headers=h)).json()
    assert [(v["portfolio_id"], v["value"]["amount"]) for v in latest] == [(first, "1.00")]
