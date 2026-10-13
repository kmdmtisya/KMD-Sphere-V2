"""The opportunity pipeline end to end (P12-T06) on the real database with a scripted model:
deterministic selection, facts with evidence and data times, a validated model explanation (or
the template), runs stored unchanged and audited, owner-scoped reads, and the daily limit."""

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.providers.fake import FakeLlmProvider, text_reply
from app.ai.providers.models import ChatRequest, ChatResponse
from app.core.config import Settings
from app.main import create_app
from app.modules.assets.models import Asset
from app.modules.research.embedding import HashEmbedder
from app.modules.research.service import ingest_research
from app.modules.research.sources import DemoResearchSource
from app.modules.universe.ingestion import DemoUniverseSource, ingest
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, assert_hidden_from, make_user, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.test_analytics_api import Book, m

pytestmark = [pytest.mark.integration, pytest.mark.security]
RUNS = "/api/v1/ai/opportunities"
TODAY = datetime.now(UTC).date()
LLM = FakeLlmProvider()


async def closes(s: AsyncSession, asset_id: uuid.UUID, currency: str) -> None:
    price = Decimal(100)
    for i in range(400, -1, -1):
        on = TODAY - timedelta(days=i)
        if on.weekday() >= 5:
            continue
        price = price * Decimal("1.0004") * (Decimal("1.006") if i % 2 else Decimal("0.995"))
        at = datetime.combine(on, time(21), UTC)
        await s.execute(
            text(
                "INSERT INTO market_prices (asset_id, price, currency, price_type, provider, "
                "as_of, retrieved_at) VALUES (:a, :p, :c, 'close', 'fake', :t, :t)"
            ),
            {"a": asset_id, "p": price.quantize(Decimal("0.0001")), "c": currency, "t": at},
        )


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    settings = migrated_settings.model_copy(update={"ai_opportunity_runs_per_day": 3})
    application = create_app(settings, readiness_checks={}, token_verifier=ah.verifier(), llm=LLM)
    sessions: async_sessionmaker[AsyncSession] = application.state.db.session_factory
    async with sessions() as s:
        await ingest(s, DemoUniverseSource())
        await ingest_research(s, DemoResearchSource(), HashEmbedder())
        ids = dict((await s.execute(select(Asset.symbol, Asset.id))).all())
        for symbol in ("DEMO-GBD", "DEMO-GLD", "DEMO-GEQ", "DEMO-KRT"):
            await closes(s, ids[symbol], "KES" if symbol == "DEMO-KRT" else "USD")
        await s.commit()
    yield application
    await application.state.db.dispose()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    LLM.reset()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def raw(migrated_settings: Settings) -> AsyncIterator[asyncpg.Connection]:  # noqa: F811
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    yield conn
    await conn.close()


def echo(request: ChatRequest) -> ChatResponse:
    """A well-behaved model: explains each candidate in words, citing its first evidence."""
    candidates = json.loads(request.messages[-1].content)["candidates"]
    return text_reply(
        json.dumps(
            {
                "opportunities": [
                    {
                        "asset_id": c["asset_id"],
                        "thesis": f"{c['name']} passed the rules.",
                        "why_surfaced": "Its measured characteristics scored well.",
                        "key_risks": ["Its price can fall."],
                        "assumptions": ["Scores describe the past."],
                        "evidence_ids": [e["id"] for e in c["evidence"][:1]],
                    }
                    for c in candidates
                ]
            }
        )
    )


async def investor(http: httpx.AsyncClient, h: dict[str, str]) -> str:
    await http.patch("/api/v1/me/preferences", headers=h, json={"residence_country": "KE"})
    await http.post(
        "/api/v1/risk-profiles", headers=h, json={"risk_tolerance": "balanced", "horizon_years": 5}
    )
    book = Book(http, h)
    pid = await book.portfolio()
    stock = await book.asset(country="US", metadata={"sector": "Tech"})
    await book.post(pid, "DEPOSIT", gross_amount=m("10000.00"))
    await book.post(pid, "BUY", asset_id=stock, quantity="90", unit_price=m("100"))
    await book.value(pid, stock, "9000.00")
    return pid


