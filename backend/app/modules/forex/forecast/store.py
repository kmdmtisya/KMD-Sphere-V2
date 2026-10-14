"""The model registry and published forecasts (P13-T05, migration 0022). Reference data.

- `forex_model_versions`: one row per training run for a pair and horizon, with everything needed
  to reproduce and judge it: the model and its parameters, the feature-set and data hashes, the
  code version and seed, the full evaluation against the baselines (kept whatever it shows),
  calibration and drift. Status moves `active` -> `superseded` when a newer run is published,
  or is `disabled` when drift is breached.
- `forex_forecasts`: the published forecasts, append-only.

A disabled pair and horizon stays unavailable until someone approves retraining
(`approve_retraining`); the training job skips it until then."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.modules.forex.forecast.pipeline import Run, summary


class ForexModelVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "forex_model_versions"
    __table_args__ = (
        CheckConstraint("horizon IN ('15m', '1h', '4h', '24h', '1w')", name="horizon"),
        CheckConstraint("status IN ('active', 'superseded', 'disabled')", name="status"),
        CheckConstraint(
            "calibration_status IN ('calibrated', 'requires_calibration')",
            name="calibration_status",
        ),
        CheckConstraint("drift_status IN ('ok', 'breached')", name="drift_status"),
        CheckConstraint("probability_source IN ('raw', 'recalibrated')", name="probability_source"),
        Index(
            "ix_forex_model_versions_instrument_horizon_trained_at",
            "instrument",
            "horizon",
            "trained_at",
        ),
    )

    instrument: Mapped[str] = mapped_column(
        String(7), ForeignKey("forex_instruments.code", ondelete="RESTRICT")
    )
    horizon: Mapped[str] = mapped_column(String(4))
    timeframe: Mapped[str] = mapped_column(String(3))
    bars_ahead: Mapped[int] = mapped_column(Integer)
    model_name: Mapped[str] = mapped_column(String(40))
    family: Mapped[str] = mapped_column(String(20))
    version: Mapped[str] = mapped_column(String(16))
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    feature_set_hash: Mapped[str] = mapped_column(String(16))
    data_snapshot_hash: Mapped[str] = mapped_column(String(16))
    code_version: Mapped[str] = mapped_column(String(64))
    seed: Mapped[int] = mapped_column(Integer)
    trained_at: Mapped[datetime] = mapped_column()
    train_rows: Mapped[int] = mapped_column(Integer)
    test_rows: Mapped[int] = mapped_column(Integer)
    folds: Mapped[int] = mapped_column(Integer)
    evaluation: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    volatility: Mapped[dict[str, Any]] = mapped_column(JSONB)
    calibration_status: Mapped[str] = mapped_column(String(24))
    probability_source: Mapped[str] = mapped_column(String(16))
    edge: Mapped[bool] = mapped_column()
    drift: Mapped[dict[str, Any]] = mapped_column(JSONB)
    drift_status: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16))
    # Data types of the candles it was trained on: an edge on simulated data is no evidence.
    data_types: Mapped[list[str]] = mapped_column(ARRAY(String(16)))
    retraining_approved_by: Mapped[str | None] = mapped_column(String(200))
    retraining_approved_at: Mapped[datetime | None] = mapped_column()


class ForexForecast(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "forex_forecasts"
    __table_args__ = (
        CheckConstraint(
            "prob_up BETWEEN 0 AND 1 AND prob_up_raw BETWEEN 0 AND 1", name="probability"
        ),
        Index(
            "ix_forex_forecasts_instrument_horizon_generated_at",
            "instrument",
            "horizon",
            "generated_at",
        ),
    )

    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("forex_model_versions.id", ondelete="CASCADE")
    )
    instrument: Mapped[str] = mapped_column(String(7))
    horizon: Mapped[str] = mapped_column(String(4))
    as_of: Mapped[datetime] = mapped_column()  # the last closed bar the forecast starts from
    generated_at: Mapped[datetime] = mapped_column()
    last_close: Mapped[Decimal] = mapped_column(Numeric(20, 10))
    prob_up: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    prob_up_raw: Mapped[Decimal] = mapped_column(Numeric(8, 6))
    return_quantiles: Mapped[list[str]] = mapped_column(JSONB)
    price_quantiles: Mapped[list[str]] = mapped_column(JSONB)
    expected_volatility: Mapped[Decimal] = mapped_column(Numeric(20, 12))
    volatility_model: Mapped[str] = mapped_column(String(8))
    data_types: Mapped[list[str]] = mapped_column(ARRAY(String(16)))


def _dec(value: float, places: int) -> Decimal:
    return Decimal(repr(float(value))).quantize(Decimal(1).scaleb(-places))


async def latest_version(
    session: AsyncSession, instrument: str, horizon: str
) -> ForexModelVersion | None:
    return await session.scalar(
        select(ForexModelVersion)
        .where(ForexModelVersion.instrument == instrument, ForexModelVersion.horizon == horizon)
        .order_by(ForexModelVersion.trained_at.desc())
        .limit(1)
    )


async def blocked(session: AsyncSession, instrument: str, horizon: str) -> bool:
    """True while the latest run breached drift and retraining has not been approved."""
    latest = await latest_version(session, instrument, horizon)
    return (
        latest is not None and latest.status == "disabled" and latest.retraining_approved_at is None
    )


async def approve_retraining(
    session: AsyncSession, instrument: str, horizon: str, approved_by: str, at: datetime
) -> ForexModelVersion:
    latest = await latest_version(session, instrument, horizon)
    if latest is None or latest.status != "disabled":
        raise ValueError("there is no disabled model to approve retraining for")
    if not approved_by.strip():
        raise ValueError("approved_by is required")
    latest.retraining_approved_by = approved_by.strip()[:200]
    latest.retraining_approved_at = at
    await session.commit()
    return latest


async def record(
    session: AsyncSession, instrument: str, run: Run, data_types: list[str], at: datetime
) -> tuple[ForexModelVersion, ForexForecast | None]:
    """Stores a training run. When drift is breached, the version is `disabled` and no forecast
    is published; otherwise the previous active version is superseded and the forecast stored."""
    pub = run.published
    chosen = run.evaluation.by_name(pub.model)
    breached = run.drift.status == "breached"
    if not breached:
        previous = (
            await session.execute(
                select(ForexModelVersion).where(
                    ForexModelVersion.instrument == instrument,
                    ForexModelVersion.horizon == pub.horizon,
                    ForexModelVersion.status == "active",
                )
            )
        ).scalars()
        for row in previous:
            row.status = "superseded"
    version = ForexModelVersion(
        instrument=instrument,
        horizon=pub.horizon,
        timeframe=pub.timeframe.value,
        bars_ahead=pub.bars_ahead,
        model_name=pub.model,
        family=pub.family,
        version=run.version,
        params=chosen.params,
        feature_set_hash=run.feature_set_hash,
        data_snapshot_hash=run.data_snapshot_hash,
        code_version=run.code_version,
        seed=run.seed,
        trained_at=at,
        train_rows=run.train_rows,
        test_rows=run.evaluation.test_rows,
        folds=run.evaluation.folds,
        evaluation=summary(run.evaluation),
        volatility={**run.volatility, "chosen": pub.volatility_model},
        calibration_status=chosen.calibration.status
        if chosen.calibration
        else "requires_calibration",
        probability_source=chosen.probability,
        edge=pub.edge,
        drift={
            "status": run.drift.status,
            "reasons": run.drift.reasons,
            "feature_psi": run.drift.feature_psi,
            "feature_ks_p": run.drift.feature_ks_p,
            "recent_log_loss": run.drift.recent_log_loss,
            "recent_random_walk_log_loss": run.drift.recent_random_walk_log_loss,
        },
        drift_status=run.drift.status,
        status="disabled" if breached else "active",
        data_types=data_types,
    )
    session.add(version)
    await session.flush()
    forecast = None
    if not breached:
        forecast = ForexForecast(
            model_version_id=version.id,
            instrument=instrument,
            horizon=pub.horizon,
            as_of=pub.as_of,
            generated_at=at,
            last_close=pub.last_close,
            prob_up=_dec(pub.prob_up, 6),
            prob_up_raw=_dec(pub.prob_up_raw, 6),
            return_quantiles=[format(_dec(q, 10), "f") for q in pub.return_quantiles],
            price_quantiles=[format(p, "f") for p in pub.price_quantiles],
            expected_volatility=_dec(pub.expected_volatility, 12),
            volatility_model=pub.volatility_model,
            data_types=data_types,
        )
        session.add(forecast)
    await session.commit()
    return version, forecast
