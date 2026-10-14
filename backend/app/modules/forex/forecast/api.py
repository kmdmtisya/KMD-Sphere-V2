"""Forecast API (P13-T05.8, design section 7.2). Reference data, the same for every signed-in
user, behind the forex flag.

A forecast states its horizon, the probabilities up and down, the return quantiles and the
price intervals they imply, the expected volatility, its calibration status, the out-of-sample
record of the model against the baselines, its freshness and the model version. A probability
is labelled "Requires calibration" until held-out calibration has passed, and is never
described as a success rate. When no model beats the baselines, the random-walk baseline is
shown and says so. When drift has disabled the model, or there is not enough history, the
forecast is unavailable and nothing is shown in its place."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.authz import ResourceNotFoundError
from app.core.money import DecimalString
from app.modules.forex.api import ForexUser, SessionDep
from app.modules.forex.forecast.pipeline import HORIZONS
from app.modules.forex.forecast.store import ForexForecast, ForexModelVersion, latest_version
from app.modules.forex.instruments.registry import active_instruments
from app.modules.forex.marketdata.types import INSTRUMENT_PATTERN, Timeframe

router = APIRouter(prefix="/api/v1/forex", tags=["forex"])
Horizon = Literal["15m", "1h", "4h", "24h", "1w"]
RESPONSES = {
    **UNAUTHORIZED,
    **invalid("request"),
    **not_found("instrument, or the forex module is switched off"),
}
NOTICE = (
    "A statistical estimate from past prices: not a prediction of what will happen, not advice, "
    "and never a guaranteed return. Probabilities are model outputs, not success rates; "
    "intervals can be wrong."
)
BAR = {
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
    Timeframe.D1: timedelta(days=1),
}
# A forecast is fresh while it starts from one of the last two bars (plus the training cadence).
FRESH_BARS = 2
TRAINING_CADENCE = timedelta(hours=1)


class Interval(BaseModel):
    low: DecimalString
    high: DecimalString


class ForecastValues(BaseModel):
    as_of: datetime = Field(description="The last closed bar the forecast starts from (UTC)")
    generated_at: datetime
    age_seconds: int
    fresh: bool
    last_close: DecimalString
    prob_up: DecimalString
    prob_down: DecimalString
    probability_label: Literal["Requires calibration", "Calibrated"]
    probability_note: str = "A model probability, not a success rate."
    return_quantiles: dict[str, DecimalString] = Field(
        description="Log return over the horizon: q10, q25, q50, q75, q90"
    )
    price_median: DecimalString
    price_interval_50: Interval
    price_interval_80: Interval
    expected_volatility: DecimalString = Field(
        description="Standard deviation of the log return over the horizon"
    )
    volatility_model: Literal["ewma", "har"]
    data_types: list[str]


class ModelInfo(BaseModel):
    name: str
    family: str
    version: str
    trained_at: datetime
    feature_set_hash: str
    data_snapshot_hash: str
    code_version: str
    seed: int
    edge: bool
    statement: str
    data_types: list[str] = Field(description="Data types of the candles the model was trained on")
    probability_source: Literal["raw", "recalibrated"]
    calibration_status: Literal["calibrated", "requires_calibration"]
    drift_status: Literal["ok", "breached"]


class OutOfSample(BaseModel):
    folds: int
    test_rows: int
    model: dict[str, float]
    baselines: dict[str, dict[str, float]]


class ForecastOut(BaseModel):
    instrument: str
    horizon: Horizon
    timeframe: str
    bars_ahead: int
    status: Literal["available", "unavailable"]
    reason: str | None = None
    forecast: ForecastValues | None = None
    model: ModelInfo | None = None
    out_of_sample: OutOfSample | None = None
    notice: str = NOTICE


class EvaluationOut(BaseModel):
    instrument: str
    horizon: Horizon
    status: Literal["available", "unavailable"]
    reason: str | None = None
    model: ModelInfo | None = None
    results: list[dict[str, Any]] = Field(
        default_factory=list, description="Every model and baseline, whatever the outcome"
    )
    volatility: dict[str, Any] = Field(default_factory=dict)
    drift: dict[str, Any] = Field(default_factory=dict)
    notice: str = NOTICE


def statement(edge: bool, data_types: list[str]) -> str:
    text = (
        "demonstrated edge against the baselines"
        if edge
        else "no demonstrated edge: the random-walk baseline is shown"
    )
    if "simulated" in data_types:
        text += " (on simulated data: not evidence about real markets)"
    return text


def _model_info(v: ForexModelVersion) -> ModelInfo:
    return ModelInfo(
        name=v.model_name,
        family=v.family,
        version=v.version,
        trained_at=v.trained_at,
        feature_set_hash=v.feature_set_hash,
        data_snapshot_hash=v.data_snapshot_hash,
        code_version=v.code_version,
        seed=v.seed,
        edge=v.edge,
        statement=statement(v.edge, list(v.data_types)),
        data_types=list(v.data_types),
        probability_source=v.probability_source,
        calibration_status=v.calibration_status,
        drift_status=v.drift_status,
    )


def _reason(v: ForexModelVersion | None) -> str | None:
    if v is None:
        return "no forecast yet: not enough history has been collected for this horizon"
    if v.status == "disabled":
        return "forecast unavailable: drift was detected and retraining has not been approved"
    return None


async def _check(session: SessionDep, instrument: str) -> None:
    if instrument not in {r.code for r in await active_instruments(session)}:
        raise ResourceNotFoundError("forex instrument")


@router.get(
    "/forecasts",
    response_model=ForecastOut,
    summary="The latest forecast for a pair and horizon, with its evaluation against baselines",
    description="Horizons 15m, 1h, 4h, 24h and 1w. Unavailable, with the reason, when there is not "
    "enough history or drift has disabled the model. Formulas and rules: "
    "docs/design/forex-forecasting.md.",
    responses=RESPONSES,
)
async def forecast(
    _: ForexUser,
    session: SessionDep,
    instrument: Annotated[str, Query(pattern=INSTRUMENT_PATTERN)],
    horizon: Horizon = "1h",
) -> ForecastOut:
    await _check(session, instrument)
    timeframe, bars_ahead = HORIZONS[horizon]
    base = ForecastOut(
        instrument=instrument,
        horizon=horizon,
        timeframe=timeframe.value,
        bars_ahead=bars_ahead,
        status="unavailable",
    )
    version = await latest_version(session, instrument, horizon)
    reason = _reason(version)
    if reason is not None or version is None:
        return base.model_copy(
            update={"reason": reason, "model": _model_info(version) if version else None}
        )
    row = await session.scalar(
        select(ForexForecast)
        .where(ForexForecast.model_version_id == version.id)
        .order_by(ForexForecast.generated_at.desc())
        .limit(1)
    )
    if row is None:  # pragma: no cover - an active version always has its forecast
        return base.model_copy(update={"reason": "no forecast stored"})
    now = datetime.now(UTC)
    q = [Decimal(v) for v in row.return_quantiles]
    p = [Decimal(v) for v in row.price_quantiles]
    chosen = next((r for r in version.evaluation if r["name"] == version.model_name), None)
    baselines = {r["name"]: r["metrics"] for r in version.evaluation if r["family"] == "baseline"}
    values = ForecastValues(
        as_of=row.as_of,
        generated_at=row.generated_at,
        age_seconds=int((now - row.as_of).total_seconds()),
        fresh=now - row.as_of <= FRESH_BARS * BAR[timeframe] + TRAINING_CADENCE,
        last_close=row.last_close,
        prob_up=row.prob_up,
        prob_down=Decimal(1) - row.prob_up,
        probability_label="Calibrated"
        if version.calibration_status == "calibrated"
        else "Requires calibration",
        return_quantiles=dict(zip(("q10", "q25", "q50", "q75", "q90"), q, strict=True)),
        price_median=p[2],
        price_interval_50=Interval(low=p[1], high=p[3]),
        price_interval_80=Interval(low=p[0], high=p[4]),
        expected_volatility=row.expected_volatility,
        volatility_model=row.volatility_model,
        data_types=list(row.data_types),
    )
    return base.model_copy(
        update={
            "status": "available",
            "forecast": values,
            "model": _model_info(version),
            "out_of_sample": OutOfSample(
                folds=version.folds,
                test_rows=version.test_rows,
                model=chosen["metrics"] if chosen else {},
                baselines=baselines,
            ),
        }
    )


@router.get(
    "/forecasts/evaluation",
    response_model=EvaluationOut,
    summary="The out-of-sample evaluation behind the latest forecast",
    description="Every model and baseline with its metrics, comparison with each baseline "
    "(Diebold-Mariano), calibration and edge statement, plus the volatility models and drift "
    "checks. Reported whatever it shows, including when a baseline wins.",
    responses=RESPONSES,
)
async def evaluation(
    _: ForexUser,
    session: SessionDep,
    instrument: Annotated[str, Query(pattern=INSTRUMENT_PATTERN)],
    horizon: Horizon = "1h",
) -> EvaluationOut:
    await _check(session, instrument)
    version = await latest_version(session, instrument, horizon)
    if version is None:
        return EvaluationOut(
            instrument=instrument, horizon=horizon, status="unavailable", reason=_reason(None)
        )
    return EvaluationOut(
        instrument=instrument,
        horizon=horizon,
        status="unavailable" if version.status == "disabled" else "available",
        reason=_reason(version),
        model=_model_info(version),
        results=version.evaluation,
        volatility=version.volatility,
        drift=version.drift,
    )
