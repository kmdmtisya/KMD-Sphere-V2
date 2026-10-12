"""The FXCUR data model (P11-T02): currencies as data, the reporting-currency preference, the
fx_rates extension and the append-only conversion audit."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import asyncpg
import pytest

from app.core.config import Settings
from app.core.money import minor_units
from app.modules.fx.models import ConversionAuditImmutableError, FxConversionAudit
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = pytest.mark.integration

LAUNCH = {"AED", "AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "KES", "USD", "ZAR"}
NEW_TABLES = ("currencies", "user_currency_preferences", "fx_conversion_audit")


@pytest.fixture
async def db(migrated_settings: Settings) -> AsyncIterator[asyncpg.Connection]:  # noqa: F811
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    yield conn
    await conn.close()


async def a_user(db: asyncpg.Connection) -> uuid.UUID:
    user = uuid.uuid4()
    await db.execute(
        "INSERT INTO users (id, issuer, subject) VALUES ($1, 'https://fx.test', $2)",
        user,
        str(user),
    )
    return user


async def test_the_launch_currencies_are_seeded_with_iso_minor_units(
    db: asyncpg.Connection,
) -> None:
    rows = await db.fetch("SELECT code, name, symbol, decimal_places, is_active FROM currencies")
    by_code = {r["code"]: r for r in rows}
    assert set(by_code) >= LAUNCH
    for code in LAUNCH:
        assert by_code[code]["decimal_places"] == minor_units(code), code
        assert by_code[code]["is_active"] is True
        assert by_code[code]["name"] and by_code[code]["symbol"]
    assert by_code["JPY"]["decimal_places"] == 0


async def test_no_new_column_is_floating_point(db: asyncpg.Connection) -> None:
    rows = await db.fetch(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_name = ANY($1::text[]) OR (table_name = 'fx_rates')",
        list(NEW_TABLES),
    )
    floats = [r for r in rows if r["data_type"] in ("real", "double precision")]
    assert floats == []
    numeric = {(r["table_name"], r["column_name"]) for r in rows if r["data_type"] == "numeric"}
    assert {
        ("fx_conversion_audit", "source_amount"),
        ("fx_conversion_audit", "converted_amount"),
        ("fx_conversion_audit", "rate"),
        ("fx_rates", "rate"),
    } <= numeric


async def test_adding_a_currency_is_a_data_change(db: asyncpg.Connection) -> None:
    code = "XTS"  # ISO 4217 code reserved for testing
    await db.execute("DELETE FROM user_currency_preferences WHERE reporting_currency = $1", code)
    await db.execute("DELETE FROM currencies WHERE code = $1", code)
    await db.execute(
        "INSERT INTO currencies (code, name, symbol, decimal_places) "
        "VALUES ($1, 'Test currency', 'T', 3)",
        code,
    )
    user = await a_user(db)
    await db.execute(
        "INSERT INTO user_currency_preferences (user_id, reporting_currency) VALUES ($1, $2)",
        user,
        code,
    )
    assert (
        await db.fetchval(
            "SELECT reporting_currency FROM user_currency_preferences WHERE user_id = $1", user
        )
        == code
    )
    await db.execute("DELETE FROM users WHERE id = $1", user)
    await db.execute("DELETE FROM currencies WHERE code = $1", code)


async def test_the_preference_must_name_a_known_currency_and_keeps_few_recents(
    db: asyncpg.Connection,
) -> None:
    user = await a_user(db)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await db.execute(
            "INSERT INTO user_currency_preferences (user_id, reporting_currency) "
            "VALUES ($1, 'ZZZ')",
            user,
        )
    with pytest.raises(asyncpg.CheckViolationError):
        await db.execute(
            "INSERT INTO user_currency_preferences (user_id, reporting_currency, "
            "recent_currencies) VALUES ($1, 'USD', $2)",
            user,
            ["AED", "EUR", "GBP", "JPY", "KES", "ZAR"],
        )
    await db.execute(
        "INSERT INTO user_currency_preferences (user_id, reporting_currency, recent_currencies) "
        "VALUES ($1, 'AED', $2)",
        user,
        ["USD", "KES"],
    )
    # A currency in use cannot be removed from the reference table.
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await db.execute("DELETE FROM currencies WHERE code = 'AED'")
    # The preference goes with the account.
    await db.execute("DELETE FROM users WHERE id = $1", user)
    assert (
        await db.fetchval("SELECT count(*) FROM user_currency_preferences WHERE user_id = $1", user)
        == 0
    )


async def test_fx_rates_carry_a_rate_type_and_an_optional_path(db: asyncpg.Connection) -> None:
    now = datetime.now(UTC)
    provider = f"schema-test-{uuid.uuid4().hex[:8]}"
    row = await db.fetchrow(
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at) VALUES ('USD', 'AED', 3.6725, $1, $2, $2) RETURNING rate_type, rate_path",
        provider,
        now,
    )
    assert row is not None
    assert (row["rate_type"], row["rate_path"]) == ("indicative", None)
    derived = await db.fetchrow(
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at, rate_type, rate_path) VALUES ('AED', 'KES', 35.1, $1, $2, $2, "
        "'mid_market', $3) RETURNING rate_path",
        provider,
        now,
        ["AED", "USD", "KES"],
    )
    assert derived is not None and derived["rate_path"] == ["AED", "USD", "KES"]
    for bad in (
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at, rate_type) VALUES ('USD', 'EUR', 0.9, $1, $2, $2, 'guessed')",
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at, rate_path) VALUES ('USD', 'EUR', 0.9, $1, $2, $2, ARRAY['USD'])",
    ):
        with pytest.raises(asyncpg.CheckViolationError):
            await db.execute(bad, provider, now)
    await db.execute("DELETE FROM fx_rates WHERE provider = $1", provider)


async def test_pair_and_time_lookups_are_indexed(db: asyncpg.Connection) -> None:
    definition = await db.fetchval(
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_fx_rates_pair_rate_timestamp'"
    )
    assert definition is not None
    assert "(base_currency, quote_currency, rate_timestamp)" in definition


async def test_the_conversion_audit_is_append_only_in_the_database(
    db: asyncpg.Connection,
) -> None:
    user = uuid.uuid4()  # no foreign key: the record outlives the account
    audit_id = await db.fetchval(
        "INSERT INTO fx_conversion_audit (user_id, source_currency, target_currency, "
        "source_amount, converted_amount, rate, rate_timestamp, provider, conversion_type) "
        "VALUES ($1, 'AED', 'USD', 500000, 136147.0, 0.272294, now(), 'ecb', 'converter') "
        "RETURNING id",
        user,
    )
    for statement in (
        "UPDATE fx_conversion_audit SET converted_amount = 1 WHERE id = $1",
        "DELETE FROM fx_conversion_audit WHERE id = $1",
    ):
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await db.execute(statement, audit_id)
    with pytest.raises(asyncpg.InsufficientPrivilegeError):
        await db.execute("TRUNCATE fx_conversion_audit")
    with pytest.raises(asyncpg.CheckViolationError):
        await db.execute(
            "INSERT INTO fx_conversion_audit (user_id, source_currency, target_currency, "
            "source_amount, converted_amount, rate, rate_timestamp, provider, conversion_type) "
            "VALUES ($1, 'AED', 'USD', 1, 1, 1, now(), 'ecb', 'display_switch')",
            user,
        )


def test_the_orm_refuses_to_change_an_audit_record() -> None:
    from app.modules.fx import models

    record = FxConversionAudit(
        user_id=uuid.uuid4(),
        source_currency="AED",
        target_currency="USD",
        source_amount=Decimal("1"),
        converted_amount=Decimal("0.27"),
        rate=Decimal("0.272294"),
        rate_timestamp=datetime.now(UTC),
        provider="ecb",
        conversion_type="converter",
    )
    with pytest.raises(ConversionAuditImmutableError):
        models._refuse_update(None, None, record)
    with pytest.raises(ConversionAuditImmutableError):
        models._refuse_delete(None, None, record)
