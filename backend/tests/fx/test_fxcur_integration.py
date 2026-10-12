"""FXCUR integration drills (P11-T09) on the running app and database: one snapshot across
dashboard, summary, net worth and the AI, outage and fallback with honest labels, stale rates,
historical reports, AI conversions through the chat, and the setting across two sessions."""

import json
import secrets
import string
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.ai.providers.fake import FakeLlmProvider, text_reply, tool_reply
from app.core.config import Settings
from app.main import create_app
from app.modules.market_data.providers.errors import ProviderUnavailable
from app.modules.market_data.providers.registry import MarketProviders
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.fx.test_refresh_and_status import StubFx

pytestmark = [pytest.mark.integration, pytest.mark.security]
LAUNCH = ["AED", "AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "KES", "USD", "ZAR"]


def code() -> str:
    return "Q" + "".join(secrets.choice(string.ascii_uppercase) for _ in range(2))


@pytest.fixture
async def raw(migrated_settings: Settings) -> AsyncIterator[asyncpg.Connection]:  # noqa: F811
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    yield conn
    await conn.close()


@pytest.fixture
def llm() -> FakeLlmProvider:
    return FakeLlmProvider()


@pytest.fixture
async def stack(
    migrated_settings: Settings,  # noqa: F811
    raw: asyncpg.Connection,
    llm: FakeLlmProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[FastAPI, str]]:
    """The app with its own pivot currency (so this file's rates never mix with others')."""
    pivot = code()
    await raw.execute(
        "INSERT INTO currencies (code, name, symbol, decimal_places) VALUES ($1, 'Pivot', 'P', 2)",
        pivot,
    )
    settings = migrated_settings.model_copy(
        update={
            "fx_pivot_currency": pivot,
            "ai_tool_calls_per_minute": 1000,
            "ai_questions_per_day": 1000,
            "rate_limit_enabled": False,
        }
    )
    import app.ai.tools.currency as currency
    import app.modules.market_data.service as fx_service
    import app.modules.portfolio.summary_service as summary_service

    for module in (currency, summary_service):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(fx_service, "get_settings", lambda: settings)
    app = create_app(settings, readiness_checks={}, token_verifier=ah.verifier(), llm=llm)
    yield app, pivot
    await app.state.db.dispose()
    await raw.execute("DELETE FROM currencies WHERE code = $1", pivot)


@pytest.fixture
async def http(stack: tuple[FastAPI, str]) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=stack[0], raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def stub(
    pivot: str, name: str, rates: dict[str, str], *, age: timedelta = timedelta(minutes=5)
) -> StubFx:
    return StubFx(
        name,
        {c: Decimal(v) for c, v in rates.items() if c != pivot},
        published=datetime.now(UTC) - age,
    )


def rates_for(pivot: str) -> dict[str, str]:
    """1 pivot = r currency; the pivot behaves like USD (USD itself is 1)."""
    return {
        "AED": "3.6725",
        "AUD": "1.5112",
        "CAD": "1.3705",
        "CHF": "0.8634",
        "EUR": "0.9216",
        "GBP": "0.7712",
        "JPY": "149.83",
        "KES": "129.15",
        "USD": "1",
        "ZAR": "17.8421",
    }


async def refresh(
    app: FastAPI, http: httpx.AsyncClient, h: dict[str, str], *sources: StubFx
) -> dict[str, Any]:
    app.state.market_providers = MarketProviders({}, None, tuple(sources))
    r = await http.post("/api/v1/fx/refresh", headers=h)
    assert r.status_code == 200, r.text
    return dict(r.json())


async def portfolio(http: httpx.AsyncClient, h: dict[str, str], currency: str, cash: str) -> str:
    pid = str(
        (
            await http.post(
                "/api/v1/portfolios",
                headers=h,
                json={"name": f"P {uuid.uuid4().hex[:6]}", "base_currency": currency},
            )
        ).json()["id"]
    )
    r = await http.post(
        f"/api/v1/portfolios/{pid}/transactions",
        headers=h,
        json={
            "transaction_type": "DEPOSIT",
            "trade_date": (datetime.now(UTC).date() - timedelta(days=2)).isoformat(),
            "currency": currency,
            "gross_amount": {"amount": cash, "currency": currency},
        },
    )
    assert r.status_code == 201, r.text
    return pid


# --------------------------------------------------------------- one snapshot across surfaces
async def test_dashboard_summary_net_worth_and_ai_agree_for_one_snapshot(
    stack: tuple[FastAPI, str],
    http: httpx.AsyncClient,
    llm: FakeLlmProvider,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    app, pivot = stack
    h = two_users.alice.headers
    await refresh(app, http, h, stub(pivot, "drill-a", rates_for(pivot)))
    await portfolio(http, h, "AED", "36725.00")
    await portfolio(http, h, "KES", "129150.00")
    await http.patch(
        "/api/v1/me/currency-preferences", headers=h, json={"reporting_currency": "EUR"}
    )

    dashboard = (await http.get("/api/v1/dashboard", headers=h)).json()
    summary = (await http.get("/api/v1/portfolios/consolidated/summary", headers=h)).json()
    net_worth = (await http.get("/api/v1/net-worth", headers=h)).json()
    snapshot = summary["reporting"]["snapshot_id"]
    assert (
        dashboard["reporting"]["snapshot_id"] == net_worth["reporting"]["snapshot_id"] == snapshot
    )
    assert summary["total_value"] == net_worth["assets"] == dashboard["net_worth"]["assets"]
    # 36725 AED = 10000 pivot; 129150 KES = 1000 pivot; 11000 pivot x 0.9216 = 10137.60 EUR.
    assert summary["total_value"] == {"amount": "10137.60", "currency": "EUR"}

    # The AI reads the same figure from the same snapshot.
    llm.queue(
        tool_reply("get_portfolio_value", {"currency": "EUR"}),
        text_reply(
            json.dumps(
                {
                    "observed": [
                        {
                            "text": "Your portfolios are worth 10,137.60 EUR.",
                            "source": "get_portfolio_value",
                        }
                    ],
                    "interpretation": "Converted at today's rates, not a forecast.",
                }
            )
        ),
    )
    events = (
        await http.post("/api/v1/ai/chat", headers=h, json={"message": "What am I worth in euros?"})
    ).text
    tool_message = next(m for m in llm.requests[1].messages if m.role == "tool")
    data = json.loads(tool_message.content)["data"]
    assert data["total_value"] == summary["total_value"]
    assert data["reporting"]["snapshot_id"] == snapshot
    assert "event: done" in events and "10,137.60 EUR" in events


# ---------------------------------------------------------------------- outage and fallback
async def test_outage_fallback_and_recovery_keep_honest_labels(
    stack: tuple[FastAPI, str],
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    app, pivot = stack
    h = two_users.alice.headers
    all_rates = rates_for(pivot)
    ecb_like = stub(
        pivot, "drill-primary", {k: v for k, v in all_rates.items() if k not in ("AED", "KES")}
    )
    fallback = stub(pivot, "drill-fallback", all_rates)

    # Fallback: the primary has no AED/KES, the commercial source supplies them.
    body = await refresh(app, http, h, ecb_like, fallback)
    by = {line["currency"]: line for line in body["status"]["rates"]}
    assert by["AED"]["provider"] == "drill-fallback" and by["EUR"]["provider"] == "drill-primary"
    assert body["missing"] == []

    # Total outage: nothing is invented; the last good rates stay with their status.
    down = StubFx("drill-down", {}, fail=ProviderUnavailable("x"))
    later = datetime.now(UTC) + timedelta(minutes=20)  # a new refresh window
    import app.modules.fx.api as fx_api

    class Later(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> "Later":
            return cls.fromtimestamp(later.timestamp(), tz)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(fx_api, "datetime", Later)
        outage = await refresh(app, http, h, down, down)
    assert outage["refreshed"] is False
    assert all(a["failed"] for a in outage["attempts"])
    still = {line["currency"]: line for line in outage["status"]["rates"]}
    assert still["AED"]["rate"] == by["AED"]["rate"], "the last good rate, not a guess"

    # Conversions still work from the last good snapshot, and say how fresh it is.
    conv = await http.post(
        "/api/v1/fx/convert",
        headers=h,
        json={"amount": {"amount": "100", "currency": pivot}, "to": "AED"},
    )
    assert conv.status_code == 200 and conv.json()["converted"]["amount"] == "367.25"


async def test_stale_rates_are_labelled_stale_everywhere(
    stack: tuple[FastAPI, str],
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    app, pivot = stack
    h = two_users.alice.headers
    old = stub(pivot, "exchangerate_api", rates_for(pivot), age=timedelta(hours=30))
    await refresh(app, http, h, old)
    status = (await http.get("/api/v1/fx/status", headers=h)).json()
    assert {line["status"] for line in status["rates"]} == {"stale"}
    await portfolio(http, h, "AED", "3672.50")
    await http.patch(
        "/api/v1/me/currency-preferences", headers=h, json={"reporting_currency": "EUR"}
    )
    nw = (await http.get("/api/v1/net-worth", headers=h)).json()
    assert nw["reporting"]["rates"] and all(
        r["status"] == "stale" for r in nw["reporting"]["rates"]
    )
    rate = (await http.get("/api/v1/fx/rates/AED/EUR", headers=h)).json()
    assert rate["status"] == "stale"


# ------------------------------------------------------------------------------- history
async def test_a_historical_report_uses_each_days_rate(
    stack: tuple[FastAPI, str],
    http: httpx.AsyncClient,
    raw: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    _, pivot = stack
    h = two_users.alice.headers
    start = date(2026, 9, 7)
    for i, value in enumerate(("3.60", "3.61", "3.62")):
        await raw.execute(
            "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
            "retrieved_at) VALUES ($1, 'AED', $2::numeric, 'hist', $3, $3)",
            pivot,
            value,
            datetime(2026, 9, 7 + i, 12, tzinfo=UTC),
        )
    history = (
        await http.get(
            "/api/v1/fx/history",
            headers=h,
            params={"base": pivot, "quote": "AED", "start": str(start), "end": "2026-09-09"},
        )
    ).json()
    assert [p["rate"] for p in history["points"]] == ["3.6", "3.61", "3.62"]
    on_day = await http.post(
        "/api/v1/fx/convert",
        headers=h,
        json={"amount": {"amount": "100", "currency": pivot}, "to": "AED", "on": "2026-09-08"},
    )
    assert on_day.json()["converted"]["amount"] == "361.00"


# -------------------------------------------------------------------------- AI conversions
async def test_an_ai_conversion_is_the_servers_and_an_invented_rate_is_refused(
    stack: tuple[FastAPI, str],
    http: httpx.AsyncClient,
    llm: FakeLlmProvider,
    raw: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    app, pivot = stack
    h = two_users.alice.headers
    await refresh(app, http, h, stub(pivot, "drill-ai", rates_for(pivot)))
    args = {"amount": {"amount": "500000.00", "currency": "AED"}, "to": "EUR"}
    fact = "500,000 AED is 125,473.11 EUR at today's rate."
    good = json.dumps(
        {
            "calculated": [{"text": fact, "source": "convert_currency"}],
            "interpretation": "An indicative rate, not a quote for a transaction.",
        }
    )
    llm.queue(tool_reply("convert_currency", args), text_reply(good))
    ok = (
        await http.post(
            "/api/v1/ai/chat", headers=h, json={"message": "Convert 500,000 AED to EUR"}
        )
    ).text
    tool = json.loads(next(m for m in llm.requests[1].messages if m.role == "tool").content)
    assert tool["data"]["converted"] == {"amount": "125473.11", "currency": "EUR"}
    assert "event: done" in ok
    assert (
        await raw.fetchval(
            "SELECT count(*) FROM fx_conversion_audit WHERE user_id = $1 "
            "AND conversion_type = 'ai_answer'",
            uuid.UUID(two_users.alice.id),
        )
        == 1
    )

    invented = json.dumps(
        {"calculated": [{"text": "That is 130,000 EUR.", "source": "convert_currency"}]}
    )
    llm.reset()
    llm.queue(tool_reply("convert_currency", args), text_reply(invented), text_reply(invented))
    refused = (
        await http.post("/api/v1/ai/chat", headers=h, json={"message": "Convert it again"})
    ).text
    assert "invalid_answer" in refused and "130,000" not in refused


# ----------------------------------------------------------------------- two sessions, one setting
async def test_the_setting_follows_the_user_across_sessions(
    stack: tuple[FastAPI, str],
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    app, _ = stack
    phone = two_users.alice.headers
    tablet = ah.bearer(ah.token(two_users.alice.subject, email="alice@example.test"))
    await http.patch(
        "/api/v1/me/currency-preferences", headers=phone, json={"reporting_currency": "KES"}
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as other:
        seen = (await other.get("/api/v1/me/currency-preferences", headers=tablet)).json()
        assert seen["reporting_currency"] == "KES"
        nw = (await other.get("/api/v1/net-worth", headers=tablet)).json()
        assert nw["currency"] == "KES"
    bob = await http.get("/api/v1/me/currency-preferences", headers=two_users.bob.headers)
    assert bob.json()["reporting_currency"] == "USD", "another user is not affected"
