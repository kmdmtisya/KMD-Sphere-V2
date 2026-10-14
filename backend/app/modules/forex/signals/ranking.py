"""Candidates and the ranking (P13-T06.3, T06.4). Pure: the caller supplies the bars, the latest
quote, event windows and the forecast; this module scores every setup of a pair and explains it.

Demotions and exclusions (design section 8.2), each stated in `adjustments`:
- bars older than two bar periods: **excluded** (stale data is not ranked);
- an open, or about to open, high-importance event window: score x 0.5;
- no fresh live quote (the spread is unknown): score x 0.75;
- a forecast that requires calibration: it contributes nothing, and says so."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from statistics import median

from app.modules.forex.calendar.risk import RiskWindow
from app.modules.forex.signals import setups as su
from app.modules.forex.signals.scoring import (
    LIQUIDITY,
    Condition,
    Factor,
    RiskLevel,
    clip,
    condition,
    risk_level,
    score,
)

D = Decimal
ZERO, ONE = D(0), D(1)
QUOTE_FRESH = timedelta(seconds=60)


@dataclass(frozen=True)
class ForecastInput:
    horizon: str
    prob_up: Decimal
    calibrated: bool
    model_version: str
    model_name: str


@dataclass(frozen=True)
class PairInput:
    instrument: str
    pip_location: int
    display_precision: int
    liquidity_tier: str
    bars: su.Bars
    bar_step: timedelta
    data_types: list[str]
    spread: Decimal | None  # from the latest fresh quote, None when there is none
    quote_age: timedelta | None
    windows: list[RiskWindow]
    forecast: ForecastInput | None
    now: datetime


@dataclass
class Candidate:
    instrument: str
    tier: str
    setup: su.Setup
    condition: Condition
    risk: RiskLevel
    score: Decimal
    factors: list[Factor]
    adjustments: list[str]
    excluded: bool
    assumptions: list[str]
    risks: list[str]
    spread_pips: Decimal | None
    spread_share_of_risk: Decimal | None
    levels_pips: dict[str, Decimal]
    bar_age: timedelta
    quote_age: timedelta | None
    data_types: list[str]
    forecast: ForecastInput | None
    precision: int = 5
    notes: list[str] = field(default_factory=list)


def _q(x: Decimal, places: str) -> Decimal:
    return x.quantize(D(places), rounding=ROUND_HALF_UP)


def _event_penalty(
    windows: Sequence[RiskWindow], now: datetime, step: timedelta
) -> tuple[Decimal, list[str]]:
    soon = [w for w in windows if w.starts <= now + step and w.ends > now]
    if any(w.importance == "high" for w in soon):
        return ONE, [f"{w.name} ({w.importance}) at {w.scheduled_at.isoformat()}" for w in soon]
    if soon:
        return D("0.5"), [
            f"{w.name} ({w.importance}) at {w.scheduled_at.isoformat()}" for w in soon
        ]
    return ZERO, []


def candidates(p: PairInput, weights: dict[str, Decimal]) -> list[Candidate]:
    """Every setup that holds for the pair, scored and explained, best first."""
    ctx = su.context(p.bars)
    found = su.detect(ctx)
    if not found:
        return []
    pip = D(1).scaleb(p.pip_location)
    atrs = [a for a in ctx.atr if a is not None]
    atr = atrs[-1]
    atr_ratio = atr / D(str(median(atrs))) if atrs else None
    adx = ctx.adx.adx[-1]
    rsi = ctx.rsi[-1]
    cond = condition(
        adx,
        ctx.adx.adx[-2] if len(ctx.adx.adx) > 1 else None,
        ctx.macd.histogram[-1],
        ctx.macd.histogram[-2],
        atr_ratio,
    )
    penalty, events = _event_penalty(p.windows, p.now, p.bar_step)
    bar_age = p.now - (p.bars.ts[-1] + p.bar_step)
    stale = bar_age > 2 * p.bar_step
    quote_fresh = p.spread is not None and p.quote_age is not None and p.quote_age <= QUOTE_FRESH
    spread_to_atr = (p.spread / atr) if quote_fresh and p.spread is not None and atr > 0 else None
    level = risk_level(atr_ratio, spread_to_atr, penalty)
    out: list[Candidate] = []
    for s in found:
        bull = s.direction == "bullish"
        pdi, mdi = ctx.adx.plus_di[-1], ctx.adx.minus_di[-1]
        agrees = pdi is not None and mdi is not None and ((pdi > mdi) if bull else (mdi > pdi))
        same = sum(1 for o in found if o is not s and o.direction == s.direction)
        rr = s.risk_reward or ZERO
        fc = p.forecast
        fc_value = ZERO
        fc_detail = "no forecast available"
        if fc is not None:
            if not fc.calibrated:
                fc_detail = f"{fc.model_name} forecast requires calibration: not used"
            else:
                agree = (fc.prob_up > D("0.5")) == bull
                fc_value = clip(2 * abs(fc.prob_up - D("0.5"))) if agree else ZERO
                verdict = "agrees" if agree else "disagrees"
                fc_detail = f"calibrated {fc.model_name} probability up {fc.prob_up} ({verdict})"
        values = {
            "trend_strength": (
                clip(adx / 50) if adx is not None and agrees else ZERO,
                f"ADX {adx:.1f}, directional indicators {'agree' if agrees else 'do not agree'}"
                if adx is not None
                else "ADX unavailable",
            ),
            "momentum": (
                clip(((rsi - 50) if bull else (50 - rsi)) / 30) if rsi is not None else ZERO,
                f"RSI {rsi:.1f}" if rsi is not None else "RSI unavailable",
            ),
            "volatility_suitability": (
                clip(ONE - abs(atr_ratio - ONE)) if atr_ratio is not None else ZERO,
                f"ATR is {atr_ratio:.2f} x its median"
                if atr_ratio is not None
                else "ATR unavailable",
            ),
            "spread_and_cost": (
                clip(ONE - spread_to_atr / D("0.1")) if spread_to_atr is not None else ZERO,
                f"spread {p.spread / pip:.1f} pips"
                if spread_to_atr is not None and p.spread is not None
                else "spread unknown (no fresh quote)",
            ),
            "liquidity": (LIQUIDITY.get(p.liquidity_tier, ZERO), f"{p.liquidity_tier} pair"),
            "technical_confluence": (
                clip(D(same) / 3),
                f"{same} other setup(s) point the same way",
            ),
            "forecast_calibration": (fc_value, fc_detail),
            "strategy_history": (
                ZERO,
                "no out-of-sample backtest yet (P13-T08): contributes nothing",
            ),
            "risk_reward": (clip(rr / 3), f"reward / risk {rr:.2f}"),
            "macro_event_risk": (penalty, "; ".join(events) if events else "no event window"),
        }
        factors = [Factor(k, _q(v, "0.0001"), weights[k], d) for k, (v, d) in values.items()]
        value = score(factors)
        adjustments: list[str] = []
        if penalty >= ONE:
            value = _q(value / 2, "0.1")
            adjustments.append(
                "demoted x 0.5: a high-importance event window is open or about to open"
            )
        if not quote_fresh:
            value = _q(value * D("0.75"), "0.1")
            adjustments.append(
                "demoted x 0.75: no fresh live quote, so the spread and costs are unknown"
            )
        if stale:
            adjustments.append(
                f"excluded: the latest bar is stale ({int(bar_age.total_seconds())} s old)"
            )
        risks = [
            "Prices can move past the illustrative stop: stops can gap or slip and do not cap a "
            "loss.",
            "The setup is a pattern in past prices; it can fail at any time.",
        ]
        if events:
            risks.append("Scheduled releases nearby can move prices sharply: " + "; ".join(events))
        if atr_ratio is not None and atr_ratio > D("1.5"):
            risks.append("Volatility is well above usual, so ranges and costs can be larger.")
        if "simulated" in p.data_types:
            risks.append("The prices are simulated development data, not a market.")
        spread_pips = _q(p.spread / pip, "0.1") if quote_fresh and p.spread is not None else None
        out.append(
            Candidate(
                instrument=p.instrument,
                tier=p.liquidity_tier,
                setup=s,
                condition=cond,
                risk=level,
                score=value,
                factors=factors,
                adjustments=adjustments,
                excluded=stale,
                assumptions=[
                    "Entry is the last close; the stop is where the setup no longer holds; the "
                    "target follows the rule.",
                    "Levels come from stored bars and the rule definition, at the time shown.",
                    "Costs use the latest quoted spread only; swaps and slippage are not included.",
                ],
                risks=risks,
                spread_pips=spread_pips,
                spread_share_of_risk=_q(p.spread / s.risk, "0.0001")
                if spread_pips is not None and p.spread is not None and s.risk > 0
                else None,
                levels_pips={
                    "risk": _q(s.risk / pip, "0.1"),
                    "reward": _q(s.reward / pip, "0.1"),
                    "risk_reward": _q(rr, "0.01"),
                },
                bar_age=bar_age,
                quote_age=p.quote_age,
                data_types=p.data_types,
                forecast=p.forecast,
                precision=p.display_precision,
            )
        )
    return sorted(out, key=lambda c: (-c.score, c.setup.rule))


def rank(per_pair: Sequence[list[Candidate]]) -> tuple[list[Candidate], list[Candidate]]:
    """The best candidate of each pair, ranked by score (ties by pair), and the excluded ones."""
    best = [c[0] for c in per_pair if c]
    ranked = sorted((c for c in best if not c.excluded), key=lambda c: (-c.score, c.instrument))
    excluded = sorted((c for c in best if c.excluded), key=lambda c: c.instrument)
    return ranked, excluded
