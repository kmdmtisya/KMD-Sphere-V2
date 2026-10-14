"""Typed responses of the forex analysis API (P13-T03). Prices and indicator values are decimal
strings (rounded half-up to 8 places for display); `null` means "not defined here" (warm-up or an
undefined ratio), never zero."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.money import DecimalString

NOTICE = (
    "Computed by the backend from stored candles with fixed, documented formulas. Descriptive "
    "only: an indicator or pattern is not a forecast, a probability or advice."
)
Basis = Literal["mid", "bid", "ask"]
Frame = Literal["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W", "1M"]


class Coverage(BaseModel):
    instrument: str
    timeframe: Frame
    price_basis: Basis
    provider: str
    as_of: datetime = Field(description="When the analysis was computed (UTC)")
    data_types: list[str] = Field(
        description="Data types of the candles used (for example simulated)"
    )
    bars: int
    partial_bars: int = Field(
        description="Bars aggregated from fewer one-minute candles than a full period"
    )
    forming_excluded: int = Field(description="Periods still open that were left out")
    truncated: bool = Field(description="True when more bars exist than were analysed")
    notice: str = NOTICE


class IndicatorSeries(BaseModel):
    name: str = Field(examples=["macd:12,26,9"])
    outputs: dict[str, list[DecimalString | None]]
    first_defined_index: int = Field(
        description="Index of the first bar with a value; earlier ones are null"
    )


class IndicatorsOut(Coverage):
    timestamps: list[datetime]
    series: list[IndicatorSeries]


class SwingOut(BaseModel):
    ts: datetime
    kind: Literal["high", "low"]
    price: DecimalString
    confirmed_ts: datetime


class LevelOut(BaseModel):
    price: DecimalString
    role: Literal["support", "resistance"] = Field(description="Relative to the last close")
    touches: int
    first_ts: datetime
    last_ts: datetime
    established_ts: datetime


class BreakoutOut(BaseModel):
    ts: datetime
    level_price: DecimalString
    direction: Literal["up", "down"]


class TrendlineOut(BaseModel):
    kind: Literal["support", "resistance"]
    first_ts: datetime
    second_ts: datetime
    slope_per_bar: DecimalString
    value_at_last: DecimalString
    intact: bool
    channel_upper_at_last: DecimalString
    channel_lower_at_last: DecimalString


class StructureOut(Coverage):
    tolerance: DecimalString = Field(
        description="Cluster tolerance: half the ATR(14) at the last bar"
    )
    swings: list[SwingOut]
    levels: list[LevelOut]
    breakouts: list[BreakoutOut]
    trendlines: list[TrendlineOut]


class PatternOut(BaseModel):
    rule: str = Field(examples=["bullish_engulfing"])
    category: Literal["reversal", "continuation", "indecision", "consolidation", "breakout"]
    bias: Literal["bullish", "bearish", "neutral"] = Field(
        description="The shape's reading, not a forecast"
    )
    timestamps: list[datetime] = Field(description="The candles involved, oldest first")


class PatternsOut(Coverage):
    patterns: list[PatternOut]
