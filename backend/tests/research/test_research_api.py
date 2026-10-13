"""Research evidence on the real database (P12-T05): idempotent ingestion with provenance on every
item, retrieval that ignores who asks, the get_asset_research tool, and the daily job."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.worker.tasks as tasks
from app.ai.tools.base import ToolContext
from app.ai.tools.factory import build_tool_registry
from app.core.config import Settings
from app.main import create_app
from app.modules.assets.models import Asset
from app.modules.research.embedding import HashEmbedder
from app.modules.research.models import ResearchItem
from app.modules.research.service import ingest_research
from app.modules.research.sources import DemoResearchSource, EdgarSubmissionsSource, ResearchEntry
from app.modules.universe.ingestion import DemoUniverseSource, ingest
from app.worker.db import run_async
from app.worker.schedule import build_schedule
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.test_analytics_api import Book

pytestmark = [pytest.mark.integration, pytest.mark.security]
FIXTURE = Path(__file__).parent / "fixtures" / "edgar_submissions_demo.json"
AT = datetime(2026, 10, 13, tzinfo=UTC)


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    settings = migrated_settings.model_copy(update={"ai_tool_calls_per_minute": 1000})
    application = create_app(settings, readiness_checks={}, token_verifier=ah.verifier())
    sessions: async_sessionmaker[AsyncSession] = application.state.db.session_factory
    async with sessions() as s:
        await ingest(s, DemoUniverseSource())
        await ingest_research(s, DemoResearchSource(), HashEmbedder())
        application.state.symbols = dict((await s.execute(select(Asset.symbol, Asset.id))).all())
    yield application
    await application.state.db.dispose()


@pytest.fixture
def sessions(app: FastAPI) -> async_sessionmaker[AsyncSession]:
    factory: async_sessionmaker[AsyncSession] = app.state.db.session_factory
    return factory


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class Scripted:
    name, is_demo, licence_status = "scripted", True, "demo"

    def __init__(self, entries: list[ResearchEntry]) -> None:
        self.entries = entries

    def load(self) -> tuple[datetime, list[ResearchEntry]]:
        return AT, self.entries


async def get(http: httpx.AsyncClient, h: dict[str, str], **params: Any) -> dict[str, Any]:
    r = await http.get("/api/v1/research", headers=h, params=params)
    assert r.status_code == 200, r.text
    return dict(r.json())


# ---------------------------------------------------------------------------------- ingestion
async def test_every_item_has_provenance_and_ingestion_is_idempotent(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as s:
        again = await ingest_research(s, DemoResearchSource(), HashEmbedder())
        assert (again.created, again.updated, again.unchanged) == (0, 0, 16)
        rows = (await s.execute(select(ResearchItem))).scalars().all()
        for r in rows:
            assert r.source and r.licence_status and r.published_at and r.retrieved_at
            assert r.retrieved_at >= r.published_at
            assert r.embedding is not None and r.embedding_model == "hash-v1"
        linked = [r for r in rows if r.source == "demo" and r.asset_id is not None]
        assert len(linked) == 15, "every note about a DEMO instrument is linked to it"


async def test_a_changed_text_is_updated_and_re_embedded_and_unknown_symbols_are_reported(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    entry = ResearchEntry(
        "s-1", "DEMO note: first", "DEMO research. One.", "note", AT, None, "NOPE"
    )
    async with sessions() as s:
        first = await ingest_research(s, Scripted([entry]), HashEmbedder())
        assert first.created == 1 and first.unlinked == ["NOPE"]
        before = await s.scalar(select(ResearchItem).where(ResearchItem.source == "scripted"))
        assert before is not None
        old = list(before.embedding or [])
        changed = ResearchEntry("s-1", "DEMO note: first", "DEMO research. Two.", "note", AT)
        second = await ingest_research(s, Scripted([changed]), HashEmbedder())
        assert second.updated == 1
        await s.refresh(before)
        assert before.summary == "DEMO research. Two." and before.embedding != old


async def test_edgar_filings_are_stored_with_their_archive_links(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as s:
        report = await ingest_research(
            s, EdgarSubmissionsSource(FIXTURE, AT, is_demo=True), HashEmbedder()
        )
        assert report.created == 3
        rows = (
            (await s.execute(select(ResearchItem).where(ResearchItem.source == "sec_edgar")))
            .scalars()
            .all()
        )
        assert all(r.source_url and r.source_url.startswith("https://www.sec.gov/") for r in rows)
        assert {r.licence_status for r in rows} == {"demo"} and all(
            r.kind == "filing" for r in rows
        )


# ---------------------------------------------------------------------------------- retrieval
async def test_search_ranks_relevant_evidence_and_ignores_who_asks(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    q = {"q": "bond prices fall when interest rates rise"}
    alice = await get(http, two_users.alice.headers, **q)
    bob = await get(http, two_users.bob.headers, **q)
    assert alice == bob, "the same answer for everyone: no user data is used"
    top = alice["items"][0]
    assert top["symbol"] in {"DEMO-GBD", "DEMO-KTB", "DEMO-ASK"}
    assert 0 < float(top["relevance"]) <= 1
    for item in alice["items"]:
        assert item["source"] and item["licence_status"] and item["published_at"]
        assert item["retrieved_at"]
    values = [float(i["relevance"]) for i in alice["items"]]
    assert values == sorted(values, reverse=True)
    assert "not advice" in alice["notice"]


async def test_an_instruments_research_newest_first_and_search_within_it(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    geq = str(app.state.symbols["DEMO-GEQ"])
    listed = await get(http, h, asset_id=geq)
    dates = [i["published_at"] for i in listed["items"]]
    assert len(dates) == 2 and dates == sorted(dates, reverse=True)
    assert all(i["relevance"] is None and i["is_demo"] for i in listed["items"])
    within = await get(http, h, asset_id=geq, q="expense ratio costs")
    assert {i["symbol"] for i in within["items"]} == {"DEMO-GEQ"}
    assert within["items"][0]["title"] == "DEMO note: costs of the Demo Global Equity ETF"


async def test_the_query_is_validated_and_needs_a_signed_in_user(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    assert (await http.get("/api/v1/research", params={"q": "bonds"})).status_code == 401
    for params in ({}, {"q": "a"}, {"q": "bonds", "limit": "50"}, {"asset_id": "x"}):
        assert (await http.get("/api/v1/research", headers=h, params=params)).status_code == 422


# ------------------------------------------------------------------------------------ AI tool
async def call(app: FastAPI, user_id: str, arguments: dict[str, Any]) -> Any:
    registry = build_tool_registry(app.state.settings)
    sessions: async_sessionmaker[AsyncSession] = app.state.db.session_factory
    async with sessions() as session:
        return await registry.execute(
            "get_asset_research",
            arguments,
            ToolContext(uuid.UUID(user_id), session, "corr", "fake-1", "fake"),
        )


async def test_the_research_tool_returns_evidence_or_none_and_respects_visibility(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    geq = str(app.state.symbols["DEMO-GEQ"])
    found = await call(app, two_users.alice.id, {"asset_id": geq})
    assert found.ok and found.data["none"] is False and len(found.data["items"]) == 2
    assert all(i["source"] == "demo" and i["licence_status"] == "demo" for i in found.data["items"])
    private = await Book(http, two_users.alice.headers).asset()
    nothing = await call(app, two_users.alice.id, {"asset_id": private})
    assert nothing.ok and nothing.data["none"] is True and nothing.data["items"] == []
    hidden = await call(app, two_users.bob.id, {"asset_id": private})
    assert (hidden.ok, hidden.error_code) == (False, "not_found"), "Alice's own asset"


# ---------------------------------------------------------------------------------------- job
@pytest.mark.parametrize("mode", ["fake", "real"])
async def test_the_daily_job_loads_demo_research_only_with_fake_market_data(
    mode: str,
    migrated_settings: Settings,  # noqa: F811
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = migrated_settings.model_copy(update={"market_data_mode": mode})
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "run_async", lambda work: run_async(work, settings))
    day = f"research-{mode}-{uuid.uuid4()}"
    result = (await asyncio.to_thread(tasks.ingest_research_job.apply, args=(day,))).get()
    if mode == "real":
        assert result == {"demo_research": "disabled"}
        return
    assert result["source"] == "demo" and result["unchanged"] == 16
    again = (await asyncio.to_thread(tasks.ingest_research_job.apply, args=(day,))).get()
    assert again == {"skipped": True}
    async with sessions() as s:
        assert await s.scalar(text("SELECT count(*) FROM research_items WHERE source='demo'")) == 16


def test_research_is_loaded_daily_after_the_universe() -> None:
    schedule = build_schedule()
    assert schedule["research-ingest"]["task"] == "app.worker.tasks.ingest_research"
