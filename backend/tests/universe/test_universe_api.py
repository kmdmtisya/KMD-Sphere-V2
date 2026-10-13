"""The investment universe on the real database (P12-T02): ingestion of the DEMO universe
(idempotent, deactivation, never two assets per symbol), GET /api/v1/universe with eligibility for
Kenyan and UAE investors, the residence country setting, and the daily job in both market-data
modes."""

import asyncio
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.worker.tasks as tasks
from app.core.config import Settings
from app.main import create_app
from app.modules.assets.models import Asset, AssetMetadata
from app.modules.universe.ingestion import (
    DemoUniverseSource,
    UniverseEntry,
    deactivate_source,
    ingest,
)
from app.modules.universe.models import UniverseInstrument
from app.worker.db import run_async
from app.worker.schedule import build_schedule
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
DEMO_SYMBOLS = 15


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    application = create_app(migrated_settings, readiness_checks={}, token_verifier=ah.verifier())
    sessions: async_sessionmaker[AsyncSession] = application.state.db.session_factory
    async with sessions() as session:
        await ingest(session, DemoUniverseSource())
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


class Source:
    """A scripted source sharing a name across runs."""

    def __init__(self, name: str, entries: Sequence[UniverseEntry]) -> None:
        self.name, self.entries = name, list(entries)
        self.is_demo, self.licence_status = True, "demo"

    def load(self) -> tuple[datetime, Sequence[UniverseEntry]]:
        return datetime(2026, 10, 13, tzinfo=UTC), self.entries


def entry(symbol: str, **changes: Any) -> UniverseEntry:
    base = UniverseEntry(symbol, f"Test {symbol} (DEMO)", "etf", "USD", 2, ("KE",))
    return replace(base, **changes)


