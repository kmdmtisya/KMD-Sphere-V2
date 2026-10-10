"""Core portfolio schema (P05-T01): column types, keys, constraints and indexes.

Part 1 inspects the SQLAlchemy metadata (no database). Part 2 runs against a freshly migrated
database and proves the constraints reject bad data, the ledger is append-only, and money and
rates round-trip exactly."""

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import asyncpg
import pytest
from sqlalchemy import Float, Numeric
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import DateTime

import app.modules.assets.models
import app.modules.identity.models
import app.modules.market_data.models
import app.modules.portfolio.models
import app.modules.transactions.models  # noqa: F401
from app.core.config import Settings
from app.db.base import Base
from app.modules.transactions.models import TRANSACTION_TYPES
from tests.db_fixtures import migrated_settings  # noqa: F401

CORE_TABLES = {
    "portfolios",
    "portfolio_members",
    "asset_classes",
    "assets",
    "asset_metadata",
    "transactions",
    "holdings",
    "valuations",
    "fx_rates",
}
MONEY_LIKE = {
    "amount",
    "gross_amount",
    "fees",
    "taxes",
    "unit_price",
    "value",
    "cost_basis",
    "realized_pl",
    "quantity",
    "rate",
    "fx_rate_to_portfolio_currency",
}

# ------------------------------------------------------------------------------ metadata


def test_no_floating_point_columns_anywhere() -> None:
    offenders = [
        f"{t.name}.{c.name}"
        for t in Base.metadata.tables.values()
        for c in t.columns
        if isinstance(c.type, Float)
    ]
    assert offenders == []


def test_every_money_quantity_and_rate_column_is_numeric() -> None:
    seen = 0
    # asset_metadata.value is deliberately JSONB (any typed fact), not a money column.
    for table in (Base.metadata.tables[n] for n in CORE_TABLES - {"asset_metadata"}):
        for column in table.columns:
            if column.name in MONEY_LIKE:
                assert isinstance(column.type, Numeric), f"{table.name}.{column.name}"
                seen += 1
    assert seen >= 11  # 6 on transactions, 3 on holdings, value, rate


def _numeric(table: str, column: str) -> "Numeric[Any]":
    column_type = Base.metadata.tables[table].c[column].type
    assert isinstance(column_type, Numeric)
    return column_type


def test_numeric_precision_follows_the_conventions() -> None:
    gross = _numeric("transactions", "gross_amount")
    assert (gross.precision, gross.scale) == (28, 8)
    assert _numeric("transactions", "quantity").scale == 12
    assert _numeric("transactions", "fx_rate_to_portfolio_currency").scale == 12
    assert _numeric("fx_rates", "rate").scale == 12


@pytest.mark.parametrize("name", sorted(CORE_TABLES))
def test_core_tables_have_a_uuid_primary_key_and_timestamps(name: str) -> None:
    table = Base.metadata.tables[name]
    pk = list(table.primary_key.columns)
    assert [c.name for c in pk] == ["id"]
    assert isinstance(pk[0].type, PG_UUID)
    assert pk[0].server_default is not None  # gen_random_uuid()
    for stamp in ("created_at", "updated_at"):
        column = table.c[stamp]
        assert isinstance(column.type, DateTime) and column.type.timezone, f"{name}.{stamp}"
        assert not column.nullable


def test_every_foreign_key_states_what_happens_on_delete() -> None:
    for name in CORE_TABLES:
        for fk in Base.metadata.tables[name].foreign_key_constraints:
            assert fk.ondelete in {"CASCADE", "RESTRICT"}, f"{name}: {fk.name}"


def test_financial_rows_are_never_cascade_deleted_from_their_owner() -> None:
    t = Base.metadata.tables
    for table, column in [
        ("portfolios", "user_id"),
        ("transactions", "portfolio_id"),
        ("transactions", "created_by_user_id"),
        ("valuations", "portfolio_id"),
        ("assets", "owner_user_id"),
    ]:
        fk = next(iter(t[table].c[column].foreign_keys))
        assert fk.ondelete == "RESTRICT", f"{table}.{column}"


