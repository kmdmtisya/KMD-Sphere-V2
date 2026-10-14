"""Opportunity Ranking API (P13-T06.5, design sections 8.3 and 8.4). Reference data, the same for
every signed-in user, behind the forex flag.

Every item is a **research candidate**: a setup that a published rule found in stored prices,
scored by a published formula with every factor shown. Not advice, not a recommendation to buy
or sell, not a probability of profit. Levels are illustrative and timestamped."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.authz import ResourceNotFoundError
from app.core.money import DecimalString
from app.modules.forex.api import ForexUser, SessionDep
from app.modules.forex.instruments.models import ForexInstrument
from app.modules.forex.instruments.registry import active_instruments
from app.modules.forex.marketdata.types import INSTRUMENT_PATTERN, Timeframe
from app.modules.forex.signals.ranking import Candidate, rank
from app.modules.forex.signals.scoring import WEIGHTS_VERSION
from app.modules.forex.signals.service import pair_candidates

router = APIRouter(prefix="/api/v1/forex", tags=["forex"])
RESPONSES = {
    **UNAUTHORIZED,
    **invalid("request"),
    **not_found("instrument, or the forex module is switched off"),
}
NOTICE = (
    "Research candidates ranked by a published formula from stored prices. Not advice, not a "
    "recommendation to buy or sell, and not a probability of profit. Levels are illustrative: "
    "markets can move past any level, and stops do not cap a loss. WealthSphere places no trades."
)
LABEL = "Research candidate"
Frame = Literal["5m", "15m", "1H", "4H", "1D"]
SetupName = Literal[
    "trend_continuation", "breakout", "reversal", "range", "momentum", "mean_reversion"
]
Risk = Literal["low", "medium", "medium_high", "high"]
Tier = Literal["major", "minor", "exotic"]


class ForexFactorOut(BaseModel):
    name: str
    value: DecimalString = Field(description="0 to 1")
    weight: DecimalString
    contribution: DecimalString
    detail: str


class Levels(BaseModel):
    as_of: datetime = Field(description="The closed bar the levels come from (UTC)")
    entry: DecimalString = Field(description="Illustrative: the last close")
    stop: DecimalString = Field(description="Illustrative invalidation level")
    target: DecimalString = Field(description="Illustrative target from the rule")
    risk_pips: DecimalString
    reward_pips: DecimalString
    risk_reward: DecimalString


class Costs(BaseModel):
    spread_pips: DecimalString | None = Field(
        description="From the latest fresh quote; null when unknown"
    )
    spread_share_of_risk: DecimalString | None
    note: str = "Spread only: swaps, commissions and slippage are not included."


class ForexFreshness(BaseModel):
    bar_as_of: datetime
    bar_age_seconds: int
    quote_age_seconds: int | None
    data_types: list[str]


class ForecastRef(BaseModel):
    horizon: str
    prob_up: DecimalString
    calibration: Literal["Calibrated", "Requires calibration"]
    model: str
    model_version: str


class ForexOpportunityOut(BaseModel):
    rank: int | None
    label: str = LABEL
    instrument: str
    tier: Tier
    market_condition: Literal[
        "trending", "consolidating", "high_volatility", "momentum_strengthening", "mixed"
    ]
    opportunity_type: SetupName
    scenario: Literal["Bullish scenario", "Bearish scenario"]
    risk: Risk
    score: DecimalString = Field(
        description="0 to 100: ranks research candidates; not a probability"
    )
    levels: Levels
    factors: list[ForexFactorOut]
    adjustments: list[str] = Field(description="Demotions or exclusions, each with its reason")
    assumptions: list[str]
    risks: list[str]
    evidence: list[str] = Field(description="What the rule saw")
    costs: Costs
    freshness: ForexFreshness
    forecast: ForecastRef | None
    rule: str
    rule_version: int


class RankingOut(BaseModel):
    timeframe: Frame
    as_of: datetime
    weights_version: int
    weights: dict[str, DecimalString]
    items: list[ForexOpportunityOut]
    excluded: list[ForexOpportunityOut]
    notice: str = NOTICE


class SetupsOut(BaseModel):
    instrument: str
    timeframe: Frame
    as_of: datetime
    items: list[ForexOpportunityOut]
    notice: str = NOTICE


def _out(c: Candidate, position: int | None) -> ForexOpportunityOut:
    s, q = c.setup, Decimal(1).scaleb(-c.precision)
    return ForexOpportunityOut(
        rank=position,
        instrument=c.instrument,
        tier=c.tier,
        market_condition=c.condition,
        opportunity_type=s.rule,
        scenario="Bullish scenario" if s.direction == "bullish" else "Bearish scenario",
        risk=c.risk,
        score=c.score,
        levels=Levels(
            as_of=s.as_of,
            entry=s.entry.quantize(q),
            stop=s.stop.quantize(q),
            target=s.target.quantize(q),
            risk_pips=c.levels_pips["risk"],
            reward_pips=c.levels_pips["reward"],
            risk_reward=c.levels_pips["risk_reward"],
        ),
        factors=[
            ForexFactorOut(
                name=f.name,
                value=f.value,
                weight=f.weight,
                contribution=f.contribution.quantize(Decimal("0.0001")),
                detail=f.detail,
            )
            for f in c.factors
        ],
        adjustments=c.adjustments,
        assumptions=c.assumptions,
        risks=c.risks,
        evidence=s.evidence,
        costs=Costs(spread_pips=c.spread_pips, spread_share_of_risk=c.spread_share_of_risk),
        freshness=ForexFreshness(
            bar_as_of=s.as_of,
            bar_age_seconds=int(c.bar_age.total_seconds()),
            quote_age_seconds=int(c.quote_age.total_seconds()) if c.quote_age is not None else None,
            data_types=c.data_types,
        ),
        forecast=None
        if c.forecast is None
        else ForecastRef(
            horizon=c.forecast.horizon,
            prob_up=c.forecast.prob_up,
            calibration="Calibrated" if c.forecast.calibrated else "Requires calibration",
            model=c.forecast.model_name,
            model_version=c.forecast.model_version,
        ),
        rule=s.rule,
        rule_version=s.version,
    )


@router.get(
    "/opportunities",
    response_model=RankingOut,
    summary="Opportunity Ranking: research candidates ranked by a published score",
    description="The best setup of each active pair on the timeframe, ranked by score, with the "
    "market condition, opportunity type, risk, every factor with its weight and contribution, "
    "illustrative levels, costs and freshness. Candidates with stale data are listed under "
    "`excluded`. Filters: setup, risk, tier.",
    responses=RESPONSES,
)
async def opportunities(
    request: Request,
    _: ForexUser,
    session: SessionDep,
    timeframe: Frame = "1H",
    setup: SetupName | None = None,
    risk: Risk | None = None,
    tier: Tier | None = None,
) -> RankingOut:
    settings = request.app.state.settings
    now = datetime.now(UTC)
    per_pair = []
    for spec in await active_instruments(session):
        if tier is not None and spec.liquidity_tier != tier:
            continue
        found = await pair_candidates(session, settings, spec, Timeframe(timeframe), now)
        if setup is not None:
            found = [c for c in found if c.setup.rule == setup]
        if risk is not None:
            found = [c for c in found if c.risk == risk]
        per_pair.append(found)
    ranked, excluded = rank(per_pair)
    return RankingOut(
        timeframe=timeframe,
        as_of=now,
        weights_version=WEIGHTS_VERSION,
        weights=settings.forex_signal_weights,
        items=[_out(c, k) for k, c in enumerate(ranked, start=1)],
        excluded=[_out(c, None) for c in excluded],
    )


@router.get(
    "/opportunities/setups",
    response_model=SetupsOut,
    summary="Every setup found for one pair, with its full explanation",
    description="All setups that hold on the latest closed bar of the pair, best first. "
    "Research candidates only; levels are illustrative.",
    responses=RESPONSES,
)
async def pair_setups(
    request: Request,
    _: ForexUser,
    session: SessionDep,
    instrument: Annotated[str, Query(pattern=INSTRUMENT_PATTERN)],
    timeframe: Frame = "1H",
) -> SetupsOut:
    if instrument not in {r.code for r in await active_instruments(session)}:
        raise ResourceNotFoundError("forex instrument")
    spec = await session.get(ForexInstrument, instrument)
    if spec is None:  # pragma: no cover - checked as active just above
        raise ResourceNotFoundError("forex instrument")
    now = datetime.now(UTC)
    found = await pair_candidates(
        session, request.app.state.settings, spec, Timeframe(timeframe), now
    )
    return SetupsOut(
        instrument=instrument, timeframe=timeframe, as_of=now, items=[_out(c, None) for c in found]
    )
