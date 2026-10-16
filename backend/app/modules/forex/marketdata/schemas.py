"""Typed request and response bodies of the forex market-data API (P13-T02). Prices are decimal
strings. Every quote states its type, quality, freshness, true age and the feed's status."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.money import DecimalString
from app.modules.forex.marketdata.types import INSTRUMENT_PATTERN

NOTICE = (
    "Forex information only, not advice. WealthSphere is not a broker and places no trades. "
    "Each price shows its type (tradable, indicative, delayed or simulated) and its age; a stale "
    "price is never shown as current, and a missing one is never filled in."
)
CANDLE_NOTICE = (
    "Candles as the provider published them, or built from stored one-minute candles for larger "
    "sizes. A period with no candle is absent, never filled in. Forming candles are not shown."
)
DataTypeName = Literal["tradable_quote", "indicative_rate", "delayed", "simulated"]
FeedStatusName = Literal["connected", "degraded", "disconnected"]


class ForexInstrumentOut(BaseModel):
    code: str = Field(pattern=INSTRUMENT_PATTERN, examples=["EUR_USD"])
    base: str
    quote: str
    pip_location: int = Field(description="A pip is 10 to this power of the quote currency")
    display_precision: int = Field(description="Decimals a price is shown with")
    liquidity_tier: Literal["major", "minor", "exotic"]
    default_data_type: Literal["tradable_quote", "indicative_rate"] = Field(
        description="What a licensed provider's price for this pair is by default; the "
        "development feed labels every price simulated"
    )
    spec_version: int


class InstrumentsOut(BaseModel):
    items: list[ForexInstrumentOut]
    notice: str = NOTICE


class QuoteOut(BaseModel):
    instrument: str = Field(pattern=INSTRUMENT_PATTERN)
    provider: str | None
    bid: DecimalString | None
    ask: DecimalString | None
    mid: DecimalString | None = Field(description="Derived: (bid + ask) / 2")
    mid_derived: bool = True
    ts_provider: datetime | None = Field(description="The provider's time of the price (UTC)")
    ts_received: datetime | None = Field(description="When WealthSphere received it (UTC)")
    age_seconds: int | None = Field(description="The price's true age when this was sent")
    data_type: DataTypeName | None
    quality: Literal["ok", "stale"] | None
    freshness: Literal["fresh", "stale", "unavailable"] = Field(
        description="unavailable: no usable price, and none is shown"
    )
    feed_status: FeedStatusName


class QuotesOut(BaseModel):
    as_of: datetime
    provider: str
    feed_status: FeedStatusName
    items: list[QuoteOut]
    notice: str = NOTICE


class CandleOut(BaseModel):
    ts: datetime = Field(description="The period's start (UTC)")
    open: DecimalString
    high: DecimalString
    low: DecimalString
    close: DecimalString
    volume: int | None = Field(description="Tick volume, when the provider has it")
    data_type: DataTypeName


class CandlesOut(BaseModel):
    instrument: str
    timeframe: Literal["1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W", "1M"]
    price_basis: Literal["mid", "bid", "ask"]
    provider: str
    start: datetime
    end: datetime
    items: list[CandleOut]
    truncated: bool = Field(description="True when more candles exist than were returned")
    notice: str = CANDLE_NOTICE