def test_all_constraints_and_indexes_are_named() -> None:
    for name in CORE_TABLES:
        table = Base.metadata.tables[name]
        for constraint in table.constraints:
            assert constraint.name, f"unnamed constraint on {name}"
        for index in table.indexes:
            assert index.name, f"unnamed index on {name}"


def test_the_fourteen_transaction_types() -> None:
    assert len(TRANSACTION_TYPES) == len(set(TRANSACTION_TYPES)) == 14
    assert set(TRANSACTION_TYPES) == {
        "BUY",
        "SELL",
        "DEPOSIT",
        "WITHDRAWAL",
        "DIVIDEND",
        "INTEREST",
        "COUPON",
        "RENT",
        "DISTRIBUTION",
        "FEE",
        "TAX",
        "TRANSFER_IN",
        "TRANSFER_OUT",
        "VALUATION_ADJUSTMENT",
    }


# ------------------------------------------------------------------------------- database


@pytest.fixture(scope="module")
async def db(migrated_settings: Settings) -> AsyncIterator[asyncpg.Connection]:  # noqa: F811
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    yield conn
    await conn.close()


async def insert(conn: asyncpg.Connection, table: str, **cols: Any) -> uuid.UUID:
    names = list(cols)
    marks = ", ".join(f"${i + 1}" for i in range(len(names)))
    sql = f"INSERT INTO {table} ({', '.join(names)}) VALUES ({marks}) RETURNING id"  # noqa: S608
    return await conn.fetchval(sql, *cols.values())  # type: ignore[no-any-return]


async def new_user(conn: asyncpg.Connection) -> uuid.UUID:
    return await insert(conn, "users", issuer="http://issuer.test", subject=str(uuid.uuid4()))


async def new_portfolio(
    conn: asyncpg.Connection, user: uuid.UUID, *, currency: str = "USD", **extra: Any
) -> uuid.UUID:
    return await insert(
        conn,
        "portfolios",
        user_id=user,
        name=f"p-{uuid.uuid4()}",
        base_currency=currency,
        **extra,
    )


async def new_class(conn: asyncpg.Connection, mode: str = "market") -> uuid.UUID:
    return await insert(
        conn,
        "asset_classes",
        code=f"c_{uuid.uuid4().hex[:12]}",
        name="Test class",
        valuation_mode=mode,
    )


async def new_asset(conn: asyncpg.Connection, cls: uuid.UUID, **extra: Any) -> uuid.UUID:
    cols: dict[str, Any] = {"asset_class_id": cls, "name": "Test asset", "currency": "USD"}
    cols.update(extra)
    return await insert(conn, "assets", **cols)


async def post(
    conn: asyncpg.Connection,
    portfolio: uuid.UUID,
    user: uuid.UUID,
    **overrides: Any,
) -> uuid.UUID:
    from datetime import date

    cols: dict[str, Any] = {
        "portfolio_id": portfolio,
        "transaction_type": "DEPOSIT",
        "trade_date": date(2026, 10, 1),
        "gross_amount": Decimal("100.00"),
        "currency": "USD",
        "created_by_user_id": user,
    }
    cols.update(overrides)
    return await insert(conn, "transactions", **cols)


@pytest.fixture
async def world(db: asyncpg.Connection) -> dict[str, uuid.UUID]:
    user = await new_user(db)
    cls = await new_class(db)
    return {
        "user": user,
        "portfolio": await new_portfolio(db, user),
        "asset": await new_asset(db, cls),
        "class": cls,
    }


