"""Backtest reports API (P13-T08.6). Read only: reports are made by the daily `forex_backtest`
job from stored bars and are reference data, the same for every signed-in user, behind the
forex flag. Every report is labelled `backtested`; it is a study of a published rule, not a
forecast, and is never combined with paper or live results."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Path, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.authz import ResourceNotFoundError
from app.core.money import DecimalString
from app.modules.forex.api import ForexUser, SessionDep
from app.modules.forex.backtest.report import NOTICE
from app.modules.forex.backtest.store import ForexBacktestReport
from app.modules.forex.marketdata.types import INSTRUMENT_PATTERN

router = APIRouter(prefix="/api/v1/forex", tags=["forex"])
Rule = Literal["trend_continuation", "breakout", "reversal", "range", "momentum", "mean_reversion"]
Frame = Literal["15m", "1H", "4H", "1D"]


class ForexBacktestMetrics(BaseModel):
    trades: int
    wins: int
    win_rate: DecimalString | None
    total_return: DecimalString = Field(description="A fraction: 0.05 is 5%, net of every cost")
    max_drawdown: DecimalString = Field(description="A fraction of the running peak")
    gross_profit: DecimalString
    gross_loss: DecimalString
    profit_factor: DecimalString | None = Field(description="None when there is no losing trade")
    average_trade: DecimalString | None
    expectancy_r: DecimalString | None = Field(description="Mean R multiple")
    longest_losing_streak: int
    exposure: DecimalString = Field(description="Share of bars with an open position")
    sharpe: DecimalString | None
    sortino: DecimalString | None
    costs: DecimalString


class ForexBacktestParams(BaseModel):
    max_hold: int
    reward_multiple: DecimalString | None = Field(description="None: the rule's own target")
    risk_percent: DecimalString


class ForexBacktestData(BaseModel):
    snapshot_hash: str
    bars: int
    warm_up_bars: int
    start: datetime
    end: datetime
    data_types: list[str]


class ForexBacktestCosts(BaseModel):
    spread_pips: DecimalString
    spread_source: str
    slippage_pips_per_fill: DecimalString
    commission_per_lot_side: DecimalString
    contract_specification_version: str
    contract_specification_review: Literal["reviewed", "unreviewed"]
    swaps: str


class ForexBacktestFullPeriod(BaseModel):
    label: str
    params: ForexBacktestParams
    metrics: ForexBacktestMetrics


class ForexCostScenario(BaseModel):
    scenario: str
    spread_and_commission_multiplier: DecimalString
    slippage_multiplier: DecimalString
    metrics: ForexBacktestMetrics


class ForexWalkForwardWindow(BaseModel):
    fold: int
    in_sample: list[datetime]
    out_of_sample: list[datetime]
    chosen: ForexBacktestParams
    in_sample_metrics: ForexBacktestMetrics
    out_of_sample_metrics: ForexBacktestMetrics


class ForexWalkForward(BaseModel):
    folds: int
    selection: str
    stability: DecimalString | None
    windows: list[ForexWalkForwardWindow]
    out_of_sample: ForexBacktestMetrics


class ForexBacktestBenchmarks(BaseModel):
    span: list[datetime]
    strategy_out_of_sample_return: DecimalString
    no_trade_return: DecimalString
    buy_and_hold_return: DecimalString
    random_entry_mean_return: DecimalString | None
    random_entry_median_return: DecimalString | None
    random_entry_runs: int
    strategy_beat_share_of_random_runs: DecimalString | None
    note: str


class ForexLeakageAudit(BaseModel):
    passed: bool
    cuts: list[datetime]
    decisions_compared: int
    first_difference: datetime | None


class ForexBacktestTrade(BaseModel):
    side: Literal["long", "short"]
    decided_at: datetime
    entry_at: datetime
    exit_at: datetime
    entry_price: DecimalString
    exit_price: DecimalString
    stop: DecimalString
    target: DecimalString
    units: DecimalString
    pnl: DecimalString
    r_multiple: DecimalString
    costs: DecimalString
    bars_held: int
    reason: Literal["stop", "target", "gap_stop", "gap_target", "time", "end"]


class ForexBacktestReportOut(BaseModel):
    id: uuid.UUID
    label: Literal["backtested"]
    notice: str
    instrument: str
    timeframe: str
    rule: str
    rule_version: int
    engine_version: str
    code_version: str
    seed: int
    data: ForexBacktestData
    costs: ForexBacktestCosts
    full_period: ForexBacktestFullPeriod
    cost_sensitivity: list[ForexCostScenario]
    walk_forward: ForexWalkForward
    benchmarks: ForexBacktestBenchmarks
    leakage_audit: ForexLeakageAudit
    out_of_sample_trades: list[ForexBacktestTrade]
    out_of_sample_trades_listed: int
    report_hash: str = Field(description="SHA-256 of the canonical report: same inputs, same hash")
    generated_at: datetime


class ForexBacktestSummaryOut(BaseModel):
    id: uuid.UUID
    label: Literal["backtested"]
    instrument: str
    timeframe: str
    rule: str
    rule_version: int
    period_start: datetime
    period_end: datetime
    bars: int
    data_types: list[str]
    out_of_sample_trades: int
    out_of_sample_return: DecimalString
    out_of_sample_profit_factor: DecimalString | None
    leakage_audit_passed: bool
    report_hash: str
    generated_at: datetime


class ForexBacktestsOut(BaseModel):
    items: list[ForexBacktestSummaryOut]
    notice: str = NOTICE


def _summary(r: ForexBacktestReport) -> ForexBacktestSummaryOut:
    return ForexBacktestSummaryOut(
        id=r.id,
        label="backtested",
        instrument=r.instrument,
        timeframe=r.timeframe,
        rule=r.rule,
        rule_version=r.rule_version,
        period_start=r.period_start,
        period_end=r.period_end,
        bars=r.bars,
        data_types=r.data_types,
        out_of_sample_trades=r.oos_trades,
        out_of_sample_return=r.oos_return,
        out_of_sample_profit_factor=r.oos_profit_factor,
        leakage_audit_passed=bool(r.report["leakage_audit"]["passed"]),
        report_hash=r.report_hash,
        generated_at=r.generated_at,
    )


@router.get(
    "/backtests",
    response_model=ForexBacktestsOut,
    summary="Stored backtest reports of the setup rules, newest first",
    description="Summaries of the reports the daily job made from stored bars: the out-of-sample "
    "result of walk-forward validation, net of costs, and whether the leakage audit passed. "
    "Backtested results only; not a forecast.",
    responses={**UNAUTHORIZED, **invalid("filter"), **not_found("forex module (switched off)")},
)
async def backtests(
    _: ForexUser,
    session: SessionDep,
    instrument: Annotated[str | None, Query(pattern=INSTRUMENT_PATTERN)] = None,
    timeframe: Frame | None = None,
    rule: Rule | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ForexBacktestsOut:
    query = select(ForexBacktestReport).order_by(
        ForexBacktestReport.generated_at.desc(),
        ForexBacktestReport.instrument,
        ForexBacktestReport.rule,
    )
    if instrument is not None:
        query = query.where(ForexBacktestReport.instrument == instrument)
    if timeframe is not None:
        query = query.where(ForexBacktestReport.timeframe == timeframe)
    if rule is not None:
        query = query.where(ForexBacktestReport.rule == rule)
    rows = (await session.execute(query.limit(limit))).scalars()
    return ForexBacktestsOut(items=[_summary(r) for r in rows])


@router.get(
    "/backtests/{report_hash}",
    response_model=ForexBacktestReportOut,
    summary="One backtest report in full",
    description="The full report: data snapshot hash, code version, parameters and seed; the "
    "full-period run, cost sensitivity, every walk-forward window in-sample and out-of-sample, "
    "benchmarks, the leakage audit and the out-of-sample trades. Addressed by its report hash: "
    "a report is global reference data, the same for every user.",
    responses={
        **UNAUTHORIZED,
        **invalid("report hash"),
        **not_found("backtest report, or the forex module is switched off"),
    },
)
async def backtest(
    report_hash: Annotated[str, Path(pattern=r"^[0-9a-f]{64}$")], _: ForexUser, session: SessionDep
) -> ForexBacktestReportOut:
    row = await session.scalar(
        select(ForexBacktestReport).where(ForexBacktestReport.report_hash == report_hash)
    )
    if row is None:
        raise ResourceNotFoundError("backtest report")
    return ForexBacktestReportOut.model_validate({**row.report, "id": row.id})
