"""Performance maths (P06-T03): golden vectors, edge cases and properties.
Methods: docs/design/performance.md."""

import ast
import json
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.modules.analytics.performance import (
    Flow,
    TwrStatus,
    ValuePoint,
    XirrStatus,
    cagr,
    external_flows,
    simple_return,
    totals,
    twr,
    xirr,
)
from app.modules.portfolio.performance_service import measure
from app.modules.transactions.holdings import Entry

VECTORS = json.loads((Path(__file__).parent / "golden" / "performance_vectors.json").read_text())


def flows_of(spec: list[list[str]]) -> list[Flow]:
    return [Flow(date.fromisoformat(d), Decimal(a)) for d, a in spec]


# --------------------------------------------------------------------------------- golden: XIRR


@pytest.mark.parametrize("case", VECTORS["xirr"], ids=lambda c: c["name"])
def test_xirr_vectors(case: dict[str, Any]) -> None:
    result = xirr(flows_of(case["flows"]))
    assert result.status == XirrStatus(case["status"])
    if case["status"] != "ok":
        assert result.rate is None
        return
    assert result.rate is not None
    assert abs(result.rate - Decimal(case["rate"])) <= Decimal(case["tolerance"])
    assert result.unique is case["unique"]


@pytest.mark.parametrize("case", VECTORS["twr"], ids=lambda c: c["name"])
def test_twr_vectors(case: dict[str, Any]) -> None:
    points = [
        ValuePoint(date.fromisoformat(d), Decimal(v), Decimal(f)) for d, v, f in case["points"]
    ]
    result = twr(points)
    assert result.status == TwrStatus(case["status"])
    if case["status"] != "ok":
        assert result.cumulative is None and result.annualized is None
        return
    assert result.cumulative == Decimal(case["cumulative"])
    if case["annualized"] is None:
        assert result.annualized is None
    else:
        assert result.annualized is not None
        assert abs(result.annualized - Decimal(case["annualized"])) < Decimal("1e-30")


@pytest.mark.parametrize("case", VECTORS["cagr"], ids=lambda c: c["name"])
def test_cagr_vectors(case: dict[str, Any]) -> None:
    start = date.fromisoformat(case["from"])
    result = cagr(
        Decimal(case["start"]), Decimal(case["end"]), start, start + timedelta(case["days"])
    )
    if case["cagr"] is None:
        assert result is None
    else:
        assert result is not None
        assert abs(result - Decimal(case["cagr"])) <= Decimal(case["tolerance"])


def test_twr_needs_increasing_dates() -> None:
    day = date(2021, 1, 1)
    with pytest.raises(ValueError, match="increasing"):
        twr([ValuePoint(day, Decimal(0), Decimal(1)), ValuePoint(day, Decimal(1))])
    with pytest.raises(ValueError, match="increasing"):
        twr([ValuePoint(day, Decimal(1)), ValuePoint(day - timedelta(1), Decimal(1))])


def test_twr_annualises_only_full_years() -> None:
    day = date(2021, 1, 1)
    points = [
        ValuePoint(day, Decimal(0), Decimal(100)),
        ValuePoint(day + timedelta(730), Decimal(121)),
    ]
    result = twr(points)
    assert result.days == 730
    assert result.annualized is not None
    assert abs(result.annualized - Decimal("0.1")) < Decimal("1e-30")
    total_loss = twr([points[0], ValuePoint(day + timedelta(730), Decimal(0))])
    assert total_loss.cumulative == Decimal(-1) and total_loss.annualized is None


def test_simple_return() -> None:
    assert simple_return(Decimal(50), Decimal(200)) == Decimal("0.25")
    assert simple_return(Decimal(-50), Decimal(200)) == Decimal("-0.25")
    assert simple_return(Decimal(10), Decimal(0)) is None
    assert simple_return(Decimal(10), Decimal(-1)) is None


# ------------------------------------------------------------------------------- external flows

T0 = datetime(2021, 1, 1, tzinfo=UTC)


def entry(kind: str, day: int, gross: str, fx: str = "1", **kw: Any) -> Entry:
    return Entry(
        id=kw.pop("id", uuid.uuid4()),
        transaction_type=kind,
        trade_date=date(2021, 1, 1) + timedelta(day),
        created_at=T0 + timedelta(seconds=day),
        asset_id=kw.pop("asset_id", None),
        quantity=kw.pop("quantity", None),
        gross_amount=Decimal(gross),
        fees=Decimal(kw.pop("fees", "0")),
        taxes=Decimal(kw.pop("taxes", "0")),
        fx=Decimal(fx),
        reverses=kw.pop("reverses", None),
        currency=kw.pop("currency", "USD"),
    )


