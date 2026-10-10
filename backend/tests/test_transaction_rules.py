"""Posting rules per transaction type (pure; P05-T04)."""

import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.core.money import Money
from app.modules.transactions.models import TRANSACTION_TYPES
from app.modules.transactions.rules import Draft, RuleViolation, normalise

TODAY = date(2026, 10, 10)
ASSET = uuid.uuid4()


def usd(amount: str, currency: str = "USD") -> Money:
    return Money(amount=Decimal(amount), currency=currency)


def draft(kind: str, **changes: Any) -> Draft:
    base = Draft(
        transaction_type=kind,
        trade_date=TODAY,
        settlement_date=None,
        asset_id=None,
        quantity=None,
        unit_price=None,
        gross_amount=usd("100.00"),
        fees=None,
        taxes=None,
        currency="USD",
        fx_rate=None,
        fx_rate_as_of=None,
        fx_rate_source=None,
    )
    if kind in {"BUY", "SELL"}:
        base = replace(
            base, asset_id=ASSET, quantity=Decimal("4"), unit_price=usd("25"), gross_amount=None
        )
    elif kind in {"TRANSFER_IN", "TRANSFER_OUT"}:
        base = replace(base, asset_id=ASSET, quantity=Decimal("4"))
    elif kind in {"DIVIDEND", "COUPON", "RENT", "DISTRIBUTION", "VALUATION_ADJUSTMENT"}:
        base = replace(base, asset_id=ASSET)
    return replace(base, **changes)


def run(d: Draft, portfolio_currency: str = "USD") -> Any:
    return normalise(d, portfolio_currency, TODAY)


def violates(field: str, d: Draft, portfolio_currency: str = "USD") -> None:
    with pytest.raises(RuleViolation) as info:
        run(d, portfolio_currency)
    assert info.value.field == field, str(info.value)


@pytest.mark.parametrize("kind", TRANSACTION_TYPES)
def test_every_type_has_a_valid_minimal_posting(kind: str) -> None:
    posting = run(draft(kind))
    assert posting.transaction_type == kind
    assert posting.fees == 0 and posting.taxes == 0
    assert posting.fx_rate_to_portfolio_currency == 1
    assert posting.fx_rate_source is None


# ------------------------------------------------------------------------------- trades


def test_a_trade_derives_its_gross_amount_rounding_ties_up() -> None:
    p = run(draft("BUY", quantity=Decimal("3"), unit_price=usd("10.005")))
    assert p.gross_amount == Decimal("30.02")  # 30.015 -> 30.02 (ROUND_HALF_UP)
    p = run(draft("SELL", quantity=Decimal("3"), unit_price=usd("10.005")))
    assert p.gross_amount == Decimal("30.02")


@pytest.mark.parametrize(
    ("quantity", "price", "gross"),
    [
        ("1", "10.025", "10.03"),  # half-even would give 10.02
        ("1", "10.015", "10.02"),
        ("1", "0.005", "0.01"),
        ("2", "0.0025", "0.01"),  # 0.005 -> 0.01
        ("1", "10.0249", "10.02"),
    ],
)
def test_derived_gross_rounds_half_up_at_the_currency_minor_unit(
    quantity: str, price: str, gross: str
) -> None:
    p = run(draft("BUY", quantity=Decimal(quantity), unit_price=usd(price)))
    assert p.gross_amount == Decimal(gross)


def test_yen_and_dinar_trades_round_to_their_own_minor_units() -> None:
    jpy = draft("BUY", currency="JPY", quantity=Decimal("3"), unit_price=usd("100.5", "JPY"))
    assert run(jpy, "JPY").gross_amount == Decimal("302")  # 301.5 -> 302
    kwd = draft("BUY", currency="KWD", quantity=Decimal("1"), unit_price=usd("1.2345", "KWD"))
    assert run(kwd, "KWD").gross_amount == Decimal("1.235")


@pytest.mark.parametrize(("given", "ok"), [("30.01", True), ("30.02", True), ("30.03", False)])
def test_a_given_gross_must_match_quantity_times_price_within_one_minor_unit(
    given: str, ok: bool
) -> None:
    d = draft("BUY", quantity=Decimal("3"), unit_price=usd("10.005"), gross_amount=usd(given))
    if ok:
        assert run(d).gross_amount == Decimal(given)
    else:
        violates("gross_amount", d)


@pytest.mark.parametrize("kind", ["BUY", "SELL"])
def test_trades_need_asset_quantity_and_price(kind: str) -> None:
    violates("asset_id", draft(kind, asset_id=None))
    violates("quantity", draft(kind, quantity=None))
    violates("quantity", draft(kind, quantity=Decimal("0")))
    violates("quantity", draft(kind, quantity=Decimal("-1")))
    violates("unit_price", draft(kind, unit_price=None))
    violates("unit_price", draft(kind, unit_price=usd("-1")))


def test_quantity_and_price_precision() -> None:
    run(draft("BUY", quantity=Decimal("0.000000000001"), unit_price=usd("1")))
    violates("quantity", draft("BUY", quantity=Decimal("0.0000000000001")))
    run(draft("BUY", unit_price=usd("0.00000001")))
    violates("unit_price", draft("BUY", unit_price=usd("0.000000001")))