@pytest.mark.integration
async def test_defaults_and_exact_round_trip_of_money_quantities_and_rates(
    db: asyncpg.Connection, world: dict[str, uuid.UUID]
) -> None:
    big = Decimal("12345678901234567890.12345678")
    tx = await post(
        db,
        world["portfolio"],
        world["user"],
        transaction_type="BUY",
        asset_id=world["asset"],
        quantity=Decimal("0.000000000001"),
        unit_price=Decimal("0.1"),
        gross_amount=big,
        fx_rate_to_portfolio_currency=Decimal("3.672500000001"),
    )
    row = await db.fetchrow("SELECT * FROM transactions WHERE id = $1", tx)
    assert row is not None
    assert row["gross_amount"] == big
    assert row["quantity"] == Decimal("0.000000000001")
    assert row["unit_price"] == Decimal("0.10000000")
    assert row["fx_rate_to_portfolio_currency"] == Decimal("3.672500000001")
    assert row["fees"] == 0 and row["taxes"] == 0
    assert row["source"] == "manual"
    assert row["created_at"] is not None and row["updated_at"] is not None
    # 0.1 + 0.2 is exact in NUMERIC (it is not in binary floating point).
    assert await db.fetchval("SELECT 0.1::numeric + 0.2::numeric") == Decimal("0.3")


@pytest.mark.integration
@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"currency": "usd"}, "currency"),
        ({"currency": "US"}, "currency"),
        ({"transaction_type": "GIFT"}, "transaction_type"),
        ({"fees": Decimal("-0.01")}, "fees_taxes_non_negative"),
        ({"taxes": Decimal("-1")}, "fees_taxes_non_negative"),
        ({"gross_amount": Decimal("-5")}, "gross_amount_non_negative"),
        ({"quantity": Decimal("-1")}, "quantity_non_negative"),
        ({"unit_price": Decimal("-1")}, "unit_price_non_negative"),
        ({"fx_rate_to_portfolio_currency": Decimal("0")}, "fx_rate_positive"),
        ({"fx_rate_to_portfolio_currency": Decimal("-1.2")}, "fx_rate_positive"),
        ({"source": "scraped"}, "source"),
        ({"idempotency_key": ""}, "idempotency_key_length"),
        ({"transaction_type": "BUY"}, "trade_has_asset_quantity_price"),
        ({"transaction_type": "SELL", "quantity": Decimal("0")}, "trade_has_asset_quantity_price"),
    ],
)
async def test_the_ledger_rejects_invalid_postings(
    db: asyncpg.Connection,
    world: dict[str, uuid.UUID],
    overrides: dict[str, Any],
    constraint: str,
) -> None:
    with pytest.raises(asyncpg.CheckViolationError) as info:
        await post(db, world["portfolio"], world["user"], **overrides)
    assert constraint in str(info.value)


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["BUY", "SELL"])
async def test_a_trade_of_zero_units_is_rejected_even_with_an_asset_and_price(
    db: asyncpg.Connection, world: dict[str, uuid.UUID], kind: str
) -> None:
    with pytest.raises(asyncpg.CheckViolationError, match="trade_has_asset_quantity_price"):
        await post(
            db,
            world["portfolio"],
            world["user"],
            transaction_type=kind,
            asset_id=world["asset"],
            quantity=Decimal("0"),
            unit_price=Decimal("10"),
        )


@pytest.mark.integration
async def test_a_buy_needs_an_asset_quantity_and_price_but_a_deposit_does_not(
    db: asyncpg.Connection, world: dict[str, uuid.UUID]
) -> None:
    await post(db, world["portfolio"], world["user"])  # DEPOSIT without an asset
    await post(
        db,
        world["portfolio"],
        world["user"],
        transaction_type="BUY",
        asset_id=world["asset"],
        quantity=Decimal("2"),
        unit_price=Decimal("10"),
    )


@pytest.mark.integration
async def test_settlement_cannot_precede_the_trade_date(
    db: asyncpg.Connection, world: dict[str, uuid.UUID]
) -> None:
    from datetime import date

    with pytest.raises(asyncpg.CheckViolationError, match="settlement_after_trade"):
        await post(
            db,
            world["portfolio"],
            world["user"],
            trade_date=date(2026, 10, 5),
            settlement_date=date(2026, 10, 4),
        )


@pytest.mark.integration
async def test_only_a_valuation_adjustment_can_be_negative(
    db: asyncpg.Connection, world: dict[str, uuid.UUID]
) -> None:
    await post(
        db,
        world["portfolio"],
        world["user"],
        transaction_type="VALUATION_ADJUSTMENT",
        gross_amount=Decimal("-250.00"),
    )


