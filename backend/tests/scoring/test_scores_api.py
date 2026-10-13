"""GET /api/v1/universe/scores (P12-T03) on the real database: scores from stored closes and the
DEMO universe, decomposed into contributions, missing data lowering confidence, eligibility per
user, and authentication."""

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

pytestmark = [pytest.mark.integration]
TODAY = datetime.now(UTC).date()


async def store_closes(
    session: AsyncSession, asset_id: uuid.UUID, currency: str, days: int, step: str
) -> None:
    price = Decimal(100)
    for i in range(days, -1, -1):
        on = TODAY - timedelta(days=i)
        if on.weekday() >= 5:
            continue
        price = price * (1 + Decimal(step)) * (Decimal("1.01") if i % 2 else Decimal("0.99"))
        at = datetime.combine(on, time(21), UTC)
        await session.execute(
            text(
                "INSERT INTO market_prices (asset_id, price, currency, price_type, provider, "
                "as_of, retrieved_at) VALUES (:a, :p, :c, 'close', 'fake', :t, :t)"
            ),
            {"a": asset_id, "p": price.quantize(Decimal("0.0001")), "c": currency, "t": at},
        )
    await session.commit()


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    application = create_app(migrated_settings, readiness_checks={}, token_verifier=ah.verifier())
    sessions: async_sessionmaker[AsyncSession] = application.state.db.session_factory
    async with sessions() as s:
        await ingest(s, DemoUniverseSource())
        ids = dict((await s.execute(select(Asset.symbol, Asset.id))).all())
        await store_closes(s, ids["DEMO-GEQ"], "USD", 400, "0.0005")  # a full year, calm
        await store_closes(s, ids["DEMO-TEC"], "USD", 400, "0.002")  # a full year, steeper
        await store_closes(s, ids["DEMO-KEN"], "KES", 120, "0.001")  # four months only
    yield application
    await application.state.db.dispose()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def scores(http: httpx.AsyncClient, h: dict[str, str], **params: Any) -> dict[str, Any]:
    r = await http.get("/api/v1/universe/scores", headers=h, params=params)
    assert r.status_code == 200, r.text
    return dict(r.json())


def by_symbol(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {i["symbol"]: i for i in body["items"]}


async def test_scores_decompose_into_contributions_and_say_what_they_are(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    body = await scores(http, two_users.alice.headers)
    weights = {"stability": "25", "resilience": "20", "momentum": "15", "cost": "10"}
    assert body["weights_percent"] == weights | {"liquidity": "15", "risk_class": "15"}
    assert "not forecasts or expected returns" in body["notice"]
    s = by_symbol(body)
    geq = s["DEMO-GEQ"]["score"]
    assert geq["confidence"] == "high" and geq["coverage_percent"] == "100"
    total = sum(Decimal(f["contribution"]) for f in geq["factors"])
    assert abs(total - Decimal(geq["score"])) <= Decimal("0.03"), "rounded parts add up"
    assert {f["factor"]: f["status"] for f in geq["factors"]} == dict.fromkeys(
        ["stability", "resilience", "momentum", "cost", "liquidity", "risk_class"], "used"
    )
    cost = next(f for f in geq["factors"] if f["factor"] == "cost")
    assert (cost["measure"], cost["unit"], cost["points"]) == ("0.2", "percent", "90")
    momentum = next(f for f in geq["factors"] if f["factor"] == "momentum")
    assert "not a forecast" in momentum["explanation"]
    assert s["DEMO-GEQ"]["is_demo"] is True and s["DEMO-GEQ"]["last_close"] is not None


async def test_missing_data_lowers_confidence_or_withholds_the_score(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    s = by_symbol(await scores(http, two_users.alice.headers))
    ken = s["DEMO-KEN"]["score"]  # a share with four months of prices
    status = {f["factor"]: f["status"] for f in ken["factors"]}
    assert status["momentum"] == status["stability"] == status["resilience"] == "missing"
    assert status["cost"] == "not_applicable"
    assert ken["score"] is None and ken["confidence"] == "none"
    assert any("Less than 10 months" in r for r in ken["reasons"])
    bond = s["DEMO-KTB"]["score"]  # valued manually: no prices at all
    assert bond["score"] is None and "Valued manually" in bond["reasons"][0]
    order = [i["symbol"] for i in (await scores(http, two_users.alice.headers))["items"]]
    scored = [sym for sym in order if s[sym]["score"]["score"] is not None]
    assert order[: len(scored)] == scored, "scored instruments first"
    values = [Decimal(s[sym]["score"]["score"]) for sym in scored]
    assert values == sorted(values, reverse=True)


async def test_eligibility_is_per_user_and_can_filter(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.bob.headers
    assert all(not i["eligible"] for i in (await scores(http, h))["items"])
    await http.patch("/api/v1/me/preferences", headers=h, json={"residence_country": "KE"})
    await http.post("/api/v1/risk-profiles", headers=h,
                    json={"risk_tolerance": "growth", "horizon_years": 10})  # fmt: skip
    only = await scores(http, h, eligible_only="true")
    symbols = {i["symbol"] for i in only["items"]}
    assert "DEMO-GEQ" in symbols and "DEMO-TEC" not in symbols  # risk level 5 > growth's 4
    assert all(i["eligible"] for i in only["items"])
    etfs = await scores(http, h, asset_class="etf")
    assert {i["asset_class"] for i in etfs["items"]} == {"etf"}


async def test_scores_need_a_signed_in_user_and_a_valid_filter(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    assert (await http.get("/api/v1/universe/scores")).status_code == 401
    r = await http.get("/api/v1/universe/scores", headers=two_users.alice.headers,
                       params={"asset_class": "1;"})  # fmt: skip
    assert r.status_code == 422
