"""Historical rates (P11-T05): past figures use their own day's rate, missing days are flagged and
never filled, and the three rate concepts stay apart."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import InvalidValueError
from app.main import create_app
from app.modules.fx.history import MAX_HISTORY_DAYS, RateConcept, rate_history
from app.modules.market_data.service import FxService
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.fx.codes import unique_code

pytestmark = pytest.mark.integration

MON = date(2026, 9, 7)  # a Monday


def code() -> str:
    return unique_code()


def at_noon(day: date) -> datetime:
    return datetime.combine(day, time(12), tzinfo=UTC)


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


async def store(raw: asyncpg.Connection, base: str, quote: str, rate: str, day: date) -> None:
    await raw.execute(
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at) VALUES ($1, $2, $3::numeric, 'hist-test', $4, $4)",
        base,
        quote,
        rate,
        at_noon(day),
    )


def test_the_three_concepts_are_distinct() -> None:
    assert {c.value for c in RateConcept} == {
        "transaction",
        "historical_valuation",
        "current_reporting",
    }


async def test_each_day_uses_its_own_rate_never_todays(
    sessions: async_sessionmaker[AsyncSession], raw: asyncpg.Connection
) -> None:
    pivot, quote = code(), code()
    for i, value in enumerate(("1.10", "1.20", "1.30", "1.40", "1.50")):  # Mon..Fri
        await store(raw, pivot, quote, value, MON + timedelta(days=i))
    await store(raw, pivot, quote, "9.99", datetime.now(UTC).date())  # "today"
    async with sessions() as s:
        points = await rate_history(s, pivot, quote, MON, MON + timedelta(days=4), pivot)
    assert [p.rate for p in points] == [
        Decimal(v) for v in ("1.10", "1.20", "1.30", "1.40", "1.50")
    ]
    assert all(not p.rate_missing and not p.from_earlier_day for p in points)
    assert Decimal("9.99") not in [p.rate for p in points]


async def test_a_weekend_carries_fridays_rate_and_says_so(
    sessions: async_sessionmaker[AsyncSession], raw: asyncpg.Connection
) -> None:
    pivot, quote = code(), code()
    friday = MON + timedelta(days=4)
    await store(raw, pivot, quote, "1.50", friday)
    async with sessions() as s:
        sat, sun = await rate_history(
            s, pivot, quote, friday + timedelta(days=1), friday + timedelta(days=2), pivot
        )
    assert sat.rate == sun.rate == Decimal("1.50")
    assert sat.from_earlier_day and sun.from_earlier_day
    assert sat.rate_timestamp is not None and sat.rate_timestamp.date() == friday


async def test_a_day_without_a_usable_rate_is_flagged_not_filled(
    sessions: async_sessionmaker[AsyncSession], raw: asyncpg.Connection
) -> None:
    pivot, quote = code(), code()
    await store(raw, pivot, quote, "1.10", MON)
    async with sessions() as s:
        points = await rate_history(
            s, pivot, quote, MON - timedelta(days=2), MON + timedelta(days=9), pivot
        )
    by_day = {p.day: p for p in points}
    assert by_day[MON - timedelta(days=1)].rate_missing  # before any rate
    assert by_day[MON - timedelta(days=1)].rate is None
    # The window is 7 x 24 hours back from the end of the day: Monday noon still serves the
    # next Sunday (6 days later) but not the Monday after (7 days 12 hours).
    assert not by_day[MON + timedelta(days=6)].rate_missing
    assert by_day[MON + timedelta(days=7)].rate_missing  # beyond the window: not substituted
    assert by_day[MON + timedelta(days=7)].rate is None


async def test_history_crosses_through_the_pivot_on_each_day(
    sessions: async_sessionmaker[AsyncSession], raw: asyncpg.Connection
) -> None:
    pivot, a, b = code(), code(), code()
    await store(raw, pivot, a, "4", MON)
    await store(raw, pivot, b, "2", MON)
    await store(raw, pivot, b, "3", MON + timedelta(days=1))
    async with sessions() as s:
        mon, tue = await rate_history(s, a, b, MON, MON + timedelta(days=1), pivot)
    assert (mon.rate, mon.path) == (Decimal("0.5"), (a, pivot, b))
    assert tue.rate == Decimal("0.75")  # Tuesday's b leg with Monday's a leg (within the window)


async def test_a_ledger_posting_uses_its_trade_dates_rate(
    sessions: async_sessionmaker[AsyncSession], raw: asyncpg.Connection
) -> None:
    pivot, quote = code(), code()
    await store(raw, pivot, quote, "1.10", MON)
    await store(raw, pivot, quote, "1.90", datetime.now(UTC).date())
    async with sessions() as s:
        posted = await FxService(s, pivot).rate_for_posting(pivot, quote, MON)
    assert posted.rate == Decimal("1.10")


async def test_ranges_are_checked(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as s:
        with pytest.raises(InvalidValueError):
            await rate_history(s, "USD", "AED", MON, MON - timedelta(days=1), "USD")
        with pytest.raises(InvalidValueError):
            await rate_history(s, "USD", "AED", MON, MON + timedelta(days=MAX_HISTORY_DAYS), "USD")


# ---------------------------------------------------------------------------------------- API
@pytest.fixture
async def api(
    migrated_settings: Settings,  # noqa: F811
    raw: asyncpg.Connection,
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient, str]]:
    pivot = code()
    await raw.execute(
        "INSERT INTO currencies (code, name, symbol, decimal_places) VALUES ($1, 'Pivot', 'P', 2)",
        pivot,
    )
    await store(raw, pivot, "AED", "3.60", MON)
    await store(raw, pivot, "AED", "3.70", MON + timedelta(days=1))
    await store(raw, pivot, "AED", "3.99", datetime.now(UTC).date() - timedelta(days=1))
    app = create_app(
        migrated_settings.model_copy(update={"fx_pivot_currency": pivot}),
        readiness_checks={},
        token_verifier=ah.verifier(),
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield app, client, pivot
    await app.state.db.dispose()
    await raw.execute("DELETE FROM currencies WHERE code = $1", pivot)


@pytest.fixture
def http(api: tuple[FastAPI, httpx.AsyncClient, str]) -> httpx.AsyncClient:
    return api[1]


async def test_the_history_endpoint_flags_missing_days(
    api: tuple[FastAPI, httpx.AsyncClient, str],
    two_users: TwoUsers,  # noqa: F811
) -> None:
    _, http, pivot = api
    h = two_users.alice.headers
    assert (await http.get("/api/v1/fx/history")).status_code == 401
    r = await http.get(
        "/api/v1/fx/history",
        headers=h,
        params={
            "base": pivot,
            "quote": "AED",
            "start": str(MON - timedelta(days=1)),
            "end": str(MON + timedelta(days=1)),
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["concept"] == "historical_valuation"
    assert [p["rate"] for p in body["points"]] == [None, "3.6", "3.7"]
    assert [p["rate_missing"] for p in body["points"]] == [True, False, False]
    assert body["missing_days"] == 1
    bad = await http.get(
        "/api/v1/fx/history",
        headers=h,
        params={"base": pivot, "quote": "ZZZ", "start": str(MON), "end": str(MON)},
    )
    assert bad.status_code == 422


async def test_converting_on_a_past_day_uses_that_days_rate(
    api: tuple[FastAPI, httpx.AsyncClient, str],
    raw: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    _, http, pivot = api
    h = two_users.alice.headers
    past = await http.post(
        "/api/v1/fx/convert",
        headers=h,
        json={"amount": {"amount": "100.00", "currency": pivot}, "to": "AED", "on": str(MON)},
    )
    assert past.status_code == 200, past.text
    body = past.json()
    assert body["converted"]["amount"] == "360.00"
    assert body["concept"] == "historical_valuation" and body["snapshot_id"] is None
    assert body["on"] == str(MON)
    today = await http.post(
        "/api/v1/fx/convert",
        headers=h,
        json={"amount": {"amount": "100.00", "currency": pivot}, "to": "AED"},
    )
    assert today.json()["converted"]["amount"] == "399.00"
    assert today.json()["concept"] == "current_reporting"
    # A day with no usable rate is not converted at all.
    long_ago = await http.post(
        "/api/v1/fx/convert",
        headers=h,
        json={"amount": {"amount": "1", "currency": pivot}, "to": "AED", "on": "2001-01-01"},
    )
    assert long_ago.status_code == 404
    both = await http.post(
        "/api/v1/fx/convert",
        headers=h,
        json={
            "amount": {"amount": "1", "currency": pivot},
            "to": "AED",
            "on": str(MON),
            "snapshot_id": str(uuid.uuid4()),
        },
    )
    assert both.status_code == 422
    audited = await raw.fetchval(
        "SELECT count(*) FROM fx_conversion_audit WHERE user_id = $1 AND snapshot_id IS NULL",
        uuid.UUID(two_users.alice.id),
    )
    assert audited == 1
