"""Response schemas for /api/v1/fx-rates."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.money import DecimalString


class FxQuoteOut(BaseModel):
    base_currency: str
    quote_currency: str
    rate: DecimalString = Field(description="1 unit of base_currency in quote_currency units")
    as_of: datetime = Field(description="When the rate was valid (the provider's timestamp)")
    provider: str
    data_type: Literal["indicative_rate"] = Field(
        default="indicative_rate",
        description="Reference rates for reporting-currency conversion, not tradable quotes: show "
        "them as indicative and never use them for transactions (ADR-0014)",
    )
    inverted: bool = Field(description="Derived as 1 / rate from the opposite pair")
    stale: bool = Field(description="Older than one day (provisional threshold, DEC-26)")
    rule: Literal["historical", "latest"] = Field(
        description="`historical`: the rate for the given date; `latest`: the most recent rate"
    )
