# ruff: noqa: F811 (imported pytest fixtures are used by name as test parameters)
"""Paper trading on the real database (P13-T09): accounts with the default balance marked;
market orders filled at the stored ask or bid with slippage, never the mid; refusals (no fresh
quote, size, levels, margin); stops, targets and limit orders triggered by later quotes; manual
closes and level changes; P/L converted into the account currency at the exit; the journal and
analytics; the PAPER TRADING marker on every response; ownership (another user's resources are
404 on every route); isolation from net worth and real analytics; the minute job; sign-in and
the flag."""

import ast
import asyncio
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.worker.tasks as tasks
from app.core.config import Settings
from app.main import create_app
from app.modules.forex.marketdata.repository import store_quotes
from app.modules.forex.marketdata.types import DataType, FeedStatus, Quality, Quote, ReceivedQuote
from tests import auth_helpers as ah
from tests.authz_harness import TestUser, make_user
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.forex.test_forex_api import app, http, sessions, user  # noqa: F401
from tests.forex.test_worker_jobs import use

pytestmark = [pytest.mark.integration, pytest.mark.security]
P = "/api/v1/forex/paper"
D = Decimal
APP = Path(__file__).resolve().parents[2] / "app"
TABLES = re.compile(r"forex_paper_(accounts|orders|positions|journal)")


async def quote(
    sessions: async_sessionmaker[AsyncSession],
    pair: str,
    bid: str,
    ask: str,
    at: datetime | None = None,
) -> datetime:
    at = at or datetime.now(UTC)
    q = Quote("fake", pair, D(bid), D(ask), at, DataType.SIMULATED)
    async with sessions() as s:
        await store_quotes(s, [ReceivedQuote(q, at, Quality.OK, FeedStatus.CONNECTED)])
    return at