# ---------------------------------------------------------------------------------- ingestion
async def test_the_demo_universe_is_loaded_once_as_public_catalogue_assets(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as s:
        again = await ingest(s, DemoUniverseSource())
        assert (again.created, again.updated, again.unchanged) == (0, 0, DEMO_SYMBOLS)
        rows = (
            await s.execute(
                select(Asset, UniverseInstrument).join(
                    UniverseInstrument, UniverseInstrument.asset_id == Asset.id
                )
            )
        ).all()
        demo = [(a, u) for a, u in rows if u.source == "demo"]
        assert len(demo) == DEMO_SYMBOLS
        for asset, row in demo:
            assert asset.owner_user_id is None, "reference data, no owner"
            assert asset.external_provider == "demo" and (asset.symbol or "").startswith("DEMO-")
            assert "(DEMO)" in asset.name and row.is_demo and row.licence_status == "demo"
        sectors: dict[str | None, Any] = dict(
            (
                await s.execute(
                    select(Asset.symbol, AssetMetadata.value)
                    .join(AssetMetadata, AssetMetadata.asset_id == Asset.id)
                    .where(AssetMetadata.key == "sector", Asset.external_provider == "demo")
                )
            ).all()
        )
        # A sector only where the asset class has one (stocks and REITs).
        assert sectors == {"DEMO-KEN": "Telecommunications", "DEMO-KBK": "Banks",
                           "DEMO-KRT": "Real Estate", "DEMO-UAE": "Real Estate"}  # fmt: skip


async def test_an_instrument_the_source_drops_is_deactivated_not_deleted(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    name = f"t{uuid.uuid4().hex[:8]}"
    async with sessions() as s:
        first = await ingest(s, Source(name, [entry("X1"), entry("X2")]))
        assert first.created == 2
        changed = await ingest(s, Source(name, [entry("X1", risk_level=3)]))
        assert (changed.updated, changed.deactivated) == (1, 1)
        back = await ingest(s, Source(name, [entry("X1", risk_level=3), entry("X2")]))
        assert back.updated == 1, "X2 is active again"
        count = await s.scalar(
            select(func.count()).select_from(Asset).where(Asset.external_provider == name)
        )
        assert count == 2, "never a second asset for the same symbol"
        skipped = await ingest(s, Source(name, [entry("X1", currency="EUR"), entry("X3",
                                                asset_class="nonsense")]))  # fmt: skip
        assert len(skipped.skipped) == 2
        assert await deactivate_source(s, name) >= 1
        active = await s.scalar(
            select(func.count())
            .select_from(UniverseInstrument)
            .where(UniverseInstrument.source == name, UniverseInstrument.is_active.is_(True))
        )
        assert active == 0


# --------------------------------------------------------------------------------------- API
async def investor(
    http: httpx.AsyncClient, h: dict[str, str], country: str | None, tolerance: str | None,
    horizon: int | None,
) -> None:  # fmt: skip
    r = await http.patch("/api/v1/me/preferences", headers=h, json={"residence_country": country})
    assert r.status_code == 200 and r.json()["residence_country"] == country, r.text
    if tolerance is not None:
        body = {"risk_tolerance": tolerance, "horizon_years": horizon}
        r = await http.post("/api/v1/risk-profiles", headers=h, json=body)
        assert r.status_code == 201, r.text


async def universe(http: httpx.AsyncClient, h: dict[str, str], **params: Any) -> dict[str, Any]:
    r = await http.get("/api/v1/universe", headers=h, params=params)
    assert r.status_code == 200, r.text
    return dict(r.json())


def eligible(body: dict[str, Any]) -> set[str]:
    return {i["symbol"] for i in body["items"] if i["eligibility"]["eligible"]}


async def test_without_a_country_or_risk_profile_nothing_is_eligible_and_it_says_why(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    body = await universe(http, two_users.alice.headers)
    assert body["total"] == DEMO_SYMBOLS and body["eligible"] == 0
    assert body["investor"] == {"residence_country": None, "risk_tolerance": None,
                                "horizon_years": None}  # fmt: skip
    first = body["items"][0]
    reasons = {r["rule"]: r for r in first["eligibility"]["rules"]}
    assert reasons["jurisdiction"]["reason"] == "No country of residence is set."
    assert reasons["jurisdiction"]["legally_reviewed"] is False
    assert reasons["risk"]["reason"] == "No risk profile is set."
    assert "not a recommendation" in body["notice"]
    assert "not been legally reviewed" in body["jurisdiction_notice"]


async def test_a_balanced_kenyan_investor_sees_kenyan_and_global_instruments_within_risk(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    await investor(http, h, "KE", "balanced", 3)
    body = await universe(http, h)
    assert eligible(body) == {"DEMO-KRT", "DEMO-KTB", "DEMO-KMM", "DEMO-KFD", "DEMO-GBD",
                              "DEMO-GLD"}  # fmt: skip
    assert body["eligible"] == 6
    only = await universe(http, h, eligible_only="true")
    assert {i["symbol"] for i in only["items"]} == eligible(body) and only["total"] == 15
    fd = next(i for i in body["items"] if i["symbol"] == "DEMO-KFD")
    assert fd["liquidity"] == "term" and fd["minimum_investment"] == {"amount": "100000.00",
                                                                     "currency": "KES"}  # fmt: skip
    assert fd["is_demo"] is True and fd["licence_status"] == "demo"
    bonds = await universe(http, h, asset_class="bond")
    assert {i["symbol"] for i in bonds["items"]} == {"DEMO-KTB", "DEMO-ASK"}


async def test_a_growth_uae_investor_without_a_horizon_cannot_tie_money_up_in_property(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.bob.headers
    await investor(http, h, "AE", "growth", None)
    body = await universe(http, h)
    assert eligible(body) == {"DEMO-UAE", "DEMO-ASK", "DEMO-AMM", "DEMO-GEQ", "DEMO-GBD",
                              "DEMO-GLD"}  # fmt: skip
    prop = next(i for i in body["items"] if i["symbol"] == "DEMO-APF")
    failed = [r["reason"] for r in prop["eligibility"]["rules"] if not r["passed"]]
    assert failed == ["illiquid liquidity needs a stated horizon of at least 5 years."]


async def test_the_residence_country_is_validated_and_can_be_cleared(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    for bad in ("ke", "KEN", "K1"):
        r = await http.patch("/api/v1/me/preferences", headers=h, json={"residence_country": bad})
        assert r.status_code == 422, bad
    await investor(http, h, "KE", None, None)
    await investor(http, h, None, None, None)
    assert (await http.get("/api/v1/me", headers=h)).json()["residence_country"] is None


async def test_the_universe_needs_a_signed_in_user_and_a_valid_filter(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    assert (await http.get("/api/v1/universe")).status_code == 401
    r = await http.get("/api/v1/universe", headers=two_users.alice.headers,
                       params={"asset_class": "DROP TABLE"})  # fmt: skip
    assert r.status_code == 422


# ---------------------------------------------------------------------------------------- job
@pytest.mark.parametrize("mode", ["fake", "real"])
async def test_the_daily_job_loads_the_demo_universe_only_with_fake_market_data(
    mode: str,
    migrated_settings: Settings,  # noqa: F811
    sessions: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = migrated_settings.model_copy(update={"market_data_mode": mode})
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "run_async", lambda work: run_async(work, settings))
    day = f"universe-{mode}-{uuid.uuid4()}"
    result = (await asyncio.to_thread(tasks.ingest_universe_job.apply, args=(day,))).get()
    again = (await asyncio.to_thread(tasks.ingest_universe_job.apply, args=(day,))).get()
    assert again == {"skipped": True}
    async with sessions() as s:
        active = await s.scalar(
            text("SELECT count(*) FROM universe_instruments WHERE source = 'demo' AND is_active")
        )
    if mode == "fake":
        assert result["source"] == "demo" and active == DEMO_SYMBOLS
    else:
        assert result["demo_universe"] == "disabled" and active == 0
        async with sessions() as s:  # restore for the other tests
            await ingest(s, DemoUniverseSource())


def test_the_universe_is_loaded_daily() -> None:
    entry_ = build_schedule()["universe-ingest"]
    assert entry_["task"] == "app.worker.tasks.ingest_universe"
