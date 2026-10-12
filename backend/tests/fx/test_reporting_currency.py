"""The reporting currency across the read APIs (P11-T06): the synced preference, one snapshot per
response, totals that reconcile, and originals that never change."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
TODAY = datetime.now(UTC).date()
RATES = {"EUR": "0.92", "AED": "3.6725", "KES": "129.15"}


def m(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


@pytest.fixture
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    application = create_app(migrated_settings, readiness_checks={}, token_verifier=ah.verifier())
    yield application
    await application.state.db.dispose()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def raw(migrated_settings: Settings) -> AsyncIterator[asyncpg.Connection]:  # noqa: F811
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    yield conn
    await conn.close()


@pytest.fixture
async def rates(raw: asyncpg.Connection) -> dict[str, Decimal]:
    """The newest USD rates in the database, so the snapshot uses them."""
    stamp = datetime.now(UTC) - timedelta(seconds=30)
    for quote, value in RATES.items():
        await raw.execute(
            "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
            "retrieved_at) VALUES ('USD', $1, $2::numeric, 'reporting-test', $3, $3)",
            quote,
            value,
            stamp,
        )
    return {k: Decimal(v) for k, v in RATES.items()}


async def portfolio(http: httpx.AsyncClient, h: dict[str, str], currency: str, cash: str) -> str:
    r = await http.post(
        "/api/v1/portfolios",
        headers=h,
        json={"name": f"P {uuid.uuid4().hex[:6]}", "base_currency": currency},
    )
    pid = str(r.json()["id"])
    t = await http.post(
        f"/api/v1/portfolios/{pid}/transactions",
        headers=h,
        json={
            "transaction_type": "DEPOSIT",
            "trade_date": (TODAY - timedelta(days=10)).isoformat(),
            "currency": currency,
            "gross_amount": m(cash, currency),
        },
    )
    assert t.status_code == 201, t.text
    return pid


async def rows(raw: asyncpg.Connection, user_id: str) -> list[Any]:
    uid = uuid.UUID(user_id)
    return [
        *await raw.fetch(
            "SELECT t.* FROM transactions t JOIN portfolios p ON p.id = t.portfolio_id "
            "WHERE p.user_id = $1 ORDER BY t.id",
            uid,
        ),
        *await raw.fetch("SELECT * FROM portfolios WHERE user_id = $1 ORDER BY id", uid),
        *await raw.fetch("SELECT * FROM goals WHERE user_id = $1 ORDER BY id", uid),
    ]


# ----------------------------------------------------------------------------------- preference
async def test_the_preference_defaults_to_the_base_currency_and_is_stored_on_the_server(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    a, b = two_users.alice.headers, two_users.bob.headers
    assert (await http.get("/api/v1/me/currency-preferences")).status_code == 401
    first = (await http.get("/api/v1/me/currency-preferences", headers=a)).json()
    assert first == {
        "reporting_currency": "USD",
        "recent_currencies": [],
        "is_default": True,
        "updated_at": None,
    }
    for code in ("AED", "EUR", "KES", "AED"):
        r = await http.patch(
            "/api/v1/me/currency-preferences", headers=a, json={"reporting_currency": code}
        )
        assert r.status_code == 200, r.text
    now = r.json()
    assert now["reporting_currency"] == "AED" and now["is_default"] is False
    assert now["recent_currencies"] == ["KES", "EUR"], "most recent first, without the current one"
    # Another device (a new client, the same account) sees the same setting.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as other_device:
        synced = await other_device.get("/api/v1/me/currency-preferences", headers=a)
    assert synced.json()["reporting_currency"] == "AED"
    # Bob is not affected, and cannot be affected through Alice.
    assert (await http.get("/api/v1/me/currency-preferences", headers=b)).json()["is_default"]
    for bad in (
        {"reporting_currency": "XYZ"},
        {"reporting_currency": "usd"},
        {"reporting_currency": "EUR", "user_id": str(uuid.uuid4())},
    ):
        assert (
            await http.patch("/api/v1/me/currency-preferences", headers=a, json=bad)
        ).status_code == 422


# -------------------------------------------------------------------------- one snapshot, reconcile
async def test_figures_follow_the_preference_and_reconcile_under_one_snapshot(
    http: httpx.AsyncClient,
    raw: asyncpg.Connection,
    rates: dict[str, Decimal],
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    usd = await portfolio(http, h, "USD", "1000.00")
    aed = await portfolio(http, h, "AED", "3672.50")
    await http.patch(
        "/api/v1/me/currency-preferences", headers=h, json={"reporting_currency": "EUR"}
    )
    before = await rows(raw, two_users.alice.id)

    summary = (await http.get("/api/v1/portfolios/consolidated/summary", headers=h)).json()
    net_worth = (await http.get("/api/v1/net-worth", headers=h)).json()
    dashboard = (await http.get("/api/v1/dashboard", headers=h)).json()

    assert summary["currency"] == net_worth["currency"] == dashboard["currency"] == "EUR"
    snapshot = summary["reporting"]["snapshot_id"]
    assert net_worth["reporting"]["snapshot_id"] == snapshot
    assert dashboard["reporting"]["snapshot_id"] == snapshot, "the same rates, the same snapshot"

    used = {(r["base"], r["quote"]): r for r in summary["reporting"]["rates"]}
    usd_eur = used[("USD", "EUR")]
    aed_eur = used[("AED", "EUR")]
    assert usd_eur["from_snapshot"] and aed_eur["from_snapshot"]
    assert Decimal(usd_eur["rate"]) == rates["EUR"]
    assert aed_eur["path"] == ["AED", "USD", "EUR"]
    for r in (usd_eur, aed_eur):
        assert r["rate_timestamp"] and r["provider"] and r["status"] == "current"

    # The converted total is the sum of the converted parts (each rounded to cents).
    parts = Decimal("1000.00") * Decimal(usd_eur["rate"]) + Decimal("3672.50") * Decimal(
        aed_eur["rate"]
    )
    assert abs(Decimal(summary["total_value"]["amount"]) - parts) <= Decimal("0.01")
    assert summary["total_value"] == net_worth["assets"] == dashboard["net_worth"]["assets"]
    shares = sum(Decimal(c["value"]["amount"]) for c in summary["currencies"])
    assert abs(shares - Decimal(summary["total_value"]["amount"])) <= Decimal("0.02")

    # A one-off view in another currency, and the portfolio itself unchanged.
    view = (
        await http.get(f"/api/v1/portfolios/{aed}/summary", headers=h, params={"currency": "USD"})
    ).json()
    assert view["currency"] == "USD" and view["total_value"] == m("1000.00")
    own = (await http.get(f"/api/v1/portfolios/{aed}/summary", headers=h)).json()
    assert own["currency"] == "AED" and own["total_value"] == m("3672.50", "AED")
    usd_view = (await http.get(f"/api/v1/portfolios/{usd}/summary", headers=h)).json()
    assert usd_view["reporting"]["rates"] == []

    # Switching currency changed nothing stored.
    await http.patch(
        "/api/v1/me/currency-preferences", headers=h, json={"reporting_currency": "KES"}
    )
    kes = (await http.get("/api/v1/net-worth", headers=h)).json()
    assert kes["currency"] == "KES"
    assert await rows(raw, two_users.alice.id) == before


async def test_an_explicit_currency_overrides_the_preference_for_that_request_only(
    http: httpx.AsyncClient,
    rates: dict[str, Decimal],
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    await portfolio(http, h, "USD", "100.00")
    once = (await http.get("/api/v1/net-worth", headers=h, params={"currency": "AED"})).json()
    assert once["currency"] == "AED" and once["assets"] == m("367.25", "AED")
    again = (await http.get("/api/v1/net-worth", headers=h)).json()
    assert again["currency"] == "USD"
    income = (
        await http.get("/api/v1/income/summary", headers=h, params={"currency": "EUR"})
    ).json()
    assert income["currency"] == "EUR" and income["reporting"]["currency"] == "EUR"


# ----------------------------------------------------------------------------- goals, forecasts
async def test_goals_keep_their_currency_and_show_the_reporting_one_beside_it(
    http: httpx.AsyncClient,
    raw: asyncpg.Connection,
    rates: dict[str, Decimal],
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h, "AED", "36725.00")
    goal = await http.post(
        "/api/v1/goals",
        headers=h,
        json={
            "name": "Home",
            "goal_type": "house_deposit",
            "target": m("367250.00", "AED"),
            "target_date": (TODAY + timedelta(days=900)).isoformat(),
            "portfolio_id": pid,
            "assumptions": {"contribution": m("1000.00", "AED"), "returns": {"base": "5"}},
        },
    )
    assert goal.status_code == 201, goal.text
    gid = goal.json()["id"]
    await http.patch(
        "/api/v1/me/currency-preferences", headers=h, json={"reporting_currency": "USD"}
    )
    summary = (await http.get("/api/v1/goals/summary", headers=h)).json()
    item = next(i for i in summary["items"] if i["id"] == gid)
    assert item["target"] == m("367250.00", "AED")
    assert item["target_in_reporting"] == m("100000.00")
    progress = (await http.get(f"/api/v1/goals/{gid}/progress", headers=h)).json()
    assert progress["target"] == m("367250.00", "AED")
    assert progress["target_in_reporting"] == m("100000.00")
    assert progress["current_value_in_reporting"] == m("10000.00")
    assert progress["reporting"]["currency"] == "USD"
    stored = await raw.fetchrow(
        "SELECT target_amount, target_currency FROM goals WHERE id = $1", uuid.UUID(gid)
    )
    assert stored is not None and stored["target_currency"] == "AED"


async def test_a_forecast_keeps_its_inputs_and_translates_only_its_end_values(
    http: httpx.AsyncClient,
    rates: dict[str, Decimal],
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    body = {
        "initial_investment": m("10000.00"),
        "contribution": m("500.00"),
        "annual_return_percent": "8.00",
        "years": 20,
    }
    plain = (await http.post("/api/v1/forecasts/compound", headers=h, json=body)).json()
    assert plain["in_reporting"] is None
    r = await http.post(
        "/api/v1/forecasts/compound", headers=h, json=body, params={"reporting_currency": "AED"}
    )
    out = r.json()
    assert out["currency"] == "USD" and out["assumptions"]["initial_investment"] == m("10000.00")
    assert out["projection"] == plain["projection"], "the forecast itself is unchanged"
    translated = out["in_reporting"]
    final = Decimal(plain["projection"]["final_nominal"]["amount"])
    assert translated["final_nominal"] == m(
        str((final * rates["AED"]).quantize(Decimal("0.01"))), "AED"
    )
    assert "Future exchange rates are not forecast" in translated["note"]
    bad = await http.post(
        "/api/v1/forecasts/compound", headers=h, json=body, params={"reporting_currency": "XYZ"}
    )
    assert bad.status_code == 422


# ------------------------------------------------------------------------------------- IDOR
async def test_bob_cannot_view_alices_portfolio_in_another_currency(
    http: httpx.AsyncClient,
    rates: dict[str, Decimal],
    two_users: TwoUsers,  # noqa: F811
) -> None:
    pid = await portfolio(http, two_users.alice.headers, "AED", "100.00")
    await assert_hidden_from(
        http, two_users.bob, "GET", f"/api/v1/portfolios/{pid}/summary?currency=USD"
    )
    assert (
        await http.get(f"/api/v1/portfolios/{pid}/summary", headers=two_users.alice.headers)
    ).status_code == 200
