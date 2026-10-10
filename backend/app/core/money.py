"""Money, quantities and rates on the wire (docs/api-conventions.md, ADR-0003, ADR-0006).

- Every amount, quantity and rate travels as a **string**. JSON numbers are refused on input,
  because a number may already have passed through binary floating point.
- Money is `{"amount": "1234.50", "currency": "USD"}`.
- Posted ledger amounts use the currency's ISO 4217 minor units (USD 2, JPY 0, KWD 3).
  Inputs with more decimals are refused rather than silently rounded.
- Rounding, where a value is derived, is ROUND_HALF_UP (ADR-0006)."""

import re
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, PlainSerializer, WithJsonSchema

DECIMAL_PATTERN = r"^-?\d{1,20}(\.\d{1,12})?$"
CURRENCY_PATTERN = r"^[A-Z]{3}$"

# ISO 4217 minor units for currencies that differ from the default of 2. The full currency table
# arrives with P11 (multi-currency); until then, any other code uses 2.
_MINOR_UNITS: dict[str, int] = {
    "BIF": 0, "CLP": 0, "DJF": 0, "GNF": 0, "ISK": 0, "JPY": 0, "KMF": 0, "KRW": 0,
    "PYG": 0, "RWF": 0, "UGX": 0, "UYI": 0, "VND": 0, "VUV": 0, "XAF": 0, "XOF": 0,
    "XPF": 0,
    "BHD": 3, "IQD": 3, "JOD": 3, "KWD": 3, "LYD": 3, "OMR": 3, "TND": 3,
}  # fmt: skip


def minor_units(currency: str) -> int:
    return _MINOR_UNITS.get(currency, 2)


def decimals_of(value: Decimal) -> int:
    exponent = value.as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def round_half_up(value: Decimal, places: int) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


_DECIMAL = re.compile(DECIMAL_PATTERN)


def _parse(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if not isinstance(value, str):
        raise ValueError('must be a decimal number written as a string, e.g. "12.50"')
    if not _DECIMAL.fullmatch(value):
        raise ValueError(
            "must be a plain decimal number with at most 20 digits before and 12 after the point"
        )
    return Decimal(value)


def format_decimal(value: Decimal) -> str:
    """Plain notation without trailing zeros (never an exponent)."""
    text = format(value.normalize(), "f")
    return text if text != "-0" else "0"


DecimalString = Annotated[
    Decimal,
    BeforeValidator(_parse),
    PlainSerializer(format_decimal, return_type=str),
    WithJsonSchema({"type": "string", "pattern": DECIMAL_PATTERN, "examples": ["1234.50"]}),
]


MoneyAmount = Annotated[
    Decimal,
    BeforeValidator(_parse),
    PlainSerializer(lambda v: format(v, "f"), return_type=str),
    WithJsonSchema({"type": "string", "pattern": DECIMAL_PATTERN, "examples": ["1234.50"]}),
]


class Money(BaseModel):
    """An amount in a currency. The amount is a string, written with the currency's minor units
    in responses ("1234.50", "1500" for JPY)."""

    model_config = ConfigDict(extra="forbid")

    amount: MoneyAmount
    currency: str = Field(pattern=CURRENCY_PATTERN, description="ISO 4217 code")

    @classmethod
    def of(cls, amount: Decimal, currency: str) -> "Money":
        """Money rounded for presentation to the currency's minor units."""
        return cls(amount=round_half_up(amount, minor_units(currency)), currency=currency)


def percentages(parts: list[Decimal], places: int = 2) -> list[Decimal] | None:
    """Shares of the total in percent, rounded to `places` decimals and allocated by largest
    remainder so they add up to exactly 100 (ADR-0006). None when the total is not positive or a
    part is negative (a percentage share would be meaningless)."""
    total = sum(parts, Decimal(0))
    if not parts or total <= 0 or any(p < 0 for p in parts):
        return None
    unit = Decimal(1).scaleb(-places)
    exact = [p * 100 / total for p in parts]
    floored = [e.quantize(unit, rounding=ROUND_FLOOR) for e in exact]
    shortfall = int((Decimal(100) - sum(floored, Decimal(0))) / unit)
    # Largest remainders first; ties go to the earlier part, so the result is deterministic.
    order = sorted(range(len(parts)), key=lambda i: (-(exact[i] - floored[i]), i))
    for i in order[:shortfall]:
        floored[i] += unit
    return floored
