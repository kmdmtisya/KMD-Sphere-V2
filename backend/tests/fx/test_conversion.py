"""The reporting-conversion engine (P11-T04): direction, inverse and cross rates with their path,
per-currency precision with one half-up rounding, snapshots, and the conversion APIs. Results are
checked against an independent computation in exact fractions."""

import secrets
import string
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.modules.fx.snapshot import Leg, Snapshot, SnapshotService, convert
from app.modules.fx.status import RateStatus, StatusPolicy
from app.modules.market_data.fx import FxRateUnavailable
from app.modules.market_data.service import FxService
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)
POLICY = StatusPolicy.from_settings(Settings())


def leg(currency: str, rate: str, *, provider: str = "exchangerate_api", age_h: float = 1) -> Leg:
    stamp = NOW - timedelta(hours=age_h)
    return Leg(currency, Decimal(rate), provider, "indicative", stamp, stamp)


SNAP = Snapshot(
    uuid.uuid4(),
    "USD",
    NOW,
    {
        "AED": leg("AED", "3.6725"),
        "KES": leg("KES", "129.15"),
        "JPY": leg("JPY", "149.83"),
        "EUR": leg("EUR", "0.9216", provider="ecb", age_h=50),
    },
)


def exact(amount: str, rate: Fraction, places: int) -> Decimal:
    """Independent reference: exact rational product, rounded half-up."""
    value = Fraction(Decimal(amount)) * rate
    scaled = value * 10**places
    floor = scaled.numerator // scaled.denominator
    rest = scaled - floor
    rounded = (
        floor + (1 if rest >= Fraction(1, 2) else 0)
        if value >= 0
        else -(
            (-scaled).numerator // (-scaled).denominator
            + (
                1
                if (-scaled) - (-scaled).numerator // (-scaled).denominator >= Fraction(1, 2)
                else 0
            )
        )
    )
    return Decimal(rounded).scaleb(-places)


# ---------------------------------------------------------------------------- rates in a snapshot
def test_identity_direct_inverse_and_cross_rates() -> None:
    assert SNAP.rate("AED", "AED").rate == 1 and SNAP.rate("AED", "AED").path is None
    direct = SNAP.rate("USD", "AED")
    assert (direct.rate, direct.path) == (Decimal("3.6725"), None)
    inverse = SNAP.rate("AED", "USD")
    assert inverse.path is None
    assert abs(Fraction(inverse.rate) - 1 / Fraction("3.6725")) < Fraction(1, 10**45)
    cross = SNAP.rate("AED", "KES")
    assert cross.path == ("AED", "USD", "KES")
    assert abs(Fraction(cross.rate) - Fraction("129.15") / Fraction("3.6725")) < Fraction(1, 10**45)
    assert [g.currency for g in cross.legs] == ["AED", "KES"]


def test_a_derived_rate_is_as_old_and_as_fresh_as_its_weakest_leg() -> None:
    cross = SNAP.rate("EUR", "KES")
    assert cross.rate_timestamp == NOW - timedelta(hours=50)
    # The ECB leg is 50 hours old: past its 36-hour current window, so the cross rate is cached.
    assert cross.status(POLICY, NOW) is RateStatus.CACHED
    assert SNAP.rate("EUR", "KES").providers == ["ecb", "exchangerate_api"]
    assert SNAP.rate("AED", "KES").status(POLICY, NOW + timedelta(hours=5)) is RateStatus.CACHED


def test_a_missing_leg_is_unavailable_never_guessed() -> None:
    with pytest.raises(FxRateUnavailable):
        SNAP.rate("AED", "GBP")
    with pytest.raises(FxRateUnavailable):
        SNAP.rate("GBP", "USD")


@pytest.mark.parametrize(
    ("amount", "base", "quote", "places", "expected"),
    [
        ("500000", "AED", "USD", 2, "136147.04"),  # 500,000 / 3.6725 = 136147.0388...
        ("1000", "USD", "JPY", 0, "149830"),
        ("1000", "USD", "KES", 2, "129150.00"),
        ("0.01", "USD", "AED", 2, "0.04"),  # 0.036725 rounds half-up to 0.04
        ("-250.00", "AED", "USD", 2, "-68.07"),  # a liability converts symmetrically
        ("1", "AED", "KES", 2, "35.17"),  # 129.15 / 3.6725 = 35.1668...
    ],
)
def test_conversion_rounds_once_to_the_target_precision(
    amount: str, base: str, quote: str, places: int, expected: str
) -> None:
    resolved = SNAP.rate(base, quote)
    result = convert(Decimal(amount), resolved.rate, places)
    assert result == Decimal(expected)
    assert str(result) == expected

    def per_pivot(c: str) -> Fraction:
        return Fraction(1) if c == "USD" else Fraction(SNAP.legs[c].rate)

    rate_fraction = per_pivot(quote) / per_pivot(base)
    assert result == exact(amount, rate_fraction, places)


