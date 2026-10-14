# ruff: noqa: F811 (imported pytest fixtures are used by name as test parameters)
"""The risk calculator API and the contract specifications on the real database (P13-T07.1,
T07.5): a USD-quoted pair, a JPY pair converted by its own inverse rate and a cross converted
through GBP_USD, with the rate's path and freshness; costs from the latest fresh quote and the
specification; refusals (no rate is ever assumed); versioned specifications with review; sign-in
and the flag."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.orchestrator.guards import guarantee_problems
from app.core.config import Settings
from app.main import create_app
from app.modules.forex.marketdata.repository import store_quotes
from app.modules.forex.marketdata.types import DataType, FeedStatus, Quality, Quote, ReceivedQuote
from app.modules.forex.risk import specs
from app.modules.forex.risk.specs import ForexContractSpec
from tests import auth_helpers as ah
from tests.authz_harness import TestUser, make_user
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.forex.test_forex_api import app, http, sessions, user  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
PATH = "/api/v1/forex"
D = Decimal


async def quote(
    sessions: async_sessionmaker[AsyncSession], pair: str, bid: str, ask: str, age: float = 1
) -> None:
    at = datetime.now(UTC) - timedelta(seconds=age)
    q = Quote("fake", pair, D(bid), D(ask), at, DataType.SIMULATED)
    async with sessions() as s:
        await store_quotes(s, [ReceivedQuote(q, at, Quality.OK, FeedStatus.CONNECTED)])


def body(**changes: Any) -> dict[str, Any]:
    out = {
        "instrument": "EUR_USD",
        "direction": "long",
        "entry": "1.10000",
        "stop": "1.09500",
        "target": "1.11000",
        "balance": "10000",
        "account_currency": "USD",
        "risk_percent": "1",
    }
    out.update(changes)
    return out


async def calculate(http: httpx.AsyncClient, user: TestUser, **changes: Any) -> httpx.Response:
    return await http.post(f"{PATH}/risk/calculate", json=body(**changes), headers=user.headers)


async def test_a_usd_quoted_pair_with_costs_from_the_quote_and_the_specification(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await quote(sessions, "EUR_USD", "1.09994", "1.10006")  # spread 1.2 pips
    r = await calculate(http, user)
    assert r.status_code == 200, r.text
    out = r.json()
    # per unit: 0.005 stop + 0.00012 spread + 2 x 0.2 pips slippage = 0.00516 -> 19,379 -> 19,000
    assert out["size"] == {"units": "19000", "lots": "0.19", "status": "sized"}
    assert out["pip_value"]["per_lot_quote_currency"] == "10"
    assert out["pip_value"]["per_lot_account_currency"] == "10"
    assert out["outcome"]["loss_before_costs"] == "95"
    assert out["costs"]["spread"] == "2.28" and out["costs"]["slippage"] == "0.76"
    assert out["outcome"]["loss_after_costs"] == "98.04"
    assert D(out["outcome"]["loss_after_costs"]) <= D(out["outcome"]["risk_amount"])
    assert out["margin"]["margin"] == "695.97" and out["margin"]["max_leverage"] == "30.03"
    assert out["conversion"]["path"] == "same currency" and out["conversion"]["rate"] == "1"
    assert out["specification"]["version"] == 1
    assert out["specification"]["review_status"] == "unreviewed"
    assert any("unreviewed defaults" in w for w in out["warnings"])
    assert any("gap or slip" in d for d in out["disclosures"])
    assert {e["currency"] for e in out["exposure"]} == {"EUR", "USD"}
    assert (
        guarantee_problems(
            [*out["warnings"], *out["disclosures"], out["notice"]], forecast_used=False
        )
        == []
    )


async def test_a_jpy_pair_uses_its_own_inverse_rate_not_a_fixed_pip_value(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await quote(sessions, "USD_JPY", "149.990", "150.010")  # mid 150
    r = await calculate(
        http, user, instrument="USD_JPY", entry="150.000", stop="149.500", target="151.000"
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["conversion"]["path"] == "1 / USD_JPY mid"
    assert out["conversion"]["data_types"] == ["simulated"]
    assert out["pip_value"]["per_lot_quote_currency"] == "1000"
    assert out["pip_value"]["per_lot_account_currency"] == "6.6667"
    # risk 100 USD = 15,000 JPY; per unit 0.5 + 0.02 spread + 0.004 slippage = 0.524 -> 28,000
    assert out["size"]["units"] == "28000"
    assert any("simulated, not a tradable quote" in w for w in out["warnings"])


async def test_a_cross_converts_through_the_quote_currency_pair(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await quote(sessions, "GBP_USD", "1.24990", "1.25010")
    await quote(sessions, "EUR_GBP", "0.84995", "0.85005")
    r = await calculate(
        http, user, instrument="EUR_GBP", entry="0.85000", stop="0.84500", target="0.86000"
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["conversion"]["path"] == "GBP_USD mid" and out["conversion"]["rate"] == "1.25"
    assert out["pip_value"]["per_lot_account_currency"] == "12.5"
    assert D(out["outcome"]["loss_after_costs"]) <= D("100")


async def test_a_stale_quote_leaves_the_spread_unknown(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await quote(sessions, "USD_CHF", "0.88000", "0.88010", age=600)
    r = await calculate(
        http,
        user,
        instrument="USD_CHF",
        entry="0.88000",
        stop="0.87500",
        target=None,
        account_currency="CHF",
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["costs"]["spread"] == "0"
    assert any("spread is unknown" in w for w in out["warnings"])
    assert out["outcome"]["profit_before_costs"] is None


async def test_refusals(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await quote(sessions, "EUR_USD", "1.09994", "1.10006")
    for changes in (
        {"account_currency": "SEK"},  # no stored rate: never assumed
        {"instrument": "EUR_SEK"},  # not a known pair
        {"stop": "1.10500"},  # a long with the stop above the entry
        {"risk_percent": "150"},
        {"risk_percent": 1},  # a number, not a decimal string
        {"account_currency": "usd"},
        {"direction": "sideways"},
    ):
        r = await calculate(http, user, **changes)
        assert r.status_code == 422, (changes, r.text)
    assert "SEK" in (await calculate(http, user, account_currency="SEK")).text


async def test_the_contract_specifications(http: httpx.AsyncClient, user: TestUser) -> None:
    r = await http.get(f"{PATH}/contract-specs", headers=user.headers)
    assert r.status_code == 200, r.text
    items = {i["instrument"]: i for i in r.json()["items"]}
    assert len(items) == 12
    eur = items["EUR_USD"]
    assert eur["margin_rate"] == "0.0333" and eur["max_leverage"] == "30.03"
    assert eur["review_status"] == "unreviewed" and eur["reviewed_by"] is None
    assert items["USD_KES"]["max_lots"] == "20"


async def test_specifications_are_versioned_and_reviewed(
    sessions: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    v1 = json.loads(specs.SPEC_FILE.read_text(encoding="utf-8"))
    nzd = next(i for i in v1["instruments"] if i["code"] == "NZD_USD")
    v2 = {**v1, "version": 2, "instruments": [{**nzd, "margin_rate": "0.05"}]}
    path = tmp_path / "v2.json"
    path.write_text(json.dumps(v2), encoding="utf-8")
    try:
        async with sessions() as s:
            assert (await specs.sync(s))["added"] == 0  # idempotent
            assert await specs.sync(s, path) == {"version": 2, "added": 1}
            assert await specs.sync(s, path) == {"version": 2, "added": 0}
            active = await specs.active_spec(s, "NZD_USD")
            assert active is not None and active.version == 2 and active.margin_rate == D("0.05")
            rows = (
                await s.execute(
                    select(ForexContractSpec).where(ForexContractSpec.instrument == "NZD_USD")
                )
            ).scalars()
            assert {(r.version, r.status) for r in rows} == {(1, "superseded"), (2, "active")}
            reviewed = await specs.mark_reviewed(s, "NZD_USD", 2, " Risk desk ", datetime.now(UTC))
            assert reviewed.review_status == "reviewed" and reviewed.reviewed_by == "Risk desk"
            with pytest.raises(ValueError, match="reviewer"):
                await specs.mark_reviewed(s, "NZD_USD", 2, "  ", datetime.now(UTC))
            with pytest.raises(ValueError, match="no such"):
                await specs.mark_reviewed(s, "NZD_USD", 9, "x", datetime.now(UTC))
            v2["instruments"][0]["margin_rate"] = "0.04"
            path.write_text(json.dumps(v2), encoding="utf-8")
            with pytest.raises(ValueError, match="bump the version"):
                await specs.sync(s, path)
            await s.rollback()
    finally:
        async with sessions() as s:
            await s.execute(
                delete(ForexContractSpec).where(
                    ForexContractSpec.instrument == "NZD_USD", ForexContractSpec.version == 2
                )
            )
            await s.execute(
                update(ForexContractSpec)
                .where(ForexContractSpec.instrument == "NZD_USD", ForexContractSpec.version == 1)
                .values(status="active")
            )
            await s.commit()


async def test_sign_in_and_the_flag(http: httpx.AsyncClient, migrated_settings: Settings) -> None:
    assert (await http.post(f"{PATH}/risk/calculate", json=body())).status_code == 401
    assert (await http.get(f"{PATH}/contract-specs")).status_code == 401
    off = create_app(
        migrated_settings.model_copy(update={"forex_enabled": False}),
        readiness_checks={},
        token_verifier=ah.verifier(),
    )
    transport = httpx.ASGITransport(app=off, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            someone = await make_user(client, "risk-off")
            r = await client.post(f"{PATH}/risk/calculate", json=body(), headers=someone.headers)
            assert r.status_code == 404
            assert (
                await client.get(f"{PATH}/contract-specs", headers=someone.headers)
            ).status_code == 404
    finally:
        await off.state.db.dispose()
