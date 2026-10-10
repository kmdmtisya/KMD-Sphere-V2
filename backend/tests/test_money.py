"""Rounding and precision rules of app/core/money.py, tested directly (ADR-0003, ADR-0006).
Allocation by largest remainder (`percentages`) is tested in test_portfolio_summary.py."""

from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from app.core.money import (
    DecimalString,
    Money,
    decimals_of,
    format_decimal,
    minor_units,
    round_half_up,
)


@pytest.mark.parametrize(
    ("value", "places", "expected"),
    [
        # Ties go away from zero (ADR-0006 rule 1), including negatives.
        ("2.345", 2, "2.35"),
        ("-2.345", 2, "-2.35"),
        ("0.005", 2, "0.01"),
        ("-0.005", 2, "-0.01"),
        ("2.5", 0, "3"),
        ("-2.5", 0, "-3"),
        ("1.0005", 3, "1.001"),
        ("-1.0005", 3, "-1.001"),
        # Not a tie: nearest.
        ("2.3449999999", 2, "2.34"),
        ("2.3450000001", 2, "2.35"),
        ("-2.3449999999", 2, "-2.34"),
        # Already at the precision: unchanged, and trailing zeros are written out.
        ("2.30", 2, "2.30"),
        ("7", 2, "7.00"),
        ("0", 3, "0.000"),
        # Many digits: no binary floating point anywhere.
        ("12345678901234567890.125", 2, "12345678901234567890.13"),
        ("0.1", 12, "0.100000000000"),
    ],
)
def test_round_half_up(value: str, places: int, expected: str) -> None:
    result = round_half_up(Decimal(value), places)
    assert str(result) == expected
    assert decimals_of(result) == places


@pytest.mark.parametrize(
    ("currency", "units"),
    [
        ("USD", 2),
        ("AED", 2),
        ("KES", 2),
        ("EUR", 2),
        ("JPY", 0),
        ("KRW", 0),
        ("KWD", 3),
        ("BHD", 3),
        ("OMR", 3),
        ("XYZ", 2),  # not in the table: the default
    ],
)
def test_minor_units_follow_iso_4217(currency: str, units: int) -> None:
    assert minor_units(currency) == units


@pytest.mark.parametrize(
    ("currency", "value", "expected"),
    [("USD", "10.005", "10.01"), ("JPY", "1500.5", "1501"), ("KWD", "1.0005", "1.001")],
)
def test_rounding_to_a_currency(currency: str, value: str, expected: str) -> None:
    assert str(round_half_up(Decimal(value), minor_units(currency))) == expected


@pytest.mark.parametrize(
    ("value", "expected"), [("12.50", 2), ("12", 0), ("1E+2", 0), ("0.000000000001", 12)]
)
def test_decimals_of(value: str, expected: int) -> None:
    assert decimals_of(Decimal(value)) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("12.500", "12.5"), ("1E+3", "1000"), ("0.00000001", "0.00000001"), ("-0.0", "0")],
)
def test_format_decimal_never_uses_an_exponent(value: str, expected: str) -> None:
    assert format_decimal(Decimal(value)) == expected


class _In(BaseModel):
    x: DecimalString


@pytest.mark.parametrize(
    "bad",
    [
        *(12.5, 12, True, None),  # JSON numbers, booleans and null
        *("1e3", "1E+3", "12.", ".5", "+1", " 1", "1\n", "1,000", "NaN", "Infinity"),
        *("1" * 21, "0." + "1" * 13),  # more than 20 digits before or 12 after the point
    ],
)
def test_numbers_and_non_plain_strings_are_refused(bad: object) -> None:
    with pytest.raises(ValidationError):
        _In.model_validate({"x": bad})


def test_plain_strings_are_parsed_exactly() -> None:
    assert _In.model_validate({"x": "0.1"}).x == Decimal("0.1")
    assert _In.model_validate({"x": "-" + "9" * 20 + "." + "9" * 12}).x.as_tuple().exponent == -12


def test_money_amount_is_written_as_a_string_with_its_digits() -> None:
    money = Money(amount=Decimal("1234.50"), currency="USD")
    assert money.model_dump(mode="json") == {"amount": "1234.50", "currency": "USD"}
    assert Money(amount=Decimal("1500"), currency="JPY").model_dump(mode="json")["amount"] == "1500"


@pytest.mark.parametrize(
    "payload",
    [
        {"amount": 12.5, "currency": "USD"},
        {"amount": "1", "currency": "usd"},
        {"amount": "1", "currency": "USD", "fx": "1"},
    ],
)
def test_money_rejects_numbers_bad_codes_and_extra_fields(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Money.model_validate(payload)
