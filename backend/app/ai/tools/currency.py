"""Currency tools (P11-T08): current and historical rates, conversion, a portfolio's value in a
currency, and a portfolio's currency exposure.

Every figure comes from the same services as the API, so a tool's answer equals the API's for the
same snapshot: current rates and conversions use the current rate snapshot (its id is returned),
historical ones the rate valid at the end of that day. Each result carries the rate, its providers,
its time and its status; a pair without a usable rate is "not found", never estimated. Portfolio
tools are owner-scoped like the API (another user's portfolio does not exist). Conversions an
answer relies on are recorded in the conversion audit (DEC-28: `ai_answer`)."""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.ai.tools.base import Tool, ToolArguments, ToolContext, ToolData
from app.ai.tools.registry import ToolRegistry
from app.core.authz import ResourceNotFoundError
from app.core.config import get_settings
from app.core.errors import InvalidValueError
from app.core.money import CURRENCY_PATTERN, DecimalString, ExactRate, Money, round_half_up
from app.modules.fx.history import RateConcept
from app.modules.fx.models import FxConversionAudit
from app.modules.fx.reporting import ReportingContext
from app.modules.fx.schemas import ReportingOut
from app.modules.fx.snapshot import Snapshot, SnapshotService, convert
from app.modules.fx.status import StatusPolicy
from app.modules.market_data.fx import FxRateUnavailable, end_of_day
from app.modules.market_data.fx_context import current_rates
from app.modules.market_data.service import FxService
from app.modules.portfolio.analytics_views import allocation_out
from app.modules.portfolio.summary_schemas import SummaryOut
from app.modules.portfolio.summary_service import SummaryService

Currency = Annotated[str, StringConstraints(pattern=CURRENCY_PATTERN)]
Status = Literal["current", "cached", "stale", "unavailable"]
NOTICE = "Indicative rate for information; not a quote for a transaction."


def _pivot() -> str:
    return get_settings().fx_pivot_currency


def _policy() -> StatusPolicy:
    return StatusPolicy.from_settings(get_settings())


async def _check_supported(ctx: ToolContext, *codes: str) -> dict[str, int]:
    places = await SnapshotService(ctx.session, _pivot()).currencies()
    for code in codes:
        if code not in places:
            raise InvalidValueError(f"{code} is not a supported currency")
    return places


# ------------------------------------------------------------------------------------- rates
class FxPairArguments(ToolArguments):
    base: Currency = Field(description="ISO 4217 code: 1 unit of this currency ...")
    quote: Currency = Field(description="... in this currency")


class HistoricalRateArguments(FxPairArguments):
    on: date = Field(description="The day (UTC); the rate valid at the end of that day")


class FxRateResult(ToolData):
    base: str
    quote: str
    rate: ExactRate = Field(description="1 base = rate quote")
    path: list[str] | None = Field(description="Currencies a derived rate went through")
    rate_timestamp: datetime | None
    providers: list[str]
    status: Status
    concept: Literal["current_reporting", "historical_valuation"]
    snapshot_id: str | None
    notice: str = NOTICE


async def get_current_fx_rate(ctx: ToolContext, args: FxPairArguments) -> FxRateResult:
    await _check_supported(ctx, args.base, args.quote)
    snapshot = await SnapshotService(ctx.session, _pivot()).current()
    try:
        resolved = snapshot.rate(args.base, args.quote)
    except FxRateUnavailable:
        raise ResourceNotFoundError("fx rate") from None
    status = resolved.status(_policy(), ctx.now())
    return FxRateResult(
        as_of=resolved.rate_timestamp or ctx.now(),
        complete=status.value == "current",
        base=args.base,
        quote=args.quote,
        rate=resolved.rate,
        path=list(resolved.path) if resolved.path else None,
        rate_timestamp=resolved.rate_timestamp,
        providers=resolved.providers,
        status=status.value,
        concept=RateConcept.CURRENT_REPORTING.value,
        snapshot_id=str(snapshot.id),
    )


async def get_historical_fx_rate(ctx: ToolContext, args: HistoricalRateArguments) -> FxRateResult:
    await _check_supported(ctx, args.base, args.quote)
    if args.on > ctx.now().date():
        raise InvalidValueError("The day is in the future.")
    try:
        q = await FxService(ctx.session, _pivot()).quote(args.base, args.quote, end_of_day(args.on))
    except FxRateUnavailable:
        raise ResourceNotFoundError("fx rate") from None
    identity = q.provider == "identity"
    return FxRateResult(
        as_of=q.as_of,
        complete=not q.stale,
        base=args.base,
        quote=args.quote,
        rate=q.rate,
        path=list(q.path) if q.path else None,
        rate_timestamp=None if identity else q.as_of,
        providers=[] if identity else q.provider.split("+"),
        status="stale" if q.stale else "current",
        concept=RateConcept.HISTORICAL_VALUATION.value,
        snapshot_id=None,
    )


# ---------------------------------------------------------------------------------- convert
class ConvertArguments(ToolArguments):
    amount: Money = Field(description="The amount and its currency, the amount as a string")
    to: Currency = Field(description="Target currency (ISO 4217)")
    on: date | None = Field(
        default=None, description="Use the historical rate of this day; omit for today's rate"
    )


class ConversionResult(FxRateResult):
    source: Money
    converted: Money = Field(description="Rounded once, half-up, to the target's decimal places")