def test_external_flows_are_deposits_withdrawals_and_transfers() -> None:
    asset = uuid.uuid4()
    reversed_deposit = entry("DEPOSIT", 3, "777")
    entries = [
        entry("DEPOSIT", 0, "1000", fees="5"),  # the fee is a cost inside, not a flow
        entry("DEPOSIT", 1, "100", fx="1.1", currency="EUR"),
        entry("BUY", 2, "500", asset_id=asset, quantity=Decimal(5)),
        entry("DIVIDEND", 4, "20", asset_id=asset),
        entry("FEE", 4, "3"),
        entry("TRANSFER_IN", 5, "300", asset_id=asset, quantity=Decimal(3)),
        entry("TRANSFER_IN", 5, "0", asset_id=asset, quantity=Decimal(8)),  # a split
        entry("TRANSFER_OUT", 6, "250", asset_id=asset, quantity=Decimal(2)),
        entry("WITHDRAWAL", 7, "200", taxes="1"),
        entry("SELL", 8, "100", asset_id=asset, quantity=Decimal(1)),
        entry("VALUATION_ADJUSTMENT", 9, "-50", asset_id=asset),
        reversed_deposit,
        entry("DEPOSIT", 4, "777", reverses=reversed_deposit.id),
    ]
    flows = external_flows(entries)
    assert [(f.on.day, f.amount) for f in flows] == [
        (1, Decimal(1000)),
        (2, Decimal("110.0")),
        (6, Decimal(300)),
        (7, Decimal(-250)),
        (8, Decimal(-200)),
    ]
    t = totals(flows)
    assert (t.contributions, t.withdrawals, t.net_invested) == (
        Decimal("1410.0"),
        Decimal(450),
        Decimal("960.0"),
    )


def test_measure_combines_the_figures() -> None:
    flows = [Flow(date(2021, 1, 1), Decimal(1000)), Flow(date(2022, 1, 1), Decimal(1000))]
    p = measure(
        "USD",
        date(2023, 1, 1),
        Decimal(2310),
        flows,
        realized_pl=Decimal(1),
        unrealized_pl=Decimal(2),
        income=Decimal(3),
        expenses=Decimal(4),
        complete=True,
    )
    assert (p.contributions, p.withdrawals, p.net_invested) == (
        Decimal(2000),
        Decimal(0),
        Decimal(2000),
    )
    assert p.total_gain == Decimal(310)
    assert p.simple_return == Decimal("0.155")
    assert p.money_weighted.status == XirrStatus.OK
    assert p.money_weighted.rate is not None
    assert abs(p.money_weighted.rate - Decimal("0.1")) < Decimal("1e-11")
    assert (p.realized_pl, p.unrealized_pl, p.income, p.expenses) == tuple(
        Decimal(i) for i in (1, 2, 3, 4)
    )
    assert p.first_flow == date(2021, 1, 1) and p.as_of == date(2023, 1, 1)
    assert p.currency == "USD" and p.complete


def test_measure_without_flows_is_explicit() -> None:
    """Purchases recorded without deposits: nothing was put in, so no return is claimed."""
    p = measure(
        "USD",
        date(2023, 1, 1),
        Decimal(500),
        [],
        realized_pl=Decimal(0),
        unrealized_pl=Decimal(500),
        income=Decimal(0),
        expenses=Decimal(0),
        complete=False,
    )
    assert p.simple_return is None
    assert p.money_weighted.status == XirrStatus.INSUFFICIENT_FLOWS
    assert p.first_flow is None and not p.complete


# ------------------------------------------------------------------------------------ properties

DAYS = st.integers(min_value=1, max_value=4000)
AMOUNT = st.decimals(min_value=1, max_value=1_000_000, places=2)


@st.composite
def investments(draw: st.DrawFn) -> list[Flow]:
    """Money in on several days, one value back at the end: exactly one sign change."""
    start = date(2010, 1, 1)
    offsets = sorted(draw(st.sets(st.integers(0, 3000), min_size=1, max_size=8)))
    flows = [Flow(start + timedelta(o), -draw(AMOUNT)) for o in offsets]
    end = start + timedelta(offsets[-1] + draw(st.integers(30, 2000)))
    paid = -sum(f.amount for f in flows)
    multiple = draw(st.decimals(min_value="0.05", max_value="20", places=3))
    return [*flows, Flow(end, (paid * multiple).quantize(Decimal("0.01")))]


