"""The trade risk calculation from stored data (P13-T07): the active pair and its contract
specification, the latest quotes for the spread and the conversion rate, then the engine. Used by
the API and by the Forex Copilot's `calculate_trade_risk` tool (P13-T10), so both give the same
figures."""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import InvalidValueError
from app.modules.forex.instruments.registry import active_instruments
from app.modules.forex.marketdata.repository import latest_quotes
from app.modules.forex.risk import engine
from app.modules.forex.risk.conversion import NoConversionRate, rates_from, resolve
from app.modules.forex.risk.schemas import (
    RATE_PLACES,
    ForexConversion,
    ForexCosts,
    ForexExposure,
    ForexLossProfit,
    ForexMargin,
    ForexPipValue,
    ForexPositionSize,
    ForexRiskLimits,
    ForexRiskOut,
    ForexRiskRequest,
    ForexSpecRef,
)
from app.modules.forex.risk.specs import ForexContractSpec, active_spec, values_of


def spec_ref(row: ForexContractSpec) -> ForexSpecRef:
    return ForexSpecRef(
        version=row.version,
        review_status="reviewed" if row.review_status == "reviewed" else "unreviewed",
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
    )


def limits_of(settings: Settings) -> engine.Limits:
    return engine.Limits(
        max_risk_percent=settings.forex_risk_max_percent,
        max_leverage=settings.forex_risk_max_leverage,
        max_margin_use_percent=settings.forex_risk_max_margin_use_percent,
    )


async def calculate_trade(
    session: AsyncSession, settings: Settings, body: ForexRiskRequest, now: datetime
) -> ForexRiskOut:
    stale_after = timedelta(seconds=settings.forex_quote_stale_seconds)
    pairs = await active_instruments(session)
    pair = next((p for p in pairs if p.code == body.instrument), None)
    if pair is None:
        raise InvalidValueError("unknown or inactive instrument")
    row = await active_spec(session, pair.code)
    if row is None:
        raise InvalidValueError("no contract specification for this instrument")
    quotes = await latest_quotes(
        session,
        settings.forex_provider,
        [p.code for p in pairs],
        now - timedelta(days=settings.forex_quote_lookback_days),
    )
    rates = rates_from(quotes, {p.code for p in pairs if p.liquidity_tier == "exotic"})
    try:
        conversion = resolve(pair.quote, body.account_currency, rates, now, stale_after)
    except NoConversionRate as exc:
        raise InvalidValueError(str(exc)) from exc
    own = quotes.get(pair.code)
    fresh = own is not None and now - own.ts_provider <= stale_after and own.ask >= own.bid
    spread = own.ask - own.bid if own is not None and fresh else None
    try:
        trade = engine.Trade(
            instrument=pair.code,
            direction=body.direction,
            entry=body.entry,
            stop=body.stop,
            target=body.target,
            balance=body.balance,
            account_currency=body.account_currency,
            risk_percent=body.risk_percent,
            spread=spread,
        )
    except ValueError as exc:
        raise InvalidValueError(str(exc)) from exc
    limits = limits_of(settings)
    r = engine.calculate(
        trade,
        values_of(row),
        pair.pip_location,
        pair.display_precision,
        conversion,
        limits,
        reviewed=row.review_status == "reviewed",
        liquidity_tier=pair.liquidity_tier,
    )
    return ForexRiskOut(
        instrument=pair.code,
        direction=body.direction,
        account_currency=body.account_currency,
        size=ForexPositionSize(units=r.units, lots=r.lots, status=r.status),
        pip_value=ForexPipValue(
            pip_size=r.pip_size,
            per_lot_quote_currency=r.pip_value_per_lot_quote,
            per_lot_account_currency=r.pip_value_per_lot_account,
            quote_currency=pair.quote,
        ),
        outcome=ForexLossProfit(
            risk_amount=r.risk_amount,
            stop_pips=r.stop_pips,
            target_pips=r.target_pips,
            loss_before_costs=r.loss_before_costs,
            loss_after_costs=r.loss_after_costs,
            profit_before_costs=r.profit_before_costs,
            profit_after_costs=r.profit_after_costs,
            risk_reward_before_costs=r.risk_reward_before_costs,
            risk_reward_after_costs=r.risk_reward_after_costs,
        ),
        costs=ForexCosts(**r.costs),
        margin=ForexMargin(
            notional=r.notional,
            margin=r.margin,
            margin_use_percent=r.margin_use_percent,
            position_leverage=r.position_leverage,
            max_leverage=r.max_leverage,
        ),
        account_impact_percent=r.account_impact_percent,
        exposure=[ForexExposure(currency=c, amount=a) for c, a in r.exposure.items()],
        exposure_percent=r.exposure_percent,
        conversion=ForexConversion(
            rate=conversion.rate.quantize(RATE_PLACES),
            path=conversion.path,
            as_of=conversion.as_of,
            data_types=list(conversion.data_types),
            stale=conversion.stale,
        ),
        specification=spec_ref(row),
        limits=ForexRiskLimits(
            max_risk_percent=limits.max_risk_percent,
            max_leverage=limits.max_leverage,
            max_margin_use_percent=limits.max_margin_use_percent,
        ),
        warnings=r.warnings,
        disclosures=list(r.disclosures),
    )
