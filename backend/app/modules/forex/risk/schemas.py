"""Schemas of the trade risk calculator (P13-T07.5): the request, the response and the contract
specifications. Shared by the API and the Forex Copilot's `calculate_trade_risk` tool (P13-T10)."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from app.core.money import CURRENCY_PATTERN, DecimalString
from app.modules.forex.marketdata.types import INSTRUMENT_PATTERN

NOTICE = (
    "A position-size and risk calculator for study and paper trading. Not advice and not a "
    "recommendation; WealthSphere places no trades. Values are estimates."
)
RATE_PLACES = Decimal("1E-10")


class ForexRiskRequest(BaseModel):
    instrument: str = Field(pattern=INSTRUMENT_PATTERN, examples=["EUR_USD"])
    direction: Literal["long", "short"]
    entry: DecimalString
    stop: DecimalString = Field(
        description="Stop-loss level; it does not cap the loss (gaps, slippage)"
    )
    target: DecimalString | None = Field(default=None, description="Optional take-profit level")
    balance: DecimalString = Field(description="Account balance in the account currency")
    account_currency: str = Field(pattern=CURRENCY_PATTERN, examples=["USD"])
    risk_percent: DecimalString = Field(description="Share of the balance to risk, in percent")


class ForexPositionSize(BaseModel):
    units: DecimalString = Field(description="Base-currency units")
    lots: DecimalString = Field(description="Standard lots, a multiple of the lot step")
    status: Literal["sized", "below_minimum", "capped_at_maximum"]


class ForexPipValue(BaseModel):
    pip_size: DecimalString
    per_lot_quote_currency: DecimalString
    per_lot_account_currency: DecimalString
    quote_currency: str


class ForexLossProfit(BaseModel):
    risk_amount: DecimalString = Field(description="Balance x risk percent")
    stop_pips: DecimalString
    target_pips: DecimalString | None
    loss_before_costs: DecimalString
    loss_after_costs: DecimalString = Field(
        description="Planned loss at the stop with costs; gaps can exceed it"
    )
    profit_before_costs: DecimalString | None
    profit_after_costs: DecimalString | None
    risk_reward_before_costs: DecimalString | None
    risk_reward_after_costs: DecimalString | None


class ForexCosts(BaseModel):
    spread: DecimalString
    slippage: DecimalString
    commission: DecimalString
    total: DecimalString
    note: str = (
        "Spread from the latest fresh quote (zero and warned when unknown), slippage and "
        "commission from the contract specification, each for entry and exit. Swaps and "
        "financing are not included."
    )


class ForexMargin(BaseModel):
    notional: DecimalString
    margin: DecimalString
    margin_use_percent: DecimalString
    position_leverage: DecimalString = Field(description="Notional / balance")
    max_leverage: DecimalString = Field(description="1 / margin rate of the specification")


class ForexExposure(BaseModel):
    currency: str
    amount: DecimalString = Field(description="Signed: positive long, negative short")


class ForexConversion(BaseModel):
    rate: DecimalString = Field(description="1 unit of the quote currency in the account currency")
    path: str
    as_of: datetime | None
    data_types: list[str]
    stale: bool


class ForexSpecRef(BaseModel):
    version: int
    review_status: Literal["unreviewed", "reviewed"]
    reviewed_by: str | None
    reviewed_at: datetime | None


class ForexRiskLimits(BaseModel):
    max_risk_percent: DecimalString
    max_leverage: DecimalString
    max_margin_use_percent: DecimalString


class ForexRiskOut(BaseModel):
    instrument: str
    direction: Literal["long", "short"]
    account_currency: str
    size: ForexPositionSize
    pip_value: ForexPipValue
    outcome: ForexLossProfit
    costs: ForexCosts
    margin: ForexMargin
    account_impact_percent: DecimalString = Field(description="Loss after costs / balance")
    exposure: list[ForexExposure]
    exposure_percent: DecimalString
    conversion: ForexConversion
    specification: ForexSpecRef
    limits: ForexRiskLimits
    warnings: list[str]
    disclosures: list[str]
    notice: str = NOTICE


class ForexContractSpecOut(BaseModel):
    instrument: str
    version: int
    contract_size: DecimalString
    lot_step: DecimalString
    min_lots: DecimalString
    max_lots: DecimalString
    margin_rate: DecimalString
    max_leverage: DecimalString
    commission_per_lot_side: DecimalString = Field(description="Quote currency")
    slippage_pips: DecimalString = Field(description="Assumed per fill")
    review_status: Literal["unreviewed", "reviewed"]
    reviewed_by: str | None
    reviewed_at: datetime | None


class ForexContractSpecsOut(BaseModel):
    items: list[ForexContractSpecOut]
    note: str = "Unreviewed specifications are development defaults, not a broker's terms."
