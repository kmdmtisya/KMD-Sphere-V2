"""Trade risk calculator API (P13-T07.5, design section 9). Behind the forex flag; the inputs are
the caller's own hypothetical trade and nothing is stored or placed.

The pip value is never a constant: it is converted from the quote currency into the account
currency at a stored rate whose path, time and data types are returned. Every response carries
the warnings that apply and the disclosures that always apply (a stop can slip or gap)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.config import Settings
from app.core.errors import InvalidValueError
from app.core.money import CURRENCY_PATTERN, DecimalString
from app.modules.forex.api import ForexUser, SessionDep
from app.modules.forex.instruments.registry import active_instruments
from app.modules.forex.marketdata.repository import latest_quotes
from app.modules.forex.marketdata.types import INSTRUMENT_PATTERN
from app.modules.forex.risk import engine
from app.modules.forex.risk.conversion import NoConversionRate, rates_from, resolve
from app.modules.forex.risk.specs import ForexContractSpec, active_spec, values_of

router = APIRouter(prefix="/api/v1/forex", tags=["forex"])
RESPONSES = {
    **UNAUTHORIZED,
    **invalid("trade or no stored conversion rate"),
    **not_found("forex module (switched off)"),
}
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


def _spec_ref(row: ForexContractSpec) -> ForexSpecRef:
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


@router.post(
    "/risk/calculate",
    response_model=ForexRiskOut,
    summary="Position size, pip value, loss, profit, costs, margin and exposure of a trade idea",
    description="Sizes a hypothetical position so the planned loss at the stop, including costs, "
    "stays within the risk percent; the size is rounded down to the lot step. The pip value is "
    "converted into the account currency at a stored rate whose path and freshness are returned. "
    "Warnings cover limits, margin, leverage, rate quality and unreviewed specifications. Nothing "
    "is stored or placed.",
    responses=RESPONSES,
)
async def calculate(
    request: Request, body: ForexRiskRequest, _: ForexUser, session: SessionDep
) -> ForexRiskOut:
    settings: Settings = request.app.state.settings
    now = datetime.now(UTC)
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
        specification=_spec_ref(row),
        limits=ForexRiskLimits(
            max_risk_percent=limits.max_risk_percent,
            max_leverage=limits.max_leverage,
            max_margin_use_percent=limits.max_margin_use_percent,
        ),
        warnings=r.warnings,
        disclosures=list(r.disclosures),
    )


@router.get(
    "/contract-specs",
    response_model=ForexContractSpecsOut,
    summary="The contract specifications the risk calculator uses",
    description="The active, versioned specification of each active pair: contract size, lot "
    "step and limits, margin rate (and the maximum leverage it implies), commission and the "
    "slippage assumption, with the review status.",
    responses={**UNAUTHORIZED, **not_found("forex module (switched off)")},
)
async def contract_specs(_: ForexUser, session: SessionDep) -> ForexContractSpecsOut:
    items = []
    for pair in await active_instruments(session):
        row = await active_spec(session, pair.code)
        if row is None:
            continue
        ref = _spec_ref(row)
        items.append(
            ForexContractSpecOut(
                instrument=row.instrument,
                version=row.version,
                contract_size=row.contract_size,
                lot_step=row.lot_step,
                min_lots=row.min_lots,
                max_lots=row.max_lots,
                margin_rate=row.margin_rate,
                max_leverage=(Decimal(1) / row.margin_rate).quantize(Decimal("0.01")),
                commission_per_lot_side=row.commission_per_lot_side,
                slippage_pips=row.slippage_pips,
                review_status=ref.review_status,
                reviewed_by=ref.reviewed_by,
                reviewed_at=ref.reviewed_at,
            )
        )
    return ForexContractSpecsOut(items=items)