async def account(http: httpx.AsyncClient, who: TestUser, **body: Any) -> dict[str, Any]:
    r = await http.post(
        f"{P}/accounts", json={"name": "Practice", "currency": "USD", **body}, headers=who.headers
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


async def order(
    http: httpx.AsyncClient, who: TestUser, account_id: str, **body: Any
) -> httpx.Response:
    payload = {
        "instrument": "NZD_USD",
        "side": "long",
        "lots": "0.10",
        "stop": "0.58000",
        "target": "0.61000",
        **body,
    }
    return await http.post(f"{P}/accounts/{account_id}/orders", json=payload, headers=who.headers)


def marked(r: httpx.Response) -> dict[str, Any]:
    assert r.headers.get("X-Trading-Mode") == "PAPER TRADING", r.headers
    body: dict[str, Any] = r.json()
    assert body["mode"] == "PAPER TRADING"
    return body


async def test_a_market_order_fills_at_the_ask_and_a_stop_closes_it_at_the_bid(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    acct = await account(http, user)
    assert acct["starting_balance"] == "10000" and acct["starting_balance_is_default"] is True
    assert acct["equity"] == "10000" and "never enter net worth" in acct["notice"]
    await quote(sessions, "NZD_USD", "0.60000", "0.60012")
    r = await order(http, user, acct["id"], strategy_tag="breakout")
    assert r.status_code == 201, r.text
    placed = marked(r)
    pos = placed["position"]
    # ask 0.60012 + slippage 0.4 pips: never the mid (0.60006)
    assert pos["entry_price"] == "0.60016" and pos["units"] == "10000" and pos["lots"] == "0.1"
    assert pos["status"] == "open" and pos["data_type"] == "simulated"
    assert pos["margin"] == "199.85"  # 10,000 x 0.60016 x 0.0333 = 199.853
    assert any("simulated" in w for w in placed["warnings"])
    assert any("unreviewed" in w for w in placed["warnings"])
    assert any("gap or slip" in d for d in placed["disclosures"])
    assert placed["order"]["status"] == "filled"
    state = marked(await http.get(f"{P}/accounts/{acct['id']}", headers=user.headers))
    assert state["open_positions"] == 1 and state["used_margin"] == "199.85"
    assert state["unrealised_pnl"] == "-1.6"  # closes at the bid 0.60000
    await quote(sessions, "NZD_USD", "0.57990", "0.58002")
    positions = marked(await http.get(f"{P}/accounts/{acct['id']}/positions", headers=user.headers))
    (closed,) = positions["items"]
    assert closed["status"] == "closed" and closed["exit_reason"] == "stop"
    # a stop is a market order: the bid 0.57990 less 0.4 pips, beyond the stop (a gap)
    assert closed["exit_price"] == "0.57986" and closed["exit_rate"] == "1"
    assert closed["realised_pnl"] == "-203"  # 10,000 x (0.57986 - 0.60016), no commission
    assert closed["costs"] == "2"  # 1 pip (half spread + slippage) at entry and at exit
    state = marked(await http.get(f"{P}/accounts/{acct['id']}", headers=user.headers))
    assert state["balance"] == "9797" and state["equity"] == "9797" and state["open_positions"] == 0


async def test_refusals(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    acct = await account(http, user, starting_balance="5000")
    assert acct["starting_balance_is_default"] is False
    stale = await order(http, user, acct["id"], instrument="AUD_USD", stop="0.5", target=None)
    assert stale.status_code == 422 and "fresh quote" in stale.text  # never filled at an old price
    await quote(sessions, "NZD_USD", "0.60000", "0.60012")
    for changes in (
        {"lots": "0.005"},
        {"lots": "0.013"},
        {"stop": "0.61000"},  # a long with the stop above the entry
        {"target": "0.59000"},
        {"lots": "20"},  # needs about 4,000 of margin: more than the free margin
        {"order_type": "limit"},  # no limit price
        {"order_type": "limit", "limit_price": "0.61000"},  # already reached: use a market order
        {"instrument": "EUR_SEK"},
        {"side": "sideways"},
        {"lots": 1},
        {"strategy_tag": "Bad Tag"},
    ):
        r = await order(http, user, acct["id"], **changes)
        assert r.status_code == 422, (changes, r.text)
    for body in (
        {"name": "x", "currency": "SEK"},
        {"name": "x", "currency": "USD", "starting_balance": "50"},
        {"name": " ", "currency": "USD"},
    ):
        assert (
            await http.post(f"{P}/accounts", json=body, headers=user.headers)
        ).status_code == 422


async def test_limit_orders_targets_manual_closes_levels_and_cancels(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    acct = await account(http, user)
    aid = acct["id"]
    await quote(sessions, "NZD_USD", "0.60000", "0.60012")
    limit = marked(
        await order(http, user, aid, order_type="limit", limit_price="0.59900", stop="0.59000")
    )
    assert limit["position"] is None and limit["order"]["status"] == "pending"
    other = marked(
        await order(http, user, aid, order_type="limit", limit_price="0.59500", stop="0.59000")
    )
    cancelled = marked(
        await http.post(
            f"{P}/accounts/{aid}/orders/{other['order']['id']}/cancel", headers=user.headers
        )
    )
    assert cancelled["status"] == "cancelled"
    again = await http.post(
        f"{P}/accounts/{aid}/orders/{other['order']['id']}/cancel", headers=user.headers
    )
    assert again.status_code == 409
    await quote(sessions, "NZD_USD", "0.59880", "0.59892")  # ask reaches the limit
    orders = marked(
        await http.get(
            f"{P}/accounts/{aid}/orders", params={"status": "filled"}, headers=user.headers
        )
    )
    assert [o["id"] for o in orders["items"]] == [limit["order"]["id"]]
    pos = marked(
        await http.get(
            f"{P}/accounts/{aid}/positions", params={"status": "open"}, headers=user.headers
        )
    )["items"][0]
    assert pos["entry_price"] == "0.599"  # a limit fills at its price, no slippage
    bad = await http.put(
        f"{P}/accounts/{aid}/positions/{pos['id']}/levels",
        json={"stop": "0.60500"},
        headers=user.headers,
    )
    assert bad.status_code == 422 and "closing price" in bad.text
    moved = marked(
        await http.put(
            f"{P}/accounts/{aid}/positions/{pos['id']}/levels",
            json={"stop": "0.59500", "target": "0.60100"},
            headers=user.headers,
        )
    )
    assert moved["stop"] == "0.595" and moved["target"] == "0.601"
    await quote(sessions, "NZD_USD", "0.60110", "0.60122")  # the bid reaches the target
    done = marked(
        await http.get(
            f"{P}/accounts/{aid}/positions", params={"status": "closed"}, headers=user.headers
        )
    )["items"][0]
    assert done["exit_reason"] == "target" and done["exit_price"] == "0.601"
    assert done["realised_pnl"] == "20"  # 10,000 x (0.601 - 0.599)
    await quote(sessions, "NZD_USD", "0.60200", "0.60212")
    manual = marked(await order(http, user, aid, side="short", stop="0.61000", target=None))[
        "position"
    ]
    assert manual["entry_price"] == "0.60196"  # the bid less slippage
    await quote(sessions, "NZD_USD", "0.60100", "0.60112")
    closed = marked(
        await http.post(f"{P}/accounts/{aid}/positions/{manual['id']}/close", headers=user.headers)
    )
    assert closed["exit_reason"] == "manual" and closed["exit_price"] == "0.60116"
    assert closed["realised_pnl"] == "8"
    twice = await http.post(
        f"{P}/accounts/{aid}/positions/{manual['id']}/close", headers=user.headers
    )
    assert twice.status_code == 409


async def test_a_jpy_pair_in_a_usd_account_converts_at_the_exit(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    acct = await account(http, user)
    await quote(sessions, "USD_JPY", "149.990", "150.010")
    pos = marked(
        await order(http, user, acct["id"], instrument="USD_JPY", stop="149.000", target="151.000")
    )["position"]
    assert pos["entry_price"] == "150.012"
    await quote(sessions, "USD_JPY", "151.990", "152.010")  # target 151 reached
    closed = marked(await http.get(f"{P}/accounts/{acct['id']}/positions", headers=user.headers))[
        "items"
    ][0]
    assert closed["exit_reason"] == "target" and closed["exit_rate_path"] == "1 / USD_JPY mid"
    # 10,000 x (151.000 - 150.012) = 9,880 JPY at 1 / 152.000
    assert D(closed["exit_rate"]) == (D(1) / D(152)).quantize(D("1e-15"))
    assert closed["realised_pnl"] == "65"


async def test_journal_analytics_and_closing_an_account(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    acct = await account(http, user)
    aid = acct["id"]
    await quote(sessions, "NZD_USD", "0.60000", "0.60012")
    pos = marked(await order(http, user, aid, strategy_tag="trend"))["position"]
    note = marked(
        await http.post(
            f"{P}/accounts/{aid}/journal",
            json={
                "note": "Followed the trend rule",
                "tags": ["trend", "plan"],
                "position_id": pos["id"],
            },
            headers=user.headers,
        )
    )
    assert note["tags"] == ["plan", "trend"] and note["position_id"] == pos["id"]
    marked(
        await http.post(
            f"{P}/accounts/{aid}/journal", json={"note": "General thought"}, headers=user.headers
        )
    )
    tagged = marked(
        await http.get(f"{P}/accounts/{aid}/journal", params={"tag": "trend"}, headers=user.headers)
    )
    assert [n["id"] for n in tagged["items"]] == [note["id"]]
    busy = await http.post(f"{P}/accounts/{aid}/close", headers=user.headers)
    assert busy.status_code == 409
    await quote(sessions, "NZD_USD", "0.61010", "0.61022")
    stats = marked(await http.get(f"{P}/accounts/{aid}/analytics", headers=user.headers))
    assert stats["label"] == "paper" and "never combined" in stats["series_note"]
    assert stats["overall"]["trades"] == 1 and stats["overall"]["net_pnl"] == "98.4"
    assert stats["by_strategy_tag"][0]["key"] == "trend" and stats["open_positions"] == 0
    deleted = await http.delete(f"{P}/accounts/{aid}/journal/{note['id']}", headers=user.headers)
    assert deleted.status_code == 204 and deleted.headers["X-Trading-Mode"] == "PAPER TRADING"
    closed = marked(await http.post(f"{P}/accounts/{aid}/close", headers=user.headers))
    assert closed["status"] == "closed"
    late = await order(http, user, aid)
    assert late.status_code == 409


async def test_loss_limits_and_exposure_give_warnings(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    acct = await account(http, user, starting_balance="1000")
    aid = acct["id"]
    await quote(sessions, "NZD_USD", "0.60000", "0.60012")
    marked(await order(http, user, aid, lots="0.10", stop="0.59500", target=None))
    # stop at the bid 0.59490 less slippage: 10,000 x (0.59486 - 0.60016) = -53, 5.3% of 1,000
    await quote(sessions, "NZD_USD", "0.59490", "0.59502")
    await http.get(f"{P}/accounts/{aid}", headers=user.headers)
    await quote(sessions, "NZD_USD", "0.59000", "0.59012")
    placed = marked(await order(http, user, aid, lots="0.20", stop="0.50000", target=None))
    joined = " ".join(placed["warnings"])
    assert "daily limit" in joined and "weekly limit" not in joined
    assert "Risk at the stop" in joined and "NZD exposure" in joined


async def test_another_users_paper_resources_are_404_on_every_route(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    acct = await account(http, user)
    aid = acct["id"]
    await quote(sessions, "NZD_USD", "0.60000", "0.60012")
    pos = marked(await order(http, user, aid))["position"]
    pending = marked(
        await order(http, user, aid, order_type="limit", limit_price="0.59000", stop="0.58000")
    )["order"]
    note = marked(
        await http.post(f"{P}/accounts/{aid}/journal", json={"note": "mine"}, headers=user.headers)
    )
    bob = await make_user(http, "paper-bob")
    attempts = [
        ("GET", f"{P}/accounts/{aid}", None),
        ("POST", f"{P}/accounts/{aid}/close", None),
        (
            "POST",
            f"{P}/accounts/{aid}/orders",
            {"instrument": "NZD_USD", "side": "long", "lots": "0.1", "stop": "0.5"},
        ),
        ("GET", f"{P}/accounts/{aid}/orders", None),
        ("POST", f"{P}/accounts/{aid}/orders/{pending['id']}/cancel", None),
        ("GET", f"{P}/accounts/{aid}/positions", None),
        ("POST", f"{P}/accounts/{aid}/positions/{pos['id']}/close", None),
        ("PUT", f"{P}/accounts/{aid}/positions/{pos['id']}/levels", {"stop": "0.59"}),
        ("GET", f"{P}/accounts/{aid}/journal", None),
        ("POST", f"{P}/accounts/{aid}/journal", {"note": "Bob was here"}),
        ("DELETE", f"{P}/accounts/{aid}/journal/{note['id']}", None),
        ("GET", f"{P}/accounts/{aid}/analytics", None),
    ]
    for method, path, body in attempts:
        r = await http.request(method, path, json=body, headers=bob.headers)
        assert r.status_code == 404, (method, path, r.status_code)
    assert marked(await http.get(f"{P}/accounts", headers=bob.headers))["items"] == []
    # Bob's own account cannot reach Alice's order or position through his account id either.
    own = await account(http, bob)
    for method, path in (
        ("POST", f"{P}/accounts/{own['id']}/orders/{pending['id']}/cancel"),
        ("POST", f"{P}/accounts/{own['id']}/positions/{pos['id']}/close"),
        ("DELETE", f"{P}/accounts/{own['id']}/journal/{note['id']}"),
    ):
        assert (await http.request(method, path, headers=bob.headers)).status_code == 404
    linked = await http.post(
        f"{P}/accounts/{own['id']}/journal",
        json={"note": "x", "position_id": pos["id"]},
        headers=bob.headers,
    )
    assert linked.status_code == 404
    # Alice's resources are untouched.
    still = marked(
        await http.get(
            f"{P}/accounts/{aid}/positions", params={"status": "open"}, headers=user.headers
        )
    )
    assert [p["id"] for p in still["items"]] == [pos["id"]]


async def test_paper_money_never_reaches_net_worth(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    before = (await http.get("/api/v1/net-worth", headers=user.headers)).json()
    acct = await account(http, user, starting_balance="250000")
    await quote(sessions, "NZD_USD", "0.60000", "0.60012")
    marked(await order(http, user, acct["id"]))
    after = (await http.get("/api/v1/net-worth", headers=user.headers)).json()
    for body in (before, after):  # the computation time differs; nothing else may
        body.pop("as_of")
        body.pop("freshness")
    assert after == before


def test_no_real_money_module_reads_paper_tables() -> None:
    """Static isolation (design section 11): outside the paper package, nothing imports it or
    names its tables, except the wiring (main and the worker) and the Copilot's paper tool."""
    allowed = {
        APP / "main.py",
        APP / "worker" / "tasks.py",
        # The Copilot's get_paper_performance tool (P13-T10): it reads the caller's own paper
        # series, labelled PAPER TRADING, and never combines it with real-money figures.
        APP / "ai" / "tools" / "forex.py",
    }
    paper = APP / "modules" / "forex" / "paper"
    for path in APP.rglob("*.py"):
        if paper in path.parents or path in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        assert not TABLES.search(text), path
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.modules.forex.paper"), path


async def test_the_minute_job(migrated_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    use(monkeypatch, migrated_settings.model_copy(update={"forex_enabled": False}))
    off = (await asyncio.to_thread(tasks.forex_paper_evaluate_job.apply, args=("p-off",))).get()
    assert off == {"forex": "disabled"}
    use(monkeypatch, migrated_settings.model_copy(update={"forex_enabled": True}))
    key = f"p-{datetime.now(UTC).isoformat()}"
    result = (await asyncio.to_thread(tasks.forex_paper_evaluate_job.apply, args=(key,))).get()
    assert set(result) == {"accounts", "fills_and_exits"}
    again = (await asyncio.to_thread(tasks.forex_paper_evaluate_job.apply, args=(key,))).get()
    assert again == {"skipped": True}


async def test_sign_in_and_the_flag(http: httpx.AsyncClient, migrated_settings: Settings) -> None:
    assert (await http.get(f"{P}/accounts")).status_code == 401
    off = create_app(
        migrated_settings.model_copy(update={"forex_enabled": False}),
        readiness_checks={},
        token_verifier=ah.verifier(),
    )
    transport = httpx.ASGITransport(app=off, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            someone = await make_user(client, "paper-off")
            assert (await client.get(f"{P}/accounts", headers=someone.headers)).status_code == 404
            r = await client.post(
                f"{P}/accounts", json={"name": "x", "currency": "USD"}, headers=someone.headers
            )
            assert r.status_code == 404
    finally:
        await off.state.db.dispose()


async def test_too_many_accounts(http: httpx.AsyncClient) -> None:
    many = await make_user(http, "paper-many")
    for _ in range(5):
        await account(http, many)
    r = await http.post(
        f"{P}/accounts", json={"name": "sixth", "currency": "USD"}, headers=many.headers
    )
    assert r.status_code == 409
