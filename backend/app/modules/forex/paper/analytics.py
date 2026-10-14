"""Paper-trading performance (P13-T09.5). PAPER TRADING: a series of its own, labelled `paper`,
never added to backtested results (P13-T08), live-observed results or any real portfolio's
analytics. Decimal only, over closed positions in the order they closed.

- net P/L = sum of realised P/L (account currency, net of spread, slippage and commission);
- win rate = positions with realised P/L > 0 / closed positions;
- profit factor = gross profit / gross loss (none without a loss);
- average and expectancy: the mean realised P/L per closed position;
- maximum drawdown = the largest fall of the closed balance (starting balance + cumulative
  realised P/L) from its running peak, as a share of that peak;
- return on the starting balance = net P/L / starting balance;
- breakdowns by strategy tag (untagged positions under "untagged") and by pair."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext
from typing import Protocol

D = Decimal
ZERO = D(0)


class Closed(Protocol):
    instrument: str
    strategy_tag: str | None
    realised_pnl: Decimal | None
    costs: Decimal | None


@dataclass(frozen=True)
class Summary:
    trades: int
    wins: int
    win_rate: Decimal | None
    net: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
    profit_factor: Decimal | None
    average: Decimal | None
    best: Decimal | None
    worst: Decimal | None
    costs: Decimal


@dataclass(frozen=True)
class Performance:
    overall: Summary
    max_drawdown: Decimal
    return_on_start: Decimal
    longest_losing_streak: int
    by_tag: dict[str, Summary]
    by_instrument: dict[str, Summary]


def summary(rows: Sequence[Closed]) -> Summary:
    pnl = [r.realised_pnl or ZERO for r in rows]
    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p <= 0]
    gross_profit, gross_loss = sum(wins, ZERO), -sum(losses, ZERO)
    n = len(pnl)
    with localcontext() as ctx:
        ctx.prec = 50
        return Summary(
            trades=n,
            wins=len(wins),
            win_rate=D(len(wins)) / n if n else None,
            net=sum(pnl, ZERO),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=gross_profit / gross_loss if gross_loss > 0 else None,
            average=sum(pnl, ZERO) / n if n else None,
            best=max(pnl) if pnl else None,
            worst=min(pnl) if pnl else None,
            costs=sum((r.costs or ZERO for r in rows), ZERO),
        )


def max_drawdown(start: Decimal, pnl: Sequence[Decimal]) -> Decimal:
    peak = balance = start
    worst = ZERO
    with localcontext() as ctx:
        ctx.prec = 50
        for p in pnl:
            balance += p
            peak = max(peak, balance)
            if peak > 0:
                worst = max(worst, (peak - balance) / peak)
    return worst


def longest_losing_streak(pnl: Sequence[Decimal]) -> int:
    best = current = 0
    for p in pnl:
        current = current + 1 if p <= 0 else 0
        best = max(best, current)
    return best


def _grouped(rows: Sequence[Closed], key: Callable[[Closed], str]) -> dict[str, Summary]:
    groups: dict[str, list[Closed]] = {}
    for r in rows:
        groups.setdefault(key(r), []).append(r)
    return {k: summary(v) for k, v in sorted(groups.items())}


def performance(start: Decimal, rows: Sequence[Closed]) -> Performance:
    """`rows` are the closed positions in the order they closed."""
    pnl = [r.realised_pnl or ZERO for r in rows]
    overall = summary(rows)
    with localcontext() as ctx:
        ctx.prec = 50
        ret = overall.net / start
    return Performance(
        overall=overall,
        max_drawdown=max_drawdown(start, pnl),
        return_on_start=ret,
        longest_losing_streak=longest_losing_streak(pnl),
        by_tag=_grouped(rows, lambda r: r.strategy_tag or "untagged"),
        by_instrument=_grouped(rows, lambda r: r.instrument),
    )