# --------------------------------------------------------------------- other types


@pytest.mark.parametrize("kind", ["TRANSFER_IN", "TRANSFER_OUT"])
def test_transfers_need_asset_and_quantity_price_optional(kind: str) -> None:
    run(draft(kind, unit_price=usd("12.5")))
    run(draft(kind, gross_amount=usd("0")))
    violates("asset_id", draft(kind, asset_id=None))
    violates("quantity", draft(kind, quantity=None))
    violates("gross_amount", draft(kind, gross_amount=None))


@pytest.mark.parametrize("kind", ["DIVIDEND", "COUPON", "RENT", "DISTRIBUTION"])
def test_asset_income_needs_an_asset_and_no_units(kind: str) -> None:
    violates("asset_id", draft(kind, asset_id=None))
    violates("quantity", draft(kind, quantity=Decimal("1")))
    violates("unit_price", draft(kind, unit_price=usd("1")))
    violates("gross_amount", draft(kind, gross_amount=None))


@pytest.mark.parametrize("kind", ["DEPOSIT", "WITHDRAWAL"])
def test_cash_movements_have_no_asset(kind: str) -> None:
    violates("asset_id", draft(kind, asset_id=ASSET))


@pytest.mark.parametrize("kind", ["INTEREST", "FEE", "TAX"])
def test_asset_optional_types(kind: str) -> None:
    run(draft(kind))
    run(draft(kind, asset_id=ASSET))


def test_only_a_valuation_adjustment_can_be_negative() -> None:
    assert run(draft("VALUATION_ADJUSTMENT", gross_amount=usd("-250.00"))).gross_amount == Decimal(
        "-250.00"
    )
    for kind in ("DEPOSIT", "DIVIDEND", "WITHDRAWAL", "TRANSFER_IN"):
        violates("gross_amount", draft(kind, gross_amount=usd("-1")))
    violates("fees", draft("DEPOSIT", fees=usd("-0.01")))
    violates("taxes", draft("DEPOSIT", taxes=usd("-0.01")))


# ------------------------------------------------------------------- currency and minor units


def test_amounts_use_the_currencys_minor_units() -> None:
    run(draft("DEPOSIT", currency="KWD", gross_amount=usd("1.234", "KWD")), "KWD")
    violates("gross_amount", draft("DEPOSIT", gross_amount=usd("100.001")))
    violates(
        "gross_amount",
        draft("DEPOSIT", currency="JPY", gross_amount=usd("100.5", "JPY")),
        "JPY",
    )
    violates("fees", draft("DEPOSIT", fees=usd("0.001")))


def test_every_amount_is_in_the_posting_currency() -> None:
    violates("gross_amount", draft("DEPOSIT", gross_amount=usd("1", "EUR")))
    violates("fees", draft("DEPOSIT", fees=usd("1", "EUR")))
    violates("taxes", draft("DEPOSIT", taxes=usd("1", "EUR")))
    violates("unit_price", draft("BUY", unit_price=usd("1", "EUR")))


def test_fx_rate_to_the_portfolio_currency() -> None:
    as_of = datetime(2026, 10, 9, 16, tzinfo=UTC)
    eur = draft("DEPOSIT", currency="EUR", gross_amount=usd("100.00", "EUR"))
    violates("fx_rate_to_portfolio_currency", eur)  # foreign: rate required
    violates("fx_rate_to_portfolio_currency", replace(eur, fx_rate=Decimal("0")))
    violates("fx_rate_to_portfolio_currency", replace(eur, fx_rate=Decimal("1.0000000000001")))
    p = run(replace(eur, fx_rate=Decimal("1.0825"), fx_rate_as_of=as_of))
    assert p.fx_rate_to_portfolio_currency == Decimal("1.0825")
    assert (p.fx_rate_as_of, p.fx_rate_source) == (as_of, "user")
    p = run(replace(eur, fx_rate=Decimal("1.0825"), fx_rate_source="broker"))
    assert p.fx_rate_source == "broker"
    # Same currency: the rate is 1, and the source and time are dropped.
    p = run(draft("DEPOSIT", fx_rate=Decimal("1"), fx_rate_as_of=as_of, fx_rate_source="x"))
    assert (p.fx_rate_to_portfolio_currency, p.fx_rate_as_of, p.fx_rate_source) == (1, None, None)
    violates("fx_rate_to_portfolio_currency", draft("DEPOSIT", fx_rate=Decimal("1.1")))


# -------------------------------------------------------------------------------- dates


def test_dates() -> None:
    run(draft("DEPOSIT", trade_date=TODAY + timedelta(days=1)))  # time-zone slack
    violates("trade_date", draft("DEPOSIT", trade_date=TODAY + timedelta(days=2)))
    run(draft("DEPOSIT", settlement_date=TODAY))
    violates("settlement_date", draft("DEPOSIT", settlement_date=TODAY - timedelta(days=1)))