def test_half_up_at_the_exact_midpoint() -> None:
    assert convert(Decimal("0.125"), Decimal("1"), 2) == Decimal("0.13")
    assert convert(Decimal("-0.125"), Decimal("1"), 2) == Decimal("-0.13")
    assert convert(Decimal("2.5"), Decimal("1"), 0) == Decimal("3")


rates = st.decimals(min_value="0.0001", max_value="100000", places=4, allow_nan=False)
amounts = st.decimals(min_value="-1000000000", max_value="1000000000", places=2, allow_nan=False)


@settings(max_examples=200, deadline=None)
@given(a=rates, b=rates, amount=amounts, places=st.sampled_from([0, 2, 3]))
def test_properties_against_exact_arithmetic(
    a: Decimal, b: Decimal, amount: Decimal, places: int
) -> None:
    snap = Snapshot(
        uuid.uuid4(), "USD", NOW, {"AAA": leg("AAA", str(a)), "BBB": leg("BBB", str(b))}
    )
    cross = snap.rate("AAA", "BBB")
    reference = Fraction(b) / Fraction(a)
    # The cross rate is the exact ratio to 45+ significant digits.
    assert abs(Fraction(cross.rate) - reference) <= reference * Fraction(1, 10**45)
    # There and back is the identity within the precision of the stored digits.
    back = snap.rate("BBB", "AAA")
    assert abs(Fraction(cross.rate) * Fraction(back.rate) - 1) < Fraction(1, 10**40)
    # The rounding error never exceeds half a unit of the last place.
    error = abs(Fraction(convert(amount, cross.rate, places)) - Fraction(amount) * reference)
    assert error <= Fraction(1, 2 * 10**places) + Fraction(1, 10**30)


def test_conversion_leaves_its_inputs_untouched() -> None:
    amount = Decimal("500000.00")
    before = (amount, dict(SNAP.legs))
    convert(amount, SNAP.rate("AED", "USD").rate, 2)
    assert (amount, dict(SNAP.legs)) == before


# ----------------------------------------------------------------------------------- database
def code() -> str:
    return "Q" + "".join(secrets.choice(string.ascii_uppercase) for _ in range(2))


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


async def store(raw: asyncpg.Connection, base: str, quote: str, rate: str, when: datetime) -> None:
    await raw.execute(
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at) VALUES ($1, $2, $3::numeric, 'conv-test', $4, $4)",
        base,
        quote,
        rate,
        when,
    )


@pytest.mark.integration
async def test_the_fx_service_crosses_through_the_pivot_with_a_path(
    sessions: async_sessionmaker[AsyncSession], raw: asyncpg.Connection
) -> None:
    pivot, a, b = code(), code(), code()
    now = datetime.now(UTC)
    await store(raw, pivot, a, "4", now - timedelta(hours=2))
    await store(raw, b, pivot, "0.5", now - timedelta(hours=1))  # stored the other way round
    async with sessions() as s:
        q = await FxService(s, pivot=pivot).quote(a, b)
        assert q.path == (a, pivot, b)
        assert q.rate == Decimal("0.5")  # 1 a = 1/4 pivot = (1/4) / 0.5 ... = 2 b? checked below
        with pytest.raises(FxRateUnavailable):
            await FxService(s, pivot=pivot).quote(a, b, cross=False)
    # 1 a = 0.25 pivot; 1 pivot = 2 b; so 1 a = 0.5 b.
    assert Fraction(q.rate) == Fraction(1, 4) * 2


@pytest.mark.integration
async def test_snapshots_are_content_addressed_and_immutable(
    sessions: async_sessionmaker[AsyncSession], raw: asyncpg.Connection
) -> None:
    pivot = code()
    async with sessions() as s:
        first = await SnapshotService(s, pivot).current()
        again = await SnapshotService(s, pivot).current()
    assert first.id == again.id, "the same rates are one snapshot"
    await store(raw, pivot, "EUR", "0.9", datetime.now(UTC))
    async with sessions() as s:
        changed = await SnapshotService(s, pivot).current()
        assert changed.id != first.id
        assert changed.rate(pivot, "EUR").rate == Decimal("0.9")
        reloaded = await SnapshotService(s, pivot).get(changed.id)
        assert reloaded.legs == changed.legs
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await raw.execute("UPDATE fx_snapshots SET pivot = 'XXX' WHERE id = $1", changed.id)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await raw.execute("DELETE FROM fx_snapshots WHERE id = $1", changed.id)