async def convert_currency(ctx: ToolContext, args: ConvertArguments) -> ConversionResult:
    source = args.amount.currency
    places = (await _check_supported(ctx, source, args.to))[args.to]
    if args.on is None:
        rate = await get_current_fx_rate(ctx, FxPairArguments(base=source, quote=args.to))
    else:
        rate = await get_historical_fx_rate(
            ctx, HistoricalRateArguments(base=source, quote=args.to, on=args.on)
        )
    converted = convert(args.amount.amount, rate.rate, places)
    ctx.session.add(
        FxConversionAudit(
            user_id=ctx.user_id,
            source_currency=source,
            target_currency=args.to,
            source_amount=args.amount.amount,
            converted_amount=converted,
            rate=round_half_up(rate.rate, 12),
            rate_timestamp=rate.rate_timestamp or ctx.now(),
            provider=("+".join(rate.providers) or "identity")[:32],
            snapshot_id=uuid.UUID(rate.snapshot_id) if rate.snapshot_id else None,
            conversion_type="ai_answer",
        )
    )
    await ctx.session.commit()
    return ConversionResult(
        **rate.model_dump(),
        source=args.amount,
        converted=Money(amount=converted, currency=args.to),
    )


# ------------------------------------------------------------------------- portfolio value
class PortfolioValueArguments(ToolArguments):
    portfolio_id: uuid.UUID | None = Field(
        default=None, description="One of the user's portfolios; omit for all combined"
    )
    currency: Currency | None = Field(
        default=None,
        description="Show the value in this currency; default: the portfolio's base currency "
        "(one portfolio) or the user's reporting currency (all)",
    )


class PortfolioValueResult(ToolData):
    portfolio_ids: list[uuid.UUID]
    currency: str
    total_value: Money
    holdings_value: Money
    cash: Money
    reporting: ReportingOut


async def get_portfolio_value(
    ctx: ToolContext, args: PortfolioValueArguments
) -> PortfolioValueResult:
    if args.currency is not None:
        await _check_supported(ctx, args.currency)
    snapshot: Snapshot = await SnapshotService(ctx.session, _pivot()).current()
    context = ReportingContext(snapshot, _policy())
    token = current_rates.set(context)
    try:
        service = SummaryService(ctx.session)
        summary: SummaryOut
        if args.portfolio_id is None:
            summary = await service.consolidated(ctx.user_id, args.currency)
        elif args.currency is None:
            summary = await service.portfolio(ctx.user_id, args.portfolio_id)
        else:
            summary = await service.portfolio_in(ctx.user_id, args.portfolio_id, args.currency)
    finally:
        current_rates.reset(token)
    return PortfolioValueResult(
        as_of=summary.freshness.data_as_of,
        complete=summary.freshness.complete,
        portfolio_ids=summary.portfolio_ids,
        currency=summary.currency,
        total_value=summary.total_value,
        holdings_value=summary.holdings_value,
        cash=summary.cash,
        reporting=context.out(summary.currency),
    )


# ------------------------------------------------------------------------------- exposure
class ExposureArguments(ToolArguments):
    portfolio_id: uuid.UUID = Field(description="One of the user's portfolios")


class CurrencyShare(BaseModel):
    currency: str | None
    value: Money = Field(description="In the portfolio's base currency")
    weight_percent: DecimalString | None


class ExposureResult(ToolData):
    portfolio_id: uuid.UUID
    base_currency: str
    total: Money
    exposure: list[CurrencyShare]


async def get_fx_exposure(ctx: ToolContext, args: ExposureArguments) -> ExposureResult:
    allocation = await allocation_out(ctx.session, ctx.user_id, args.portfolio_id)
    return ExposureResult(
        as_of=ctx.now(),
        complete=allocation.complete,
        portfolio_id=allocation.portfolio_id,
        base_currency=allocation.currency,
        total=allocation.total,
        exposure=[
            CurrencyShare(currency=s.key, value=s.value, weight_percent=s.weight_percent)
            for s in allocation.currency_exposure.slices
        ],
    )


# ---------------------------------------------------------------------------- registration
def register_currency_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "get_current_fx_rate",
            "Today's exchange rate between two supported currencies from WealthSphere's current "
            "rate snapshot, with provider, time, status and the path of a derived rate. "
            "Indicative, not a quote for a transaction.",
            FxPairArguments,
            FxRateResult,
            get_current_fx_rate,
        )
    )
    registry.register(
        Tool(
            "get_historical_fx_rate",
            "The exchange rate valid at the end of a past day (UTC), for past values. Not found "
            "when that day has no usable rate.",
            HistoricalRateArguments,
            FxRateResult,
            get_historical_fx_rate,
        )
    )
    registry.register(
        Tool(
            "convert_currency",
            "Convert an amount into another currency with today's rate (or a past day's), "
            "rounded to the target currency. Returns the rate, its time and providers.",
            ConvertArguments,
            ConversionResult,
            convert_currency,
        )
    )
    registry.register(
        Tool(
            "get_portfolio_value",
            "The value, holdings and cash of one of the user's portfolios or of all combined, "
            "in a chosen currency, with every rate used. Nothing is changed.",
            PortfolioValueArguments,
            PortfolioValueResult,
            get_portfolio_value,
        )
    )
    registry.register(
        Tool(
            "get_fx_exposure",
            "How one portfolio's value is split by currency (values in its base currency).",
            ExposureArguments,
            ExposureResult,
            get_fx_exposure,
        )
    )
