"""Paper trading without a database (P13-T09): fills at the bid or ask with slippage (never the
mid), limit fills, stops and targets over the quote sequence (a gap fills beyond the stop), the
levels and sizes accepted, P/L and costs, and the paper analytics worked by hand."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.forex.paper import analytics as an
from app.modules.forex.paper import book
from app.modules.forex.risk.specs import SpecValues

D = Decimal
T0 = datetime(2026, 10, 14, 12, tzinfo=UTC)
SPEC = SpecValues(D(100000), D("0.01"), D("0.01"), D(100), D("0.0333"), D("3.5"), D("0.2"))
SLIP = D("0.00002")


def tick(k: int, bid: str, ask: str) -> book.Tick:
    return book.Tick(T0 + timedelta(seconds=k), D(bid), D(ask))


def test_market_fills_are_at_the_bid_or_ask_with_slippage_never_the_mid() -> None:
    t = tick(0, "1.10000", "1.10012")
    assert book.slippage(SPEC, -4) == SLIP
    assert book.market_entry("long", t, SLIP) == D("1.10014")  # ask + slippage
    assert book.market_entry("short", t, SLIP) == D("1.09998")  # bid - slippage
    assert book.market_exit("long", t, SLIP) == D("1.09998")
    assert book.market_exit("short", t, SLIP) == D("1.10014")
    assert t.mid == D("1.10006") and book.market_entry("long", t, D(0)) != t.mid
    assert book.closing_price("long", t) == t.bid and book.closing_price("short", t) == t.ask


def test_limit_orders_fill_when_the_quote_reaches_them() -> None:
    ticks = [tick(1, "1.1005", "1.1006"), tick(2, "1.0998", "1.0999"), tick(3, "1.0990", "1.0991")]
    assert book.limit_fill("long", D("1.1000"), ticks) == ticks[1]  # ask <= limit
    assert book.limit_fill("short", D("1.1005"), ticks) == ticks[0]  # bid >= limit
    assert book.limit_fill("long", D("1.0980"), ticks) is None


def test_stops_and_targets_over_the_quote_sequence() -> None:
    quiet = [tick(1, "1.1000", "1.1001")]
    assert book.exit_for("long", D("1.0950"), D("1.1100"), quiet, SLIP) is None
    touched = [*quiet, tick(2, "1.0950", "1.0951")]
    stop = book.exit_for("long", D("1.0950"), D("1.1100"), touched, SLIP)
    assert stop is not None and stop.reason == "stop" and stop.price == D("1.09498")
    gap = [*quiet, tick(3, "1.0900", "1.0901")]
    gapped = book.exit_for("long", D("1.0950"), D("1.1100"), gap, SLIP)
    assert gapped is not None and gapped.price == D("1.08998")  # beyond the stop: a gap
    target = [*quiet, tick(4, "1.1105", "1.1106"), tick(5, "1.0900", "1.0901")]
    hit = book.exit_for("long", D("1.0950"), D("1.1100"), target, SLIP)
    assert hit is not None and hit.reason == "target" and hit.price == D("1.1100")
    assert hit.tick == target[1]  # the first trigger in time order wins
    short = book.exit_for("short", D("1.1050"), None, [tick(6, "1.1049", "1.1050")], SLIP)
    assert short is not None and short.reason == "stop" and short.price == D("1.10502")
    assert book.exit_for("short", D("1.1050"), None, quiet, SLIP) is None  # no target set


def test_levels_and_sizes() -> None:
    book.check_levels("long", D("1.1"), D("1.09"), D("1.12"))
    book.check_levels("short", D("1.1"), D("1.11"), None)
    for side, stop, target in (
        ("long", "1.11", None),
        ("short", "1.09", None),
        ("long", "1.09", "1.08"),
        ("short", "1.11", "1.12"),
    ):
        with pytest.raises(ValueError):
            book.check_levels(side, D("1.1"), D(stop), None if target is None else D(target))  # type: ignore[arg-type]
    assert book.units_for(D("0.25"), SPEC) == D(25000)
    for bad in ("0", "0.005", "0.013", "101", "-1"):
        with pytest.raises(ValueError):
            book.units_for(D(bad), SPEC)
    assert book.commission(D(25000), SPEC) == D("0.875")  # 3.5 per lot per side


def test_pnl_and_costs() -> None:
    assert book.pnl_quote("long", D(10000), D("1.10014"), D("1.10998")) == D("98.40")
    assert book.pnl_quote("short", D(10000), D("1.10014"), D("1.10998")) == D("-98.40")
    assert book.spread_and_slippage(D(10000), D("1.10014"), D("1.10006")) == D("0.80")
    assert book.sign("long") == 1 and book.sign("short") == -1


@dataclass
class Row:
    instrument: str
    strategy_tag: str | None
    realised_pnl: Decimal | None
    costs: Decimal | None


def test_analytics_worked_by_hand() -> None:
    rows = [
        Row("EUR_USD", "breakout", D(100), D(2)),
        Row("EUR_USD", "breakout", D(-50), D(2)),
        Row("USD_JPY", None, D(-50), D(3)),
        Row("USD_JPY", "breakout", D(200), D(3)),
        Row("EUR_USD", None, D(-25), D(1)),
    ]
    perf = an.performance(D(1000), rows)
    o = perf.overall
    assert o.trades == 5 and o.wins == 2 and o.win_rate == D("0.4")
    assert o.net == D(175) and o.gross_profit == D(300) and o.gross_loss == D(125)
    assert o.profit_factor == D("2.4") and o.average == D(35)
    assert o.best == D(200) and o.worst == D(-50) and o.costs == D(11)
    # closed balance 1100, 1050, 1000, 1200, 1175: the worst fall is 100 from 1100
    assert perf.max_drawdown.quantize(D("1e-20")) == D("0.09090909090909090909")  # 100 / 1100
    assert perf.return_on_start == D("0.175") and perf.longest_losing_streak == 2
    assert set(perf.by_tag) == {"breakout", "untagged"}
    assert perf.by_tag["breakout"].net == D(250) and perf.by_tag["untagged"].trades == 2
    assert perf.by_instrument["USD_JPY"].net == D(150)
    empty = an.performance(D(1000), [])
    assert empty.overall.win_rate is None and empty.overall.profit_factor is None
    assert empty.max_drawdown == 0 and empty.overall.best is None