@pytest.mark.integration
async def test_idempotency_keys_are_unique_within_a_portfolio_only(
    db: asyncpg.Connection, world: dict[str, uuid.UUID]
) -> None:
    key = f"key-{uuid.uuid4()}"
    await post(db, world["portfolio"], world["user"], idempotency_key=key)
    with pytest.raises(asyncpg.UniqueViolationError):
        await post(db, world["portfolio"], world["user"], idempotency_key=key)
    other = await new_portfolio(db, world["user"])
    await post(db, other, world["user"], idempotency_key=key)  # another portfolio: fine
    await post(db, world["portfolio"], world["user"])  # no key: never conflicts
    await post(db, world["portfolio"], world["user"])


@pytest.mark.integration
async def test_a_reversal_points_at_one_entry_in_the_same_portfolio_once(
    db: asyncpg.Connection, world: dict[str, uuid.UUID]
) -> None:
    original = await post(db, world["portfolio"], world["user"])
    reversal = await post(db, world["portfolio"], world["user"], reverses_transaction_id=original)
    assert reversal != original
    with pytest.raises(asyncpg.UniqueViolationError):  # reversed already
        await post(db, world["portfolio"], world["user"], reverses_transaction_id=original)
    other = await new_portfolio(db, world["user"])
    unreversed = await post(db, world["portfolio"], world["user"])
    with pytest.raises(asyncpg.ForeignKeyViolationError):  # a reversal in another portfolio
        await post(db, other, world["user"], reverses_transaction_id=unreversed)
    with pytest.raises(asyncpg.ForeignKeyViolationError):  # unknown entry
        await post(db, world["portfolio"], world["user"], reverses_transaction_id=uuid.uuid4())


@pytest.mark.integration
async def test_posted_transactions_cannot_be_changed_or_deleted(
    db: asyncpg.Connection, world: dict[str, uuid.UUID]
) -> None:
    tx = await post(db, world["portfolio"], world["user"])
    for sql in (
        "UPDATE transactions SET gross_amount = 1 WHERE id = $1",
        "UPDATE transactions SET note = 'edited' WHERE id = $1",
        "DELETE FROM transactions WHERE id = $1",
    ):
        with pytest.raises(asyncpg.InsufficientPrivilegeError, match="append-only"):
            await db.execute(sql, tx)
    with pytest.raises(asyncpg.InsufficientPrivilegeError, match="TRUNCATE"):
        await db.execute("TRUNCATE transactions")
    assert await db.fetchval("SELECT gross_amount FROM transactions WHERE id = $1", tx) == Decimal(
        "100.00"
    )


@pytest.mark.integration
async def test_ledger_history_cannot_be_deleted_through_its_owners(
    db: asyncpg.Connection, world: dict[str, uuid.UUID]
) -> None:
    await post(
        db,
        world["portfolio"],
        world["user"],
        transaction_type="BUY",
        asset_id=world["asset"],
        quantity=Decimal("1"),
        unit_price=Decimal("5"),
    )
    with pytest.raises(asyncpg.IntegrityConstraintViolationError):
        await db.execute("DELETE FROM portfolios WHERE id = $1", world["portfolio"])
    with pytest.raises(asyncpg.IntegrityConstraintViolationError):
        await db.execute("DELETE FROM users WHERE id = $1", world["user"])
    with pytest.raises(asyncpg.IntegrityConstraintViolationError):
        await db.execute("DELETE FROM assets WHERE id = $1", world["asset"])
    with pytest.raises(asyncpg.IntegrityConstraintViolationError):
        await db.execute("DELETE FROM asset_classes WHERE id = $1", world["class"])


@pytest.mark.integration
@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"base_currency": "usd"}, asyncpg.CheckViolationError),
        ({"portfolio_type": "hedge_fund"}, asyncpg.CheckViolationError),
        ({"name": "   "}, asyncpg.CheckViolationError),
        ({"name": "x" * 101}, asyncpg.StringDataRightTruncationError),
    ],
)
async def test_portfolio_constraints(
    db: asyncpg.Connection,
    world: dict[str, uuid.UUID],
    overrides: dict[str, Any],
    error: type[Exception],
) -> None:
    cols: dict[str, Any] = {
        "user_id": world["user"],
        "name": f"p-{uuid.uuid4()}",
        "base_currency": "USD",
    }
    cols.update(overrides)
    with pytest.raises(error):
        await insert(db, "portfolios", **cols)