def _npv(flows: list[Flow], rate: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 40
        first = flows[0].on
        return sum(
            (f.amount / (1 + rate) ** (Decimal((f.on - first).days) / 365) for f in flows),
            Decimal(0),
        )


@settings(max_examples=60, deadline=None)
@given(investments())
def test_the_xirr_rate_zeroes_the_npv(flows: list[Flow]) -> None:
    result = xirr(flows)
    assume(result.status == XirrStatus.OK)
    assert result.unique and result.rate is not None
    scale = sum(abs(f.amount) for f in flows)
    # NPV is monotone around a unique root; at the bracket ends it has opposite signs.
    below = _npv(flows, result.rate - Decimal("1e-9"))
    above = _npv(flows, result.rate + Decimal("1e-9"))
    assert (below > 0) != (above > 0) or abs(_npv(flows, result.rate)) <= scale * Decimal("1e-9")


@settings(max_examples=40, deadline=None)
@given(investments(), st.decimals(min_value="0.01", max_value=1000, places=2), DAYS)
def test_xirr_ignores_scale_and_calendar_shift(flows: list[Flow], k: Decimal, shift: int) -> None:
    base = xirr(flows)
    scaled = xirr([Flow(f.on, f.amount * k) for f in flows])
    moved = xirr([Flow(f.on + timedelta(shift), f.amount) for f in flows])
    assert base.status == scaled.status == moved.status
    if base.rate is not None:
        assert scaled.rate is not None and moved.rate is not None
        assert abs(scaled.rate - base.rate) < Decimal("1e-10")
        assert abs(moved.rate - base.rate) < Decimal("1e-10")


@settings(max_examples=60, deadline=None)
@given(AMOUNT, st.decimals(min_value="0.01", max_value=50, places=4), st.integers(365, 7300))
def test_without_flows_xirr_twr_and_cagr_agree(
    start: Decimal, multiple: Decimal, days: int
) -> None:
    day = date(2005, 3, 1)
    end_value = start * multiple
    by_cagr = cagr(start, end_value, day, day + timedelta(days))
    by_xirr = xirr([Flow(day, -start), Flow(day + timedelta(days), end_value)])
    by_twr = twr([ValuePoint(day, Decimal(0), start), ValuePoint(day + timedelta(days), end_value)])
    assert by_cagr is not None and by_xirr.rate is not None and by_twr.annualized is not None
    assert abs(by_xirr.rate - by_cagr) < Decimal("1e-10")
    assert abs(by_twr.annualized - by_cagr) < Decimal("1e-25")


@settings(max_examples=80, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.decimals(min_value="-0.9", max_value="3", places=4),  # sub-period return
            st.decimals(min_value=-500, max_value=5000, places=2),  # flow at the next point
        ),
        min_size=1,
        max_size=12,
    ),
    AMOUNT,
)
def test_twr_is_independent_of_flows(steps: list[tuple[Decimal, Decimal]], first: Decimal) -> None:
    """Build a series from known sub-period returns and arbitrary flows: TWR is their product."""
    day = date(2015, 1, 1)
    points = [ValuePoint(day, Decimal(0), first)]
    base, expected = first, Decimal(1)
    with localcontext() as ctx:
        ctx.prec = 50
        for i, (r, flow) in enumerate(steps, start=1):
            value = base * (1 + r)
            flow = max(flow, -value)  # never withdraw more than is there
            points.append(ValuePoint(day + timedelta(30 * i), value, flow))
            expected *= 1 + r
            base = value + flow
            if base == 0:
                break
    result = twr(points)
    assert result.status == TwrStatus.OK
    assert result.cumulative is not None
    assert abs(result.cumulative - (expected - 1)) < Decimal("1e-25")


def test_no_float_or_io_in_the_maths() -> None:
    tree = ast.parse(
        (Path(__file__).parents[1] / "app/modules/analytics/performance.py").read_text("utf-8")
    )
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "float" not in names
    assert not [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, float)
    ]
    modules = {
        (n.module or "").split(".")[0] if isinstance(n, ast.ImportFrom) else a.name.split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in n.names
    }
    assert modules <= {"collections", "dataclasses", "datetime", "decimal", "enum", "itertools",
                       "app"}, modules  # fmt: skip