# ---------------------------------------------------------------------------------------- API
@pytest.fixture
async def api(
    migrated_settings: Settings,  # noqa: F811
    raw: asyncpg.Connection,
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient, str]]:
    """An app whose pivot is a test currency with its own rates (removed afterwards)."""
    pivot = code()
    await raw.execute(
        "INSERT INTO currencies (code, name, symbol, decimal_places) VALUES ($1, 'Pivot', 'P', 2)",
        pivot,
    )
    now = datetime.now(UTC) - timedelta(minutes=10)
    for quote, rate in (("AED", "3.6725"), ("KES", "129.15"), ("JPY", "149.83"), ("USD", "1")):
        await store(raw, pivot, quote, rate, now)
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


@pytest.mark.integration
async def test_currencies_are_listed_with_their_precision(
    api: tuple[FastAPI, httpx.AsyncClient, str],
    two_users: TwoUsers,  # noqa: F811
) -> None:
    _, http, _ = api
    assert (await http.get("/api/v1/currencies")).status_code == 401
    listed = {
        c["code"]: c
        for c in (await http.get("/api/v1/currencies", headers=two_users.alice.headers)).json()
    }
    assert {"AED", "KES", "USD", "JPY"} <= set(listed)
    assert listed["JPY"]["decimal_places"] == 0 and listed["AED"]["symbol"]


@pytest.mark.integration
async def test_rates_come_from_one_snapshot_with_paths_and_unavailable_pairs(
    api: tuple[FastAPI, httpx.AsyncClient, str],
    two_users: TwoUsers,  # noqa: F811
) -> None:
    _, http, pivot = api
    h = two_users.alice.headers
    r = await http.get(
        "/api/v1/fx/rates", headers=h, params={"base": "AED", "quotes": "KES,USD,GBP"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    by = {x["quote"]: x for x in body["rates"]}
    assert by["KES"]["path"] == ["AED", pivot, "KES"]
    assert Decimal(by["KES"]["rate"]) == Decimal("129.15") / Decimal("3.6725")
    assert by["KES"]["status"] == "current"
    assert body["unavailable"] == ["GBP"]
    one = await http.get(f"/api/v1/fx/rates/AED/KES?snapshot_id={body['snapshot_id']}", headers=h)
    assert one.json()["rate"] == by["KES"]["rate"]
    assert (await http.get("/api/v1/fx/rates/AED/ZZZ", headers=h)).status_code == 422
    assert (await http.get("/api/v1/fx/rates/AED/GBP", headers=h)).status_code == 404
    missing = await http.get(f"/api/v1/fx/rates?snapshot_id={uuid.uuid4()}", headers=h)
    assert missing.status_code == 404


@pytest.mark.integration
async def test_convert_rounds_to_the_target_and_records_the_converter_use(
    api: tuple[FastAPI, httpx.AsyncClient, str],
    raw: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    _, http, pivot = api
    h = two_users.alice.headers
    r = await http.post(
        "/api/v1/fx/convert",
        headers=h,
        json={"amount": {"amount": "500000.00", "currency": "AED"}, "to": "KES"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    expected = exact("500000", Fraction("129.15") / Fraction("3.6725"), 2)
    assert body["converted"] == {"amount": str(expected), "currency": "KES"}
    assert body["source"] == {"amount": "500000.00", "currency": "AED"}
    assert body["path"] == ["AED", pivot, "KES"] and body["notice"]
    jpy = await http.post(
        "/api/v1/fx/convert",
        headers=h,
        json={"amount": {"amount": "10.00", "currency": "AED"}, "to": "JPY"},
    )
    assert "." not in jpy.json()["converted"]["amount"], "JPY has no decimals"
    audit = await raw.fetchrow(
        "SELECT conversion_type, source_amount, converted_amount, snapshot_id FROM "
        "fx_conversion_audit WHERE user_id = $1 ORDER BY created_at LIMIT 1",
        uuid.UUID(two_users.alice.id),
    )
    assert audit is not None and audit["conversion_type"] == "converter"
    assert audit["converted_amount"] == expected
    assert str(audit["snapshot_id"]) == body["snapshot_id"]
    for bad in (
        {"amount": {"amount": "1", "currency": "AED"}, "to": "ZZZ"},
        {"amount": {"amount": 1, "currency": "AED"}, "to": "KES"},
        {"amount": {"amount": "1", "currency": "AED"}, "to": "KES", "rate": "9"},
    ):
        assert (await http.post("/api/v1/fx/convert", headers=h, json=bad)).status_code == 422