@pytest.mark.integration
async def test_portfolio_names_are_unique_per_user_and_types_default_to_personal(
    db: asyncpg.Connection, world: dict[str, uuid.UUID]
) -> None:
    name = f"Retirement-{uuid.uuid4()}"
    pid = await insert(db, "portfolios", user_id=world["user"], name=name, base_currency="KES")
    assert (
        await db.fetchval("SELECT portfolio_type FROM portfolios WHERE id = $1", pid) == "personal"
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await insert(db, "portfolios", user_id=world["user"], name=name, base_currency="KES")
    another_user = await new_user(db)
    await insert(db, "portfolios", user_id=another_user, name=name, base_currency="KES")


@pytest.mark.integration
async def test_members_have_a_role_and_appear_once(
    db: asyncpg.Connection, world: dict[str, uuid.UUID]
) -> None:
    member = await new_user(db)
    await insert(
        db, "portfolio_members", portfolio_id=world["portfolio"], user_id=member, role="viewer"
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await insert(
            db, "portfolio_members", portfolio_id=world["portfolio"], user_id=member, role="editor"
        )
    with pytest.raises(asyncpg.CheckViolationError):
        await insert(
            db,
            "portfolio_members",
            portfolio_id=world["portfolio"],
            user_id=await new_user(db),
            role="owner",
        )


@pytest.mark.integration
async def test_assets_catalogue_rules(db: asyncpg.Connection, world: dict[str, uuid.UUID]) -> None:
    cls = world["class"]
    # A new asset class is a row, not a schema change.
    await new_class(db, "manual")
    with pytest.raises(asyncpg.CheckViolationError):
        await new_class(db, "guess")
    with pytest.raises(asyncpg.CheckViolationError):
        await new_asset(db, cls, currency="usd")
    with pytest.raises(asyncpg.CheckViolationError):
        await new_asset(db, cls, country="ke")
    with pytest.raises(asyncpg.StringDataRightTruncationError):
        await new_asset(db, cls, country="KEN")
    with pytest.raises(asyncpg.CheckViolationError):  # half a provider reference
        await new_asset(db, cls, external_provider="acme")
    ref = f"X-{uuid.uuid4()}"
    await new_asset(db, cls, external_provider="acme", external_provider_id=ref)
    with pytest.raises(asyncpg.UniqueViolationError):
        await new_asset(db, cls, external_provider="acme", external_provider_id=ref)
    await new_asset(db, cls, external_provider="other", external_provider_id=ref)
    await new_asset(db, cls)  # user-defined assets have no provider reference, many allowed
    await new_asset(db, cls)
    mine = await new_asset(db, cls, owner_user_id=world["user"])
    assert (
        await db.fetchval("SELECT owner_user_id FROM assets WHERE id = $1", mine) == world["user"]
    )


@pytest.mark.integration
async def test_asset_metadata_is_one_value_per_key_and_follows_its_asset(
    db: asyncpg.Connection, world: dict[str, uuid.UUID]
) -> None:
    asset = await new_asset(db, world["class"])
    sql = "INSERT INTO asset_metadata (asset_id, key, value) VALUES ($1, $2, $3::jsonb)"
    await db.execute(sql, asset, "coupon_rate", '"0.0525"')
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.execute(sql, asset, "coupon_rate", '"0.06"')
    with pytest.raises(asyncpg.CheckViolationError):
        await db.execute(sql, asset, "Bad Key", "1")
    await db.execute("DELETE FROM assets WHERE id = $1", asset)
    assert await db.fetchval("SELECT count(*) FROM asset_metadata WHERE asset_id = $1", asset) == 0


@pytest.mark.integration
async def test_fx_rates_are_positive_distinct_pairs_stored_exactly_and_unique_per_instant(
    db: asyncpg.Connection,
) -> None:
    from datetime import UTC, datetime

    ts = datetime(2026, 10, 1, 12, tzinfo=UTC)
    base: dict[str, Any] = {
        "base_currency": "USD",
        "quote_currency": "KES",
        "rate": Decimal("129.123456789012"),
        "provider": f"p-{uuid.uuid4().hex[:8]}",
        "rate_timestamp": ts,
        "retrieved_at": ts,
    }
    fx = await insert(db, "fx_rates", **base)
    assert await db.fetchval("SELECT rate FROM fx_rates WHERE id = $1", fx) == Decimal(
        "129.123456789012"
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await insert(db, "fx_rates", **base)
    for change in (
        {"rate": Decimal("0")},
        {"rate": Decimal("-1")},
        {"quote_currency": "USD"},
        {"base_currency": "usd"},
    ):
        with pytest.raises(asyncpg.CheckViolationError):
            await insert(db, "fx_rates", **{**base, "provider": "other", **change})


@pytest.mark.integration
async def test_holdings_are_one_row_per_asset_per_portfolio(
    db: asyncpg.Connection, world: dict[str, uuid.UUID]
) -> None:
    cols: dict[str, Any] = {
        "portfolio_id": world["portfolio"],
        "asset_id": world["asset"],
        "quantity": Decimal("10.5"),
        "cost_basis": Decimal("1050.00"),
        "currency": "USD",
    }
    hid = await insert(db, "holdings", **cols)
    assert await db.fetchval("SELECT realized_pl FROM holdings WHERE id = $1", hid) == 0
    with pytest.raises(asyncpg.UniqueViolationError):
        await insert(db, "holdings", **cols)
    with pytest.raises(asyncpg.CheckViolationError):
        await insert(
            db,
            "holdings",
            **{**cols, "asset_id": await new_asset(db, world["class"]), "quantity": Decimal("-1")},
        )
    # Derived data goes with its portfolio's holdings rows (rebuildable from the ledger).
    empty = await new_portfolio(db, world["user"])
    await insert(db, "holdings", **{**cols, "portfolio_id": empty})
    await db.execute("DELETE FROM portfolios WHERE id = $1", empty)
    assert await db.fetchval("SELECT count(*) FROM holdings WHERE portfolio_id = $1", empty) == 0


@pytest.mark.integration
async def test_valuations_are_one_per_asset_per_instant_and_not_negative(
    db: asyncpg.Connection, world: dict[str, uuid.UUID]
) -> None:
    from datetime import UTC, datetime

    cols: dict[str, Any] = {
        "portfolio_id": world["portfolio"],
        "asset_id": world["asset"],
        "value": Decimal("250000.00"),
        "currency": "KES",
        "as_of": datetime(2026, 9, 30, tzinfo=UTC),
        "source": "owner estimate",
        "created_by_user_id": world["user"],
    }
    await insert(db, "valuations", **cols)
    with pytest.raises(asyncpg.UniqueViolationError):
        await insert(db, "valuations", **cols)
    await insert(db, "valuations", **{**cols, "as_of": datetime(2026, 10, 1, tzinfo=UTC)})
    for change in ({"value": Decimal("-1")}, {"currency": "ke"}, {"source": "  "}):
        with pytest.raises(asyncpg.CheckViolationError):
            await insert(
                db, "valuations", **{**cols, "as_of": datetime(2026, 11, 1, tzinfo=UTC), **change}
            )


@pytest.mark.integration
async def test_the_indexes_that_serve_the_main_queries_exist(db: asyncpg.Connection) -> None:
    rows = await db.fetch("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
    names = {r["indexname"] for r in rows}
    expected = {
        "ix_portfolios_user_id_archived_at",
        "ix_portfolio_members_user_id",
        "ix_assets_symbol",
        "ix_assets_asset_class_id",
        "ix_assets_owner_user_id",
        "uq_assets_external_ref",
        "ix_transactions_portfolio_id_trade_date",
        "ix_transactions_asset_id",
        "ix_holdings_asset_id",
        "ix_fx_rates_pair_rate_timestamp",
    }
    assert expected <= names, expected - names
