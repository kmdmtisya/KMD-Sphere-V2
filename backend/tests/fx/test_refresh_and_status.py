"""Reporting-currency rates (P11-T03): provider order and fallback, batch refresh, one refresh per
window, honest status, the cached board, and the /api/v1/fx endpoints."""

import secrets
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.cache import MemoryCacheStore
from app.core.config import Settings
from app.main import create_app
from app.modules.fx.board import RateBoard, invalidate
from app.modules.fx.refresh import (
    refresh_once_per_window,
    refresh_rates,
    window_key,
)
from app.modules.fx.status import RateStatus, StatusPolicy
from app.modules.market_data.providers.errors import (
    ProviderAuthError,
    ProviderDataError,
    ProviderError,
    ProviderUnavailable,
    UnsupportedKind,
)
from app.modules.market_data.providers.models import (
    AssetKind,
    FxBatch,
    FxQuote,
    PricePoint,
    PriceQuote,
    Provenance,
)
from app.modules.market_data.providers.registry import MarketProviders
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.fx.codes import unique_code

pytestmark = pytest.mark.integration

LAUNCH = ["AED", "AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "KES", "USD", "ZAR"]
POLICY = StatusPolicy.from_settings(Settings())


class StubFx:
    """An FX source with fixed rates against any base; counts its requests."""

    supported_kinds: frozenset[AssetKind] = frozenset()

    def __init__(
        self,
        name: str,
        rates: dict[str, Decimal],
        *,
        fail: ProviderError | None = None,
        published: datetime | None = None,
    ) -> None:
        self.name = name
        self.rates = rates
        self.fail = fail
        self.published = published or datetime.now(UTC) - timedelta(minutes=5)
        self.requests = 0

    def _q(self, base: str, quote: str) -> FxQuote:
        return FxQuote(
            base,
            quote,
            self.rates[quote],
            Provenance(self.name, self.published, max(self.published, datetime.now(UTC))),
        )

    async def get_fx_rates(self, base: str, quotes: list[str]) -> FxBatch:
        self.requests += 1
        if self.fail is not None:
            raise self.fail
        return FxBatch(
            [self._q(base, q) for q in quotes if q in self.rates],
            [q for q in quotes if q not in self.rates],
        )

    async def get_fx_rate(self, base: str, quote: str) -> FxQuote:
        batch = await self.get_fx_rates(base, [quote])
        if not batch.rates:
            raise UnsupportedKind(quote)
        return batch.rates[0]

    async def get_fx_history(self, base: str, quote: str, start: date, end: date) -> list[FxQuote]:
        raise UnsupportedKind("no history")

    async def get_quote(self, symbol: str, kind: AssetKind) -> PriceQuote:
        raise UnsupportedKind("fx only")

    async def get_history(
        self, symbol: str, kind: AssetKind, start: date, end: date
    ) -> list[PricePoint]:
        raise UnsupportedKind("fx only")


def pivot_code() -> str:
    return unique_code()


def far_window() -> datetime:
    """A moment in a refresh window no other test uses (windows are claimed in the database)."""
    return datetime(2031, 1, 1, tzinfo=UTC) + timedelta(minutes=15 * secrets.randbelow(10**7))


def ecb_like(pivot: str) -> StubFx:
    return StubFx(
        f"ecb-{uuid.uuid4().hex[:6]}",
        {c: Decimal("1.1") for c in LAUNCH if c not in ("AED", "KES") and c != pivot},
    )


def commercial(pivot: str) -> StubFx:
    return StubFx(f"era-{uuid.uuid4().hex[:6]}", {c: Decimal("3.5") for c in LAUNCH if c != pivot})


@pytest.fixture
async def sessions(migrated_settings: Settings) -> AsyncIterator[async_sessionmaker[AsyncSession]]:  # noqa: F811
    app = create_app(migrated_settings, readiness_checks={})
    yield app.state.db.session_factory
    await app.state.db.dispose()


@pytest.fixture
async def raw(migrated_settings: Settings) -> AsyncIterator[asyncpg.Connection]:  # noqa: F811
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    yield conn
    await conn.close()


# ------------------------------------------------------------------------------------ status
@pytest.mark.parametrize(
    ("provider", "age", "status"),
    [
        ("ecb", timedelta(hours=20), RateStatus.CURRENT),
        ("ecb", timedelta(hours=36), RateStatus.CURRENT),
        ("ecb", timedelta(hours=37), RateStatus.CACHED),
        ("ecb", timedelta(hours=72), RateStatus.CACHED),
        ("ecb", timedelta(hours=73), RateStatus.STALE),
        ("exchangerate_api", timedelta(minutes=90), RateStatus.CURRENT),
        ("exchangerate_api", timedelta(hours=3), RateStatus.CACHED),
        ("exchangerate_api", timedelta(hours=25), RateStatus.STALE),
        ("someone-new", timedelta(hours=3), RateStatus.CACHED),
    ],
)
def test_status_follows_the_providers_rhythm(
    provider: str, age: timedelta, status: RateStatus
) -> None:
    now = datetime(2026, 10, 12, 12, tzinfo=UTC)
    assert POLICY.status(provider, now - age, now) is status


def test_windows_are_fixed_slices_of_the_clock() -> None:
    assert window_key(datetime(2026, 10, 12, 21, 44, 59, tzinfo=UTC), 15) == "2026-10-12T21:30"
    assert window_key(datetime(2026, 10, 12, 21, 45, tzinfo=UTC), 15) == "2026-10-12T21:45"
    assert window_key(datetime(2026, 10, 12, 21, 59, tzinfo=UTC), 60) == "2026-10-12T21:00"


def test_the_refresh_schedule_fits_the_commercial_quota() -> None:
    """One request per provider per window, a window every 15 minutes, a 31-day month."""
    s = Settings()
    worst_month = (60 // s.fx_refresh_window_minutes) * 24 * 31
    assert worst_month <= s.fx_monthly_request_budget
    assert worst_month == 2976


# ----------------------------------------------------------------------------------- refresh
async def test_the_commercial_provider_supplies_what_the_ecb_does_not(
    sessions: async_sessionmaker[AsyncSession], raw: asyncpg.Connection
) -> None:
    pivot = pivot_code()
    ecb, era = ecb_like(pivot), commercial(pivot)
    async with sessions() as s:
        outcome = await refresh_rates(s, (ecb, era), pivot, LAUNCH)
    first, second = outcome.attempts
    assert first.provider == ecb.name and "AED" in first.unsupported and "KES" in first.unsupported
    assert second.supplied == ["AED", "KES"], "the fallback is asked only for what is missing"
    assert outcome.missing == []
    assert (ecb.requests, era.requests) == (1, 1), "one batch request per provider"
    rows = await raw.fetch(
        "SELECT quote_currency, provider, rate_type FROM fx_rates WHERE base_currency = $1",
        pivot,
    )
    assert {r["quote_currency"] for r in rows} == set(LAUNCH)
    assert {r["provider"] for r in rows if r["quote_currency"] in ("AED", "KES")} == {era.name}
    assert {r["rate_type"] for r in rows} == {"indicative"}


async def test_when_the_primary_is_down_the_fallback_supplies_everything(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pivot = pivot_code()
    down = StubFx("ecb-down", {}, fail=ProviderUnavailable("down"))
    era = commercial(pivot)
    async with sessions() as s:
        outcome = await refresh_rates(s, (down, era), pivot, LAUNCH)
    assert outcome.attempts[0].error == "ProviderUnavailable"
    assert len(outcome.attempts[1].supplied) == len(LAUNCH)
    assert not outcome.every_provider_failed


async def test_bad_data_or_a_refused_key_moves_on_and_stores_nothing_from_that_provider(
    sessions: async_sessionmaker[AsyncSession], raw: asyncpg.Connection
) -> None:
    pivot = pivot_code()
    for failure in (ProviderDataError("garbage"), ProviderAuthError("key")):
        bad = StubFx(f"bad-{uuid.uuid4().hex[:6]}", {}, fail=failure)
        async with sessions() as s:
            outcome = await refresh_rates(s, (bad, commercial(pivot)), pivot, LAUNCH)
        assert outcome.attempts[0].error == type(failure).__name__
        assert (
            await raw.fetchval("SELECT count(*) FROM fx_rates WHERE provider = $1", bad.name) == 0
        )


async def test_a_currency_no_provider_has_stays_missing(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pivot = pivot_code()
    async with sessions() as s:
        outcome = await refresh_rates(s, (ecb_like(pivot),), pivot, LAUNCH)
    assert outcome.missing == ["AED", "KES"]


async def test_one_refresh_per_window_whoever_asks(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pivot = pivot_code()
    era = commercial(pivot)
    now = far_window()
    first = await refresh_once_per_window(sessions, (era,), pivot, now, 15)
    second = await refresh_once_per_window(sessions, (era,), pivot, now + timedelta(minutes=5), 15)
    assert first.ran and not second.ran
    assert era.requests == 1, "the second request did not reach the provider"
    third = await refresh_once_per_window(sessions, (era,), pivot, now + timedelta(minutes=15), 15)
    assert third.ran and era.requests == 2


async def test_when_every_provider_fails_the_window_is_released_for_a_retry(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pivot = pivot_code()
    down = StubFx("down", {}, fail=ProviderUnavailable("down"))
    now = far_window()
    with pytest.raises(ProviderUnavailable):
        await refresh_once_per_window(sessions, (down,), pivot, now, 15)
    era = commercial(pivot)
    retry = await refresh_once_per_window(sessions, (era,), pivot, now, 15)
    assert retry.ran and era.requests == 1


# ------------------------------------------------------------------------------------- board
async def test_the_board_labels_each_rate_honestly_even_from_the_cache(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pivot = pivot_code()
    published = datetime.now(UTC) - timedelta(minutes=30)
    era = StubFx(
        f"exchangerate_api-{uuid.uuid4().hex[:4]}", {"EUR": Decimal("0.92")}, published=published
    )
    async with sessions() as s:
        await refresh_rates(s, (era,), pivot, ["EUR"])
    cache = MemoryCacheStore()
    async with sessions() as s:
        board = RateBoard(s, POLICY, cache, 60)
        now_lines = {line.currency: line for line in await board.lines(pivot, datetime.now(UTC))}
        later = datetime.now(UTC) + timedelta(hours=3)
        later_lines = {line.currency: line for line in await board.lines(pivot, later)}
    assert now_lines["EUR"].status is RateStatus.CURRENT
    assert now_lines["EUR"].rate == Decimal("0.92")
    assert later_lines["EUR"].status is RateStatus.CACHED, "a cached row is never shown as current"
    assert later_lines["EUR"].age_seconds is not None and later_lines["EUR"].age_seconds >= 3 * 3600
    assert now_lines["KES"].status is RateStatus.UNAVAILABLE and now_lines["KES"].rate is None
    stored_keys = cache.keys()
    assert any(k.startswith("fx:board:") for k in stored_keys)


async def test_a_refresh_invalidates_the_cached_board(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    pivot = pivot_code()
    cache = MemoryCacheStore()
    async with sessions() as s:
        board = RateBoard(s, POLICY, cache, 600)
        before = {line.currency: line for line in await board.lines(pivot, datetime.now(UTC))}
        await refresh_rates(s, (commercial(pivot),), pivot, ["EUR"])
        stale_view = {line.currency: line for line in await board.lines(pivot, datetime.now(UTC))}
        await invalidate(cache)
        after = {line.currency: line for line in await board.lines(pivot, datetime.now(UTC))}
    assert before["EUR"].status is RateStatus.UNAVAILABLE
    assert stale_view["EUR"].status is RateStatus.UNAVAILABLE, "served from the cache"
    assert after["EUR"].status is RateStatus.CURRENT


# --------------------------------------------------------------------------------------- API
@pytest.fixture
async def api(migrated_settings: Settings) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:  # noqa: F811
    settings = migrated_settings.model_copy(
        update={
            "rate_limit_enabled": True,
            "rate_limit_storage": "memory",
            "rate_limit_user_requests": 1000,
            "rate_limit_ip_requests": 1000,
            "fx_refresh_per_user_per_hour": 2,
            "fx_pivot_currency": pivot_code(),
        }
    )
    app = create_app(settings, readiness_checks={}, token_verifier=ah.verifier())
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield app, client
    await app.state.db.dispose()


@pytest.fixture
async def http(api: tuple[FastAPI, httpx.AsyncClient]) -> httpx.AsyncClient:
    return api[1]


async def test_the_fx_routes_need_a_signed_in_user(http: httpx.AsyncClient) -> None:
    assert (await http.get("/api/v1/fx/status")).status_code == 401
    assert (await http.post("/api/v1/fx/refresh")).status_code == 401


async def test_refresh_then_status_report_provider_type_time_and_status(
    api: tuple[FastAPI, httpx.AsyncClient],
    two_users: TwoUsers,  # noqa: F811
) -> None:
    app, http = api
    pivot = app.state.settings.fx_pivot_currency
    ecb, era = ecb_like(pivot), commercial(pivot)
    app.state.market_providers = MarketProviders({}, None, (ecb, era))
    r = await http.post("/api/v1/fx/refresh", headers=two_users.alice.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["refreshed"] is True and body["missing"] == []
    assert [a["provider"] for a in body["attempts"]] == [ecb.name, era.name]
    lines = {line["currency"]: line for line in body["status"]["rates"]}
    assert set(lines) == set(LAUNCH)  # the pivot itself is not a line (it is a QXX code)
    assert lines["AED"]["provider"] == era.name
    assert lines["AED"]["rate"] == "3.5" and isinstance(lines["AED"]["rate"], str)
    for line in lines.values():
        assert line["status"] == "current"
        assert line["rate_type"] == "indicative"
        assert line["rate_timestamp"] and line["retrieved_at"]
    status = await http.get("/api/v1/fx/status", headers=two_users.bob.headers)
    assert status.json()["pivot_currency"] == pivot


async def test_a_second_refresh_in_the_window_calls_no_provider(
    api: tuple[FastAPI, httpx.AsyncClient],
    two_users: TwoUsers,  # noqa: F811
) -> None:
    app, http = api
    pivot = app.state.settings.fx_pivot_currency
    era = commercial(pivot)
    app.state.market_providers = MarketProviders({}, None, (era,))
    await http.post("/api/v1/fx/refresh", headers=two_users.alice.headers)
    again = await http.post("/api/v1/fx/refresh", headers=two_users.bob.headers)
    assert again.json()["refreshed"] is False
    assert era.requests == 1


async def test_refresh_is_limited_per_user(
    api: tuple[FastAPI, httpx.AsyncClient],
    two_users: TwoUsers,  # noqa: F811
) -> None:
    app, http = api
    app.state.market_providers = MarketProviders({}, None, (commercial("USD"),))
    for _ in range(2):
        assert (
            await http.post("/api/v1/fx/refresh", headers=two_users.alice.headers)
        ).status_code == 200
    limited = await http.post("/api/v1/fx/refresh", headers=two_users.alice.headers)
    assert limited.status_code == 429 and int(limited.headers["retry-after"]) > 0
    assert (await http.post("/api/v1/fx/refresh", headers=two_users.bob.headers)).status_code == 200


async def test_when_every_provider_fails_the_last_good_rate_is_shown_with_its_age(
    api: tuple[FastAPI, httpx.AsyncClient],
    sessions: async_sessionmaker[AsyncSession],
    two_users: TwoUsers,  # noqa: F811
) -> None:
    app, http = api
    pivot = app.state.settings.fx_pivot_currency
    old = StubFx(
        f"exchangerate_api-{uuid.uuid4().hex[:4]}",
        {"EUR": Decimal("0.91")},
        published=datetime.now(UTC) - timedelta(hours=30),
    )
    async with sessions() as s:
        await refresh_rates(s, (old,), pivot, ["EUR"])
    app.state.market_providers = MarketProviders(
        {},
        None,
        (
            StubFx("a", {}, fail=ProviderUnavailable("x")),
            StubFx("b", {}, fail=ProviderUnavailable("y")),
        ),
    )
    r = await http.post("/api/v1/fx/refresh", headers=two_users.alice.headers)
    body = r.json()
    assert r.status_code == 200 and body["refreshed"] is False
    assert all(a["failed"] for a in body["attempts"])
    lines = {line["currency"]: line for line in body["status"]["rates"]}
    assert lines["EUR"]["rate"] == "0.91"
    assert lines["EUR"]["status"] == "stale"
    assert lines["EUR"]["age_seconds"] >= 30 * 3600
    assert lines["KES"]["status"] == "unavailable" and lines["KES"]["rate"] is None
