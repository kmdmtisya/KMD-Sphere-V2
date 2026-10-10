"""The initial asset classes and the rules for their metadata.

A class's `metadata_schema` lists the facts an asset of that class may carry:

    {"fields": {"<key>": {"type": "string|decimal|date|integer|boolean", "required": bool}}}

Adding a class is a new row (and a data migration that inserts it), never a schema change.
Migration 0005 seeds `INITIAL_CLASSES`; a test keeps the two identical.

The implementation guide lists 15 classes and combines "Private Business/Private Equity". They are
split here (16 classes) because they are valued differently: a share of an operating company
versus units in a fund with commitments and vintages."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

FieldType = str  # "string" | "decimal" | "date" | "integer" | "boolean"
FIELD_TYPES = frozenset({"string", "decimal", "date", "integer", "boolean"})
MAX_STRING = 200


@dataclass(frozen=True)
class ClassDefinition:
    code: str
    name: str
    valuation_mode: str  # "market" or "manual"
    fields: dict[str, tuple[FieldType, bool]]  # key -> (type, required)

    @property
    def metadata_schema(self) -> dict[str, Any]:
        return {
            "fields": {
                key: {"type": kind, "required": required}
                for key, (kind, required) in self.fields.items()
            }
        }


S, D, DT, INT = "string", "decimal", "date", "integer"
INITIAL_CLASSES: tuple[ClassDefinition, ...] = (
    ClassDefinition(
        "stock",
        "Stocks",
        "market",
        {"exchange": (S, False), "isin": (S, False), "sector": (S, False)},
    ),
    ClassDefinition(
        "etf",
        "ETFs",
        "market",
        {"exchange": (S, False), "isin": (S, False), "expense_ratio": (D, False)},
    ),
    ClassDefinition(
        "bond",
        "Bonds",
        "market",
        {
            "issuer": (S, False),
            "isin": (S, False),
            "coupon_rate": (D, False),
            "maturity_date": (DT, False),
            "face_value": (D, False),
        },
    ),
    ClassDefinition(
        "money_market_fund",
        "Money market funds",
        "manual",
        {"fund_manager": (S, False), "yield_rate": (D, False)},
    ),
    ClassDefinition(
        "fixed_deposit",
        "Fixed deposits",
        "manual",
        {
            "institution": (S, False),
            "interest_rate": (D, True),
            "start_date": (DT, False),
            "maturity_date": (DT, True),
        },
    ),
    ClassDefinition(
        "mutual_fund",
        "Mutual funds",
        "market",
        {"fund_manager": (S, False), "isin": (S, False), "expense_ratio": (D, False)},
    ),
    ClassDefinition(
        "reit",
        "REITs",
        "market",
        {"exchange": (S, False), "isin": (S, False), "sector": (S, False)},
    ),
    ClassDefinition(
        "real_estate",
        "Real estate",
        "manual",
        {"property_type": (S, False), "location": (S, False), "ownership_percent": (D, False)},
    ),
    ClassDefinition("cryptocurrency", "Cryptocurrency", "market", {"network": (S, False)}),
    ClassDefinition("commodity", "Commodities", "market", {"unit": (S, False)}),
    ClassDefinition(
        "pension",
        "Pension and retirement",
        "manual",
        {"provider": (S, False), "scheme_type": (S, False)},
    ),
    ClassDefinition(
        "sacco",
        "SACCO and co-operative holdings",
        "manual",
        {"institution": (S, False), "share_type": (S, False)},
    ),
    ClassDefinition(
        "private_business",
        "Private business",
        "manual",
        {"ownership_percent": (D, False), "registration_country": (S, False)},
    ),
    ClassDefinition(
        "private_equity",
        "Private equity",
        "manual",
        {"fund_manager": (S, False), "vintage_year": (INT, False), "commitment": (D, False)},
    ),
    ClassDefinition(
        "cash",
        "Cash and savings",
        "manual",
        {"institution": (S, False), "account_type": (S, False)},
    ),
    ClassDefinition("custom", "Custom assets", "manual", {"description": (S, False)}),
)


class MetadataError(ValueError):
    pass


def validate_metadata(schema: dict[str, Any], values: dict[str, Any]) -> dict[str, Any]:
    """Checks `values` against a class's metadata schema and returns their stored form.

    Decimals are stored as plain strings (never floats), dates as ISO strings. Unknown keys and
    missing required keys are refused."""
    fields: dict[str, dict[str, Any]] = schema.get("fields", {})
    unknown = sorted(set(values) - set(fields))
    if unknown:
        raise MetadataError(f"unknown metadata: {', '.join(unknown)}")
    missing = sorted(k for k, f in fields.items() if f.get("required") and values.get(k) is None)
    if missing:
        raise MetadataError(f"required metadata missing: {', '.join(missing)}")
    return {
        key: _coerce(key, fields[key]["type"], value)
        for key, value in values.items()
        if value is not None
    }


def _coerce(key: str, kind: str, value: Any) -> Any:
    if kind == "string":
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_STRING:
            raise MetadataError(f"{key} must be text of 1 to {MAX_STRING} characters")
        return value.strip()
    if kind == "decimal":
        # Strings only: a JSON number may already have been rounded through a float.
        if not isinstance(value, str):
            raise MetadataError(f"{key} must be a decimal number written as a string")
        try:
            number = Decimal(value)
        except InvalidOperation as e:
            raise MetadataError(f"{key} is not a decimal number") from e
        if not number.is_finite():
            raise MetadataError(f"{key} is not a decimal number")
        return format(number, "f")
    if kind == "date":
        if not isinstance(value, str):
            raise MetadataError(f"{key} must be a date (YYYY-MM-DD)")
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError as e:
            raise MetadataError(f"{key} must be a date (YYYY-MM-DD)") from e
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise MetadataError(f"{key} must be a whole number")
        return value
    if kind == "boolean":
        if not isinstance(value, bool):
            raise MetadataError(f"{key} must be true or false")
        return value
    raise MetadataError(f"{key} has an unsupported type")  # a schema error, not user input
