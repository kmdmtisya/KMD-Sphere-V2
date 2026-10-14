"""The event-driven backtest engine (P13-T08.1, T08.2). Decimal only; deterministic.

**Clock.** Bars are processed strictly in order. A decision made at the close of bar i is filled
at the open of bar i + 1; exits are checked from that bar on. Nothing reads a later bar.

**Fills and costs** (always included; the sensitivity runs only scale them up):
- every fill pays half the spread and the slippage assumption, against the position: a long buys
  at open + spread / 2 + slippage and sells at price - spread / 2 - slippage;
- commission is charged per unit per side (the specification's commission per lot per side /
  contract size);
- the spread is an assumption per pair (no historical spread is stored), the slippage and the
  commission come from the contract specification (P13-T07).

**Entries.** An entry is skipped when the next open has already gapped through the stop or the
target, or when the risk amount is too small for the minimum lot size.

**Size.** Risk per trade is a percent of the current equity, sized by the risk engine
(`risk.engine.size`: rounded down to the lot step, costs included).

**Exits,** checked bar by bar after the fill:
1. the open gapped through the stop: filled at the open (worse than the stop);
2. the open gapped through the target: filled at the open;
3. the bar touched the stop: filled at the stop. When a bar touches both the stop and the target,
   the stop is assumed first (the conservative order, since the path inside a bar is unknown);
4. the bar touched the target: filled at the target;
5. after `max_hold` bars: filled at the close;
6. at the end of the window: filled at the last close (reason `end`).

**Equity** is marked at each close: cash plus the open position at the close mid, less its exit
commission.

**Currency.** A backtest is kept in the pair's quote currency, starting from 100,000 units of
it; results are read as returns, so no conversion rate enters."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, localcontext
from typing import Literal

from app.modules.forex.backtest.strategy import Decision, Side
from app.modules.forex.risk import engine as risk
from app.modules.forex.risk.specs import SpecValues
from app.modules.forex.signals import setups as su

D = Decimal
ZERO = D(0)
ONE_PERCENT = D(1)
INITIAL_EQUITY = D(100_000)
ENGINE_VERSION = "fx-backtest-1"
ExitReason = Literal["stop", "target", "gap_stop", "gap_target", "time", "end"]


@dataclass(frozen=True)
class Costs:
    """Per unit, in price (quote currency) terms."""

    spread: Decimal  # full spread
    slippage: Decimal  # per fill
    commission: Decimal  # per unit per side

    def scaled(self, spread_and_commission: Decimal, slippage: Decimal) -> "Costs":
        return Costs(
            self.spread * spread_and_commission,
            self.slippage * slippage,
            self.commission * spread_and_commission,
        )

    @property
    def round_trip(self) -> Decimal:
        return self.spread + 2 * self.slippage + 2 * self.commission


def costs_for(spec: SpecValues, pip_location: int, spread_pips: Decimal) -> Costs:
    pip = D(1).scaleb(pip_location)
    return Costs(
        spread_pips * pip,
        spec.slippage_pips * pip,
        spec.commission_per_lot_side / spec.contract_size,
    )


@dataclass(frozen=True)
class Params:
    max_hold: int = 48  # bars
    reward_multiple: Decimal | None = None  # None: the rule's own target
    risk_percent: Decimal = ONE_PERCENT

    def __post_init__(self) -> None:
        if self.max_hold < 1:
            raise ValueError("max_hold must be at least one bar")
        if self.reward_multiple is not None and self.reward_multiple <= 0:
            raise ValueError("reward_multiple must be positive")
        if not ZERO < self.risk_percent <= 10:
            raise ValueError("risk_percent must be in (0, 10]")


@dataclass(frozen=True)
class Trade:
    rule: str
    side: Side
    decided_at: datetime
    entry_at: datetime
    exit_at: datetime
    entry_price: Decimal  # the fill, costs included
    exit_price: Decimal
    stop: Decimal
    target: Decimal
    units: Decimal
    risk_amount: Decimal  # planned loss at the stop, costs included
    pnl: Decimal  # net of every cost
    costs: Decimal  # spread, slippage and commission paid
    bars_held: int
    reason: ExitReason

    @property
    def r_multiple(self) -> Decimal:
        return self.pnl / self.risk_amount


@dataclass
class Run:
    start: int
    end: int
    initial: Decimal
    trades: list[Trade] = field(default_factory=list)
    equity: list[Decimal] = field(default_factory=list)  # at each bar's close in [start, end)
    in_market: int = 0  # bars with an open position
    skipped: dict[str, int] = field(default_factory=lambda: {"gap": 0, "too_small": 0})

    @property
    def final(self) -> Decimal:
        return self.equity[-1] if self.equity else self.initial


@dataclass
class _Open:
    decision: Decision
    decided_at: datetime
    entry_at: datetime
    entry_index: int
    entry_price: Decimal
    target: Decimal
    units: Decimal
    risk_amount: Decimal
    entry_cost: Decimal


def _sign(side: Side) -> Decimal:
    return D(1) if side == "long" else D(-1)


def _fill(side: Side, price: Decimal, costs: Costs, opening: bool) -> Decimal:
    """The price paid or received: half the spread and the slippage against the position."""
    against = costs.spread / 2 + costs.slippage
    buying = (side == "long") == opening
    return price + against if buying else price - against


def _exit_for(p: _Open, bars: su.Bars, k: int) -> tuple[Decimal, ExitReason] | None:
    side, stop, target = p.decision.side, p.decision.stop, p.target
    o, h, lo = bars.open[k], bars.high[k], bars.low[k]
    long = side == "long"
    if k > p.entry_index:  # the fill bar's open is the entry itself
        if (long and o <= stop) or (not long and o >= stop):
            return o, "gap_stop"
        if (long and o >= target) or (not long and o <= target):
            return o, "gap_target"
    if (long and lo <= stop) or (not long and h >= stop):
        return stop, "stop"
    if (long and h >= target) or (not long and lo <= target):
        return target, "target"
    return None


def simulate(
    bars: su.Bars,
    decisions: Sequence[Decision | None],
    spec: SpecValues,
    costs: Costs,
    params: Params,
    start: int,
    end: int,
    initial: Decimal = INITIAL_EQUITY,
) -> Run:
    """Runs the decisions over bars [start, end). A position still open at the end is closed at
    the last close; a decision on the last bar is not filled."""
    if not 0 <= start < end <= len(bars):
        raise ValueError("start and end must select bars")
    run = Run(start, end, initial)
    cash = initial
    pos: _Open | None = None
    with localcontext() as ctx:
        ctx.prec = 50
        for k in range(start, end):
            if pos is None and k > start and decisions[k - 1] is not None:
                pos = _enter(bars, decisions[k - 1], k, cash, spec, costs, params, run)  # type: ignore[arg-type]
            if pos is not None:
                run.in_market += 1
                hit = _exit_for(pos, bars, k)
                held = k - pos.entry_index + 1
                if hit is None and held >= params.max_hold:
                    hit = (bars.close[k], "time")
                if hit is None and k == end - 1:
                    hit = (bars.close[k], "end")
                if hit is not None:
                    cash, trade = _close(pos, bars, k, hit, costs, cash)
                    run.trades.append(trade)
                    pos = None
            mark = cash
            if pos is not None:
                s = _sign(pos.decision.side)
                mark = (
                    cash
                    + s * pos.units * (bars.close[k] - pos.entry_price)
                    - pos.units * costs.commission
                )
            run.equity.append(mark)
    return run


def _enter(
    bars: su.Bars,
    d: Decision,
    k: int,
    equity: Decimal,
    spec: SpecValues,
    costs: Costs,
    params: Params,
    run: Run,
) -> _Open | None:
    o = bars.open[k]
    long = d.side == "long"
    stop_distance = (o - d.stop) if long else (d.stop - o)
    target = d.target
    if params.reward_multiple is not None and stop_distance > 0:
        target = o + _sign(d.side) * params.reward_multiple * stop_distance
    if stop_distance <= 0 or (long and target <= o) or (not long and target >= o):
        run.skipped["gap"] += 1
        return None
    risk_amount = equity * params.risk_percent / 100
    units, status = risk.size(risk_amount, stop_distance + costs.round_trip, spec)
    if status == "below_minimum":
        run.skipped["too_small"] += 1
        return None
    price = _fill(d.side, o, costs, opening=True)
    return _Open(
        decision=d,
        decided_at=bars.ts[k - 1],
        entry_at=bars.ts[k],
        entry_index=k,
        entry_price=price,
        target=target,
        units=units,
        risk_amount=units * (stop_distance + costs.round_trip),
        entry_cost=units * (costs.spread / 2 + costs.slippage + costs.commission),
    )


def _close(
    p: _Open, bars: su.Bars, k: int, hit: tuple[Decimal, ExitReason], costs: Costs, cash: Decimal
) -> tuple[Decimal, Trade]:
    level, reason = hit
    side = p.decision.side
    price = _fill(side, level, costs, opening=False)
    pnl = _sign(side) * p.units * (price - p.entry_price) - 2 * p.units * costs.commission
    exit_cost = p.units * (costs.spread / 2 + costs.slippage + costs.commission)
    trade = Trade(
        rule=p.decision.rule,
        side=side,
        decided_at=p.decided_at,
        entry_at=p.entry_at,
        exit_at=bars.ts[k],
        entry_price=p.entry_price,
        exit_price=price,
        stop=p.decision.stop,
        target=p.target,
        units=p.units,
        risk_amount=p.risk_amount,
        pnl=pnl,
        costs=p.entry_cost + exit_cost,
        bars_held=k - p.entry_index + 1,
        reason=reason,
    )
    return cash + pnl, trade
