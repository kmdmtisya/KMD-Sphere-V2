"""POST /api/v1/ai/compare and /api/v1/ai/simulate (P12-T07) on the real database: side-by-side
facts with past figures labelled past and no future return; simulation through the forecast
engine under the user's own return assumptions only, with notes where they differ from what is
recorded; optional portfolio fit; validation and ownership."""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.modules.assets.models import Asset
from app.modules.universe.ingestion import DemoUniverseSource, ingest
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.test_analytics_api import Book, m

pytestmark = [pytest.mark.integration, pytest.mark.security]
TODAY = datetime.now(UTC).date()
SCENARIOS: dict[str, Any] = {
    "initial_investment": m("10000.00"),
    "contribution": m("500.00"),
    "annual_return_percent": "8.00",
    "conservative_return_percent": "5.00",
    "growth_return_percent": "12.00",
    "years": 20,
    "inflation_percent": "2.50",
    "annual_fee_percent": "0.50",
}


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    application = create_app(migrated_settings, readiness_checks={}, token_verifier=ah.verifier())
    sessions: async_sessionmaker[AsyncSession] = application.state.db.session_factory
    async with sessions() as s:
        await ingest(s, DemoUniverseSource())
        ids = dict((await s.execute(select(Asset.symbol, Asset.id))).all())
        price = Decimal(100)
        for i in range(400, -1, -1):
            on = TODAY - timedelta(days=i)
            if on.weekday() >= 5:
                continue
            price = price * Decimal("1.0005") * (Decimal("1.01") if i % 2 else Decimal("0.99"))
            await s.execute(
                text(
                    "INSERT INTO market_prices (asset_id, price, currency, price_type, provider, "
                    "as_of, retrieved_at) VALUES (:a, :p, 'USD', 'close', 'fake', :t, :t)"
                ),
                {
                    "a": ids["DEMO-GEQ"],
                    "p": price.quantize(Decimal("0.0001")),
                    "t": datetime.combine(on, time(21), UTC),
                },
            )
        await s.commit()
        application.state.ids = {k: str(v) for k, v in ids.items()}
    yield application
    await application.state.db.dispose()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def post(http: httpx.AsyncClient, h: dict[str, str], path: str, body: Any) -> dict[str, Any]:
    r = await http.post(path, headers=h, json=body)
    assert r.status_code == 200, r.text
    return dict(r.json())


async def portfolio(http: httpx.AsyncClient, h: dict[str, str]) -> str:
    book = Book(http, h)
    pid = await book.portfolio()
    await book.post(pid, "DEPOSIT", gross_amount=m("20000.00"))
    return pid


