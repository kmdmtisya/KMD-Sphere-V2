"""The risk calculator (P13-T07.2 to T07.6, design section 9). Pure, Decimal-only, computed at 50
significant digits and rounded only for display, with each rounding stated (ADR-0006).

Definitions (one unit is one unit of the base currency; a standard lot is `contract_size` units):
- pip size = 10 ** pip_location (0.0001 for EUR/USD, 0.01 for USD/JPY);
- pip value per unit, in the quote currency = pip size. In the account currency = pip size x
  rate(quote -> account). **Never a constant:** the rate comes from the timestamped feed, and is
  exactly 1 only when the quote currency is the account currency;
- cost per unit, in the quote currency = spread + 2 x slippage_pips x pip size + 2 x commission
  per lot per side / contract size (entry and exit);
- risk amount = balance x risk percent / 100;
- units = (risk amount / rate) / (abs(entry - stop) + cost per unit), computed in the quote
  currency with the rate kept as a fraction of stored mids, **rounded down** to the lot step,
  so the planned loss including costs never exceeds the risk amount; below the minimum lot size
  the trade is refused (size 0); above the maximum it is capped, with a warning;
- loss = units x abs(entry - stop) x rate (before costs), plus costs = units x cost per unit x rate;
- profit = units x abs(target - entry) x rate (before costs), less costs;
- risk/reward = abs(target - entry) / abs(entry - stop) before costs; profit after costs / loss
  after costs after costs;
- notional = units x entry x rate (account currency); margin = notional x margin rate; position
  leverage = notional / balance; the specification's maximum leverage = 1 / margin rate;
- exposure: the base currency +units (long) or -units (short), the quote currency the opposite
  in quote units; as a share of the balance, notional / balance (shown, and limited through the
  leverage limit, which is the same ratio).
Display rounding: account amounts to the currency's minor units, half up; pips to 0.1; prices to
the pair's display precision; ratios to 0.01; percentages to 0.01; lots are exact multiples of
the lot step.

Warnings are returned, never silent clipping: limits, insufficient margin, leverage, a non
tradable or stale conversion rate, an unknown spread, unreviewed specifications, a less liquid
pair, and a capped or refused size."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal, localcontext
from typing import Literal

from app.core.money import minor_units
from app.modules.forex.risk.specs import SpecValues

D = Decimal
ZERO, ONE, HUNDRED = D(0), D(1), D(100)
Direction = Literal["long", "short"]
DISCLOSURES = (
    "A stop-loss does not guarantee the maximum loss: prices can gap or slip past it, for example "
    "over a weekend or around news.",
    "Leverage amplifies losses as well as gains; a loss can exceed the margin placed.",
    "All values are estimates from the configured contract specifications and the stated rates "
    "and costs. This is a calculator for study and paper trading, not advice; nothing is placed.",
)


@dataclass(frozen=True)
class Conversion:
    """1 unit of the quote currency = numerator / denominator units of the account currency.

    Kept as a fraction of stored mids so an inverse rate (1 / USD_JPY) is exact: the size is
    computed in the quote currency with a single division, and 1 / 150 is never rounded first."""

    numerator: Decimal
    path: str  # how it was obtained, for example "1 / USD_JPY mid"
    as_of: datetime | None
    data_types: tuple[str, ...]
    denominator: Decimal = ONE
    stale: bool = False

    @property
    def rate(self) -> Decimal:
        with localcontext() as ctx:
            ctx.prec = 50
            return self.numerator / self.denominator


@dataclass(frozen=True)
class Limits:
    max_risk_percent: Decimal
    max_leverage: Decimal
    max_margin_use_percent: Decimal


@dataclass(frozen=True)
class Trade:
    instrument: str
    direction: Direction
    entry: Decimal
    stop: Decimal
    target: Decimal | None
    balance: Decimal
    account_currency: str
    risk_percent: Decimal
    spread: Decimal | None  # price units; None when unknown (no fresh quote)

    def __post_init__(self) -> None:
        for name in ("entry", "stop", "balance", "risk_percent"):
            v = getattr(self, name)
            if not v.is_finite() or v <= 0:
                raise ValueError(f"{name} must be a positive decimal")
        if self.risk_percent > HUNDRED:
            raise ValueError("risk_percent must be at most 100")
        if self.direction == "long" and self.stop >= self.entry:
            raise ValueError("for a long position the stop must be below the entry")
        if self.direction == "short" and self.stop <= self.entry:
            raise ValueError("for a short position the stop must be above the entry")
        if self.target is not None:
            if not self.target.is_finite() or self.target <= 0:
                raise ValueError("target must be a positive decimal")
            if (self.direction == "long" and self.target <= self.entry) or (
                self.direction == "short" and self.target >= self.entry
            ):
                raise ValueError("the target must be on the profit side of the entry")
        if self.spread is not None and (not self.spread.is_finite() or self.spread < 0):
            raise ValueError("spread must not be negative")


@dataclass
class Result:
    units: Decimal
    lots: Decimal
    status: Literal["sized", "below_minimum", "capped_at_maximum"]
    pip_size: Decimal
    pip_value_per_lot_quote: Decimal
    pip_value_per_lot_account: Decimal
    stop_pips: Decimal
    target_pips: Decimal | None
    risk_amount: Decimal
    loss_before_costs: Decimal
    loss_after_costs: Decimal
    profit_before_costs: Decimal | None
    profit_after_costs: Decimal | None
    risk_reward_before_costs: Decimal | None
    risk_reward_after_costs: Decimal | None
    costs: dict[str, Decimal]  # spread, slippage, commission, total (account currency)
    notional: Decimal
    margin: Decimal
    position_leverage: Decimal
    max_leverage: Decimal
    account_impact_percent: Decimal
    margin_use_percent: Decimal
    exposure: dict[str, Decimal]  # currency -> signed amount in that currency
    exposure_percent: Decimal
    warnings: list[str] = field(default_factory=list)
    disclosures: tuple[str, ...] = DISCLOSURES


def pip_size(pip_location: int) -> Decimal:
    return D(1).scaleb(pip_location)


def pip_value_per_lot(
    spec: SpecValues, pip_location: int, rate: Decimal
) -> tuple[Decimal, Decimal]:
    """(in the quote currency, in the account currency) for one standard lot."""
    quote = spec.contract_size * pip_size(pip_location)
    return quote, quote * rate


def cost_per_unit(
    spec: SpecValues, pip_location: int, spread: Decimal
) -> tuple[Decimal, Decimal, Decimal]:
    """(spread, slippage, commission) per unit, in the quote currency, entry and exit."""
    slippage = 2 * spec.slippage_pips * pip_size(pip_location)
    commission = 2 * spec.commission_per_lot_side / spec.contract_size
    return spread, slippage, commission


def size(
    risk_amount: Decimal, per_unit_loss: Decimal, spec: SpecValues
) -> tuple[Decimal, Literal["sized", "below_minimum", "capped_at_maximum"]]:
    """Units for a risk amount, rounded down to the lot step; refused below the minimum, capped at
    the maximum. Both amounts are in the same currency (the engine uses the quote currency)."""
    if per_unit_loss <= 0:
        raise ValueError("the loss per unit must be positive")
    step = spec.lot_step * spec.contract_size
    with localcontext() as ctx:
        ctx.prec = 50
        # One correctly rounded division: an exact multiple of the step stays exact.
        steps = (risk_amount / (per_unit_loss * step)).to_integral_value(rounding=ROUND_DOWN)
    units = steps * step
    if units < spec.min_lots * spec.contract_size:
        return ZERO, "below_minimum"
    if units > spec.max_lots * spec.contract_size:
        return spec.max_lots * spec.contract_size, "capped_at_maximum"
    return units, "sized"


def exposure(
    instrument: str, direction: Direction, units: Decimal, entry: Decimal
) -> dict[str, Decimal]:
    """Signed exposure per currency: long EUR_USD 1,000 at 1.1 is EUR +1,000 and USD -1,100."""
    base, quote = instrument[:3], instrument[4:]
    sign = ONE if direction == "long" else -ONE
    return {base: sign * units, quote: -sign * units * entry}


def calculate(
    trade: Trade,
    spec: SpecValues,
    pip_location: int,
    display_precision: int,
    conversion: Conversion,
    limits: Limits,
    reviewed: bool,
    liquidity_tier: str,
) -> Result:
    for part in (conversion.numerator, conversion.denominator):
        if not part.is_finite() or part <= 0:
            raise ValueError("the conversion rate must be positive")
    money = D(1).scaleb(-minor_units(trade.account_currency))
    warnings: list[str] = []
    with localcontext() as ctx:
        ctx.prec = 50
        rate = conversion.rate
        pip = pip_size(pip_location)
        spread = trade.spread if trade.spread is not None else ZERO
        s_spread, s_slip, s_comm = cost_per_unit(spec, pip_location, spread)
        cost_unit = s_spread + s_slip + s_comm
        stop_distance = abs(trade.entry - trade.stop)
        risk_amount = trade.balance * trade.risk_percent / HUNDRED
        # The risk amount in the quote currency: exact for a direct or an inverse rate.
        risk_quote = risk_amount * conversion.denominator / conversion.numerator
        units, status = size(risk_quote, stop_distance + cost_unit, spec)
        loss_before = units * stop_distance * rate
        costs = {
            "spread": units * s_spread * rate,
            "slippage": units * s_slip * rate,
            "commission": units * s_comm * rate,
        }
        costs["total"] = costs["spread"] + costs["slippage"] + costs["commission"]
        loss_after = loss_before + costs["total"]
        target_distance = abs(trade.target - trade.entry) if trade.target is not None else None
        profit_before = units * target_distance * rate if target_distance is not None else None
        profit_after = profit_before - costs["total"] if profit_before is not None else None
        rr_before = target_distance / stop_distance if target_distance is not None else None
        rr_after = (
            (profit_after / loss_after) if profit_after is not None and loss_after > 0 else None
        )
        notional = units * trade.entry * rate
        margin = notional * spec.margin_rate
        leverage = notional / trade.balance
        impact = loss_after / trade.balance * HUNDRED
        margin_use = margin / trade.balance * HUNDRED
        pv_quote, pv_account = pip_value_per_lot(spec, pip_location, rate)
        flows = exposure(trade.instrument, trade.direction, units, trade.entry)
        exposure_pct = notional / trade.balance * HUNDRED

    if status == "below_minimum":
        warnings.append(
            "The risk amount is too small for the minimum position size: no position is sized."
        )
    if status == "capped_at_maximum":
        warnings.append(
            "The size is capped at the maximum lot size, so the risk taken is less than requested."
        )
    if trade.risk_percent > limits.max_risk_percent:
        warnings.append(
            f"Risk per trade {trade.risk_percent}% is above the limit of "
            f"{limits.max_risk_percent}%."
        )
    if leverage > limits.max_leverage:
        warnings.append(
            f"Position leverage {leverage:.2f}x is above the limit of {limits.max_leverage}x."
        )
    if margin > trade.balance:
        warnings.append("Insufficient margin: the margin required exceeds the balance.")
    elif margin_use > limits.max_margin_use_percent:
        warnings.append(
            f"The margin would use {margin_use:.2f}% of the balance, above the "
            f"{limits.max_margin_use_percent}% limit; a small move could lead to a margin call."
        )
    non_tradable = sorted(t for t in conversion.data_types if t != "tradable_quote")
    if non_tradable:
        warnings.append(
            f"The pip value is converted at a rate that is {', '.join(non_tradable)}, "
            "not a tradable quote."
        )
    if conversion.stale:
        warnings.append(
            "The conversion rate is stale; the account-currency values may be out of date."
        )
    if trade.spread is None:
        warnings.append(
            "No fresh quote: the spread is unknown and counted as zero, so costs are understated."
        )
    if not reviewed:
        warnings.append(
            "The contract specifications are unreviewed defaults, not a broker's terms."
        )
    if liquidity_tier == "exotic":
        warnings.append(
            "A less liquid pair: spreads, slippage and gaps can be much larger than assumed."
        )

    def m(x: Decimal) -> Decimal:
        return x.quantize(money, rounding=ROUND_HALF_UP)

    def r2(x: Decimal | None) -> Decimal | None:
        return None if x is None else x.quantize(D("0.01"), rounding=ROUND_HALF_UP)

    return Result(
        units=units,
        lots=(units / spec.contract_size).quantize(spec.lot_step) if units else ZERO,
        status=status,
        pip_size=pip,
        pip_value_per_lot_quote=pv_quote,
        pip_value_per_lot_account=pv_account.quantize(D("0.0001"), rounding=ROUND_HALF_UP),
        stop_pips=(stop_distance / pip).quantize(D("0.1"), rounding=ROUND_HALF_UP),
        target_pips=None
        if target_distance is None
        else (target_distance / pip).quantize(D("0.1"), rounding=ROUND_HALF_UP),
        risk_amount=m(risk_amount),
        loss_before_costs=m(loss_before),
        loss_after_costs=m(loss_after),
        profit_before_costs=None if profit_before is None else m(profit_before),
        profit_after_costs=None if profit_after is None else m(profit_after),
        risk_reward_before_costs=r2(rr_before),
        risk_reward_after_costs=r2(rr_after),
        costs={k: m(v) for k, v in costs.items()},
        notional=m(notional),
        margin=m(margin),
        position_leverage=r2(leverage) or ZERO,
        max_leverage=r2(ONE / spec.margin_rate) or ZERO,
        account_impact_percent=r2(impact) or ZERO,
        margin_use_percent=r2(margin_use) or ZERO,
        exposure={k: v.quantize(D(1).scaleb(-display_precision)) for k, v in flows.items()},
        exposure_percent=r2(exposure_pct) or ZERO,
        warnings=warnings,
    )