async def run(http: httpx.AsyncClient, h: dict[str, str], **body: Any) -> dict[str, Any]:
    r = await http.post(RUNS, headers=h, json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


async def test_a_run_selects_explains_stores_and_audits(
    http: httpx.AsyncClient,
    raw: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    pid = await investor(http, h)
    LLM.queue(echo)
    body = await run(http, h, portfolio_id=pid)
    assert body["explanation_source"] == "model" and body["model"] == "fake-1"
    assert body["amount"] == m("500.00"), "5% of the portfolio by default"
    assert "not a recommendation" in body["notice"]
    opps = body["opportunities"]
    assert 1 <= len(opps) <= 3 and [o["rank"] for o in opps] == list(range(1, len(opps) + 1))
    for o in opps:
        f = o["facts"]
        assert o["is_trade"] is False and o["actions"] == ["research", "compare", "simulate"]
        assert f["score"]["score"] is not None and f["prices_as_of"] and f["universe_as_of"]
        assert (
            f["research_horizon"]["minimum_years"] >= 1
            and "Assumed" in f["research_horizon"]["basis"]
        )
        assert f["compatibility"]["verdict"] in {"fits", "caution"}
        assert "total_value" not in f["compatibility"]["before"], "no amounts go to the model"
        for e in f["evidence"]:
            assert e["source"] and e["licence_status"] and e["published_at"]
        assert o["explanation"]["key_risks"]
        assert set(map(str, o["explanation"]["evidence_ids"])) <= {e["id"] for e in f["evidence"]}
    sent = LLM.requests[0].messages[-1].content
    assert two_users.alice.id not in sent and "10000" not in sent
    stored = (await http.get(f"{RUNS}/runs/{body['id']}", headers=h)).json()
    assert stored == body
    listed = (await http.get(f"{RUNS}/runs", headers=h)).json()
    assert [r["id"] for r in listed] == [body["id"]]
    audit = await raw.fetchrow(
        "SELECT details FROM audit_events WHERE action = 'ai.opportunities.run' "
        "AND resource_id = $1",
        body["id"],
    )
    assert audit is not None
    details = json.loads(audit["details"])
    assert details["opportunities"] == len(opps) and details["explanation_source"] == "model"


async def test_an_unacceptable_explanation_is_replaced_by_the_template(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    await investor(http, h)
    forecast = text_reply('{"opportunities": []}')
    LLM.queue(forecast, forecast)
    body = await run(http, h)
    assert body["explanation_source"] == "template" and body["portfolio_id"] is None
    assert body["opportunities"] and all(
        o["explanation_source"] == "template" for o in body["opportunities"]
    )
    assert "out of 100" in body["opportunities"][0]["explanation"]["thesis"]


async def test_runs_are_kept_unchanged_and_private(
    app: FastAPI,
    http: httpx.AsyncClient,
    raw: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    await investor(http, h)
    LLM.queue(echo)
    body = await run(http, h)
    await assert_hidden_from(http, two_users.bob, "GET", f"{RUNS}/runs/{body['id']}")
    assert (await http.get(f"{RUNS}/runs", headers=two_users.bob.headers)).json() == []
    with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
        await raw.execute(
            "UPDATE opportunity_runs SET explanation_source = 'model' WHERE id = $1",
            uuid.UUID(body["id"]),
        )


async def test_bob_cannot_read_alices_opportunity_run(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    await investor(http, two_users.alice.headers)
    LLM.queue(echo)
    body = await run(http, two_users.alice.headers)
    await assert_hidden_from(http, two_users.bob, "GET", f"{RUNS}/runs/{body['id']}")


async def test_nothing_eligible_gives_an_empty_run_and_the_daily_limit_holds(
    http: httpx.AsyncClient,
) -> None:
    carol = await make_user(http, "carol")
    for _ in range(3):
        body = await run(http, carol.headers)
        assert body["opportunities"] == [] and body["investor"]["residence_country"] is None
    limited = await http.post(RUNS, headers=carol.headers, json={})
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) > 0


async def test_the_request_is_validated(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    assert (await http.post(RUNS, json={})).status_code == 401
    bad = [{"amount": m("100.00")}, {"limit": 6}, {"user_id": two_users.bob.id}]
    for body in bad:
        assert (await http.post(RUNS, headers=h, json=body)).status_code == 422, body
    foreign = await http.post(RUNS, headers=h, json={"portfolio_id": str(uuid.uuid4())})
    assert foreign.status_code == 404