# ------------------------------------------------------------------------------------ compare
async def test_compare_shows_past_and_recorded_facts_and_no_future_return(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    ids = app.state.ids
    body = await post(
        http,
        two_users.alice.headers,
        "/api/v1/ai/compare",
        {"asset_ids": [ids["DEMO-GEQ"], ids["DEMO-KTB"]]},
    )
    geq, bond = body["items"]
    assert [geq["symbol"], bond["symbol"]] == ["DEMO-GEQ", "DEMO-KTB"], "in the order asked"
    assert geq["past"]["volatility_percent"] is not None and geq["past"]["weeks_of_prices"] > 26
    assert geq["past"]["price_change_percent"] is not None
    assert bond["past"] == {
        "price_change_percent": None,
        "volatility_percent": None,
        "max_drawdown_percent": None,
        "last_close": None,
        "weeks_of_prices": 0,
    }
    assert geq["expense_ratio_percent"] == "0.2" and bond["expense_ratio_percent"] is None
    assert geq["income_yield"] is None and bond["minimum_investment"] == m("50000.00") | {
        "currency": "KES"
    }
    assert geq["score"]["confidence"] == "high" and bond["score"]["score"] is None
    assert not geq["eligible"] and "No country of residence is set." in geq["eligibility_reasons"]
    assert geq["research_horizon"]["minimum_years"] == 5
    assert geq["diversification"] is None
    assert "No future return is shown" in body["notice"]
    # No field carries a future return; the text only disclaims ("past, not a forecast").
    keys: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            keys.update(value)
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(body)
    assert not {k for k in keys if any(w in k for w in ("expected", "projected", "forecast"))}
    text_ = json.dumps(body).lower()
    for word in ("expected return", "target price", "will rise"):
        assert word not in text_, word


async def test_compare_with_a_portfolio_shows_each_diversification_impact(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    ids = app.state.ids
    body = await post(
        http,
        h,
        "/api/v1/ai/compare",
        {
            "asset_ids": [ids["DEMO-GBD"], ids["DEMO-GLD"], ids["DEMO-GEQ"]],
            "portfolio_id": pid,
            "amount": m("2000.00"),
        },
    )
    for item in body["items"]:
        d = item["diversification"]
        assert d["portfolio_id"] == pid and d["is_trade"] is False
        assert d["after"]["instrument_share_percent"] == "9.09"


async def test_compare_is_validated_and_owner_scoped(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    ids = app.state.ids
    h = two_users.alice.headers
    pair = [ids["DEMO-GEQ"], ids["DEMO-GBD"]]
    assert (await http.post("/api/v1/ai/compare", json={"asset_ids": pair})).status_code == 401
    bad = [
        {"asset_ids": [ids["DEMO-GEQ"]]},
        {
            "asset_ids": [
                ids[s]
                for s in ("DEMO-GEQ", "DEMO-GBD", "DEMO-GLD", "DEMO-TEC", "DEMO-BTC", "DEMO-KEN")
            ]
        },
        {"asset_ids": [ids["DEMO-GEQ"], ids["DEMO-GEQ"]]},
        {"asset_ids": pair, "portfolio_id": str(uuid.uuid4())},  # no amount
        {"asset_ids": pair, "advice": True},
    ]
    for body in bad:
        assert (await http.post("/api/v1/ai/compare", headers=h, json=body)).status_code == 422
    unknown = await http.post(
        "/api/v1/ai/compare", headers=h, json={"asset_ids": [ids["DEMO-GEQ"], str(uuid.uuid4())]}
    )
    assert unknown.status_code == 404
    pid = await portfolio(http, h)
    foreign = await http.post(
        "/api/v1/ai/compare",
        headers=two_users.bob.headers,
        json={"asset_ids": pair, "portfolio_id": pid, "amount": m("100.00")},
    )
    assert foreign.status_code == 404


# ----------------------------------------------------------------------------------- simulate
async def test_simulate_runs_the_engine_under_the_users_returns_only(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    body = await post(
        http,
        h,
        "/api/v1/ai/simulate",
        {"asset_id": app.state.ids["DEMO-GEQ"], "assumptions": SCENARIOS},
    )
    engine = await post(http, h, "/api/v1/forecasts/scenarios", SCENARIOS)
    assert body["simulation"]["scenarios"] == engine["scenarios"], "the same deterministic engine"
    assert body["returns_source"] == "your_assumptions" and body["fit"] is None
    assert body["notes"][0] == (
        "The instrument's recorded expense ratio is 0.2% a year; your assumptions use 0.5%."
    )
    assert any("not a forecast of this instrument" in n for n in body["notes"])
    assert "not a forecast" in body["notice"] and "nothing is guaranteed" in body["notice"]


async def test_simulate_notes_the_currency_and_checks_the_fit(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await portfolio(http, h)
    body = await post(
        http,
        h,
        "/api/v1/ai/simulate",
        {"asset_id": app.state.ids["DEMO-KRT"], "assumptions": SCENARIOS, "portfolio_id": pid},
    )
    assert any("priced in KES" in n and "not modelled" in n for n in body["notes"])
    fit = body["fit"]
    assert fit["amount"] == m("10000.00") and fit["verdict"] == "not_suitable"
    assert {r["code"] for r in fit["reasons"]} >= {"eligibility_jurisdiction", "eligibility_risk"}


async def test_simulate_needs_the_users_returns_and_a_known_instrument(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    geq = app.state.ids["DEMO-GEQ"]
    no_returns = {k: v for k, v in SCENARIOS.items() if not k.endswith("return_percent")}
    for assumptions in (no_returns, SCENARIOS | {"conservative_return_percent": "9.00"}):
        r = await http.post(
            "/api/v1/ai/simulate", headers=h, json={"asset_id": geq, "assumptions": assumptions}
        )
        assert r.status_code == 422
    unknown = await http.post(
        "/api/v1/ai/simulate",
        headers=h,
        json={"asset_id": str(uuid.uuid4()), "assumptions": SCENARIOS},
    )
    assert unknown.status_code == 404
    assert (await http.post("/api/v1/ai/simulate", json={})).status_code == 401
