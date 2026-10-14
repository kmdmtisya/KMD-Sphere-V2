"""The transparent opportunity score (P13-T06.2, design section 8.2), the market condition and
the risk level (P13-T06.3). Pure Decimal functions; weights are versioned configuration.

    score = 100 x clip(sum(weight_i x component_i), 0, 1)

Every component is in [0, 1]. `macro_event_risk` has a negative weight (a penalty). The positive
weights sum to 1. The score ranks **research candidates**; it is not a probability of profit.

Components:
- `trend_strength`: ADX / 50 (capped at 1) when the directional indicators agree, else 0;
- `momentum`: bullish (RSI - 50) / 30, bearish (50 - RSI) / 30, clipped to [0, 1];
- `volatility_suitability`: 1 - abs(ATR / median ATR - 1), clipped: best near usual volatility;
- `spread_and_cost`: 1 - spread / (10% of ATR), clipped; 0 when the spread is unknown;
- `liquidity`: major 1, minor 0.7, exotic 0.3;
- `technical_confluence`: other setups in the same direction / 3, capped at 1;
- `macro_event_risk` (penalty): 1 inside or within one bar of a high-importance window, 0.5 for
  medium, else 0;
- `forecast_calibration`: 2 x abs(p - 0.5) when the forecast is calibrated and agrees, else 0;
- `strategy_history`: out-of-sample backtest quality: 0 until backtests exist (P13-T08), stated;
- `risk_reward`: reward / risk / 3, capped at 1.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

D = Decimal
WEIGHTS_VERSION = 1
DEFAULT_WEIGHTS: dict[str, Decimal] = {
    "trend_strength": D("0.15"),
    "momentum": D("0.10"),
    "volatility_suitability": D("0.10"),
    "spread_and_cost": D("0.10"),
    "liquidity": D("0.10"),
    "technical_confluence": D("0.15"),
    "forecast_calibration": D("0.10"),
    "strategy_history": D("0.05"),
    "risk_reward": D("0.15"),
    "macro_event_risk": D("-0.20"),
}
COMPONENTS = tuple(DEFAULT_WEIGHTS)
LIQUIDITY = {"major": D(1), "minor": D("0.7"), "exotic": D("0.3")}
ZERO, ONE = D(0), D(1)
Condition = Literal[
    "trending", "consolidating", "high_volatility", "momentum_strengthening", "mixed"
]
RiskLevel = Literal["low", "medium", "medium_high", "high"]


def validate_weights(weights: Mapping[str, Decimal]) -> None:
    if set(weights) != set(COMPONENTS):
        raise ValueError(f"weights must name exactly: {', '.join(COMPONENTS)}")
    if weights["macro_event_risk"] > 0:
        raise ValueError("macro_event_risk is a penalty: its weight must be zero or negative")
    positive = [w for k, w in weights.items() if k != "macro_event_risk"]
    if any(w < 0 for w in positive) or sum(positive, ZERO) != ONE:
        raise ValueError("the positive weights must be non-negative and sum to 1")


def clip(x: Decimal) -> Decimal:
    return max(ZERO, min(ONE, x))


@dataclass(frozen=True)
class Factor:
    name: str
    value: Decimal  # 0..1
    weight: Decimal
    detail: str

    @property
    def contribution(self) -> Decimal:
        return self.value * self.weight


def score(factors: list[Factor]) -> Decimal:
    total = sum((f.contribution for f in factors), ZERO)
    return (clip(total) * 100).quantize(D("0.1"), rounding=ROUND_HALF_UP)


def condition(
    adx: Decimal | None,
    adx_before: Decimal | None,
    hist: Decimal | None,
    hist_before: Decimal | None,
    atr_ratio: Decimal | None,
) -> Condition:
    """The market condition, in priority order: high volatility (ATR above 1.5 x its median),
    trending (ADX >= 25), momentum strengthening (ADX rising and the MACD histogram growing),
    consolidating (ADX < 20), otherwise mixed."""
    if atr_ratio is not None and atr_ratio > D("1.5"):
        return "high_volatility"
    if adx is not None and adx >= 25:
        return "trending"
    if (
        adx is not None
        and adx_before is not None
        and hist is not None
        and hist_before is not None
        and adx > adx_before
        and abs(hist) > abs(hist_before)
    ):
        return "momentum_strengthening"
    if adx is not None and adx < 20:
        return "consolidating"
    return "mixed"


def risk_level(
    atr_ratio: Decimal | None, spread_to_atr: Decimal | None, event_penalty: Decimal
) -> RiskLevel:
    """Points: volatility above 1.5 x usual +2 (above 1.2 x +1); spread above 10% of ATR, or
    unknown, +1; a high-importance event window +2 (medium +1). 0 low, 1 medium, 2 medium-high,
    3 or more high."""
    points = 0
    if atr_ratio is not None:
        points += 2 if atr_ratio > D("1.5") else 1 if atr_ratio > D("1.2") else 0
    if spread_to_atr is None or spread_to_atr > D("0.1"):
        points += 1
    points += 2 if event_penalty >= ONE else 1 if event_penalty > ZERO else 0
    return ("low", "medium", "medium_high", "high")[min(points, 3)]
