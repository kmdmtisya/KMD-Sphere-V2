"""Backtest metrics (P13-T08.3). Decimal at 50 digits; every figure is net of costs.

- total return = final equity / initial equity - 1;
- maximum drawdown = the largest fall from a running peak of the marked equity, as a share of
  that peak;
- win rate = winning trades / trades (a trade with pnl > 0 wins; pnl = 0 counts as a loss);
- profit factor = gross profit / gross loss; none when there is no loss;
- average trade = mean pnl; expectancy = mean R multiple (pnl / the planned risk of the trade);
- longest losing streak = the most consecutive losing trades;
- exposure = bars with an open position / bars in the window;
- Sharpe = mean / sample standard deviation of the per-bar equity returns x sqrt(bars per year);
  Sortino uses the downside deviation sqrt(mean(min(r, 0)^2)) instead; risk-free rate 0; none
  with fewer than two returns or no variation;
- bars per year: 260 trading days of 24 hours (5m 74,880; 15m 24,960; 1H 6,240; 4H 1,560;
  1D 260).
Display rounding (report): returns and shares as fractions to 6 places, ratios to 0.01, money to
0.01."""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, localcontext

from app.modules.forex.backtest.engine import Run, Trade

D = Decimal
ZERO = D(0)
BARS_PER_YEAR = {"5m": 74_880, "15m": 24_960, "1H": 6_240, "4H": 1_560, "1D": 260}


@dataclass(frozen=True)
class Metrics:
    trades: int
    wins: int
    win_rate: Decimal | None
    total_return: Decimal
    max_drawdown: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
    profit_factor: Decimal | None
    average_trade: Decimal | None
    expectancy_r: Decimal | None
    longest_losing_streak: int
    exposure: Decimal
    sharpe: Decimal | None
    sortino: Decimal | None
    costs: Decimal


def max_drawdown(equity: Sequence[Decimal]) -> Decimal:
    peak, worst = None, ZERO
    for e in equity:
        peak = e if peak is None or e > peak else peak
        if peak > 0:
            worst = max(worst, (peak - e) / peak)
    return worst


def longest_losing_streak(trades: Sequence[Trade]) -> int:
    best = current = 0
    for t in trades:
        current = current + 1 if t.pnl <= 0 else 0
        best = max(best, current)
    return best


def bar_returns(initial: Decimal, equity: Sequence[Decimal]) -> list[Decimal]:
    out, previous = [], initial
    for e in equity:
        out.append(e / previous - 1 if previous > 0 else ZERO)
        previous = e
    return out


def sharpe_sortino(
    returns: Sequence[Decimal], per_year: int
) -> tuple[Decimal | None, Decimal | None]:
    n = len(returns)
    if n < 2:
        return None, None
    mean = sum(returns, ZERO) / n
    var = sum(((r - mean) ** 2 for r in returns), ZERO) / (n - 1)
    downside = sum((min(r, ZERO) ** 2 for r in returns), ZERO) / n
    scale = D(per_year).sqrt()
    sharpe = mean / var.sqrt() * scale if var > 0 else None
    sortino = mean / downside.sqrt() * scale if downside > 0 else None
    return sharpe, sortino


def compute(run: Run, timeframe: str) -> Metrics:
    return summarise(
        run.trades, run.initial, run.equity, run.in_market, run.end - run.start, timeframe
    )


def summarise(
    trades: Sequence[Trade],
    initial: Decimal,
    equity: Sequence[Decimal],
    in_market: int,
    bars: int,
    timeframe: str,
) -> Metrics:
    with localcontext() as ctx:
        ctx.prec = 50
        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        gross_profit = sum((t.pnl for t in wins), ZERO)
        gross_loss = -sum((t.pnl for t in losses), ZERO)
        n = len(trades)
        final = equity[-1] if equity else initial
        sharpe, sortino = sharpe_sortino(bar_returns(initial, equity), BARS_PER_YEAR[timeframe])
        return Metrics(
            trades=n,
            wins=len(wins),
            win_rate=D(len(wins)) / n if n else None,
            total_return=final / initial - 1,
            max_drawdown=max_drawdown([initial, *equity]),
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            profit_factor=gross_profit / gross_loss if gross_loss > 0 else None,
            average_trade=sum((t.pnl for t in trades), ZERO) / n if n else None,
            expectancy_r=sum((t.r_multiple for t in trades), ZERO) / n if n else None,
            longest_losing_streak=longest_losing_streak(trades),
            exposure=D(in_market) / bars if bars else ZERO,
            sharpe=sharpe,
            sortino=sortino,
            costs=sum((t.costs for t in trades), ZERO),
        )
