"""P06-T10: the application's financial engines against an independent oracle (tests/oracle.py,
exact rational arithmetic written from the specification). Methods: docs/financial-methods.md."""

import math
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from app.core.money import percentages
from app.modules.analytics import allocation as alloc
from app.modules.analytics.performance import (
    Flow,
    ValuePoint,
    XirrStatus,
    external_flows,
    twr,
    xirr,
)
from app.modules.analytics.risk import volatility
from app.modules.forecasting.engine import (
    ForecastInput,
    Frequency,
    project,
    required_contribution,
    required_contribution_by,
)
from app.modules.networth.income import totals
from app.modules.networth.networth import Debt
from app.modules.networth.networth import compute as net_worth
from app.modules.portfolio.performance_service import measure as performance
from app.modules.portfolio.summary import HoldingInput, Rate, ValuationInput, compute_summary
from app.modules.transactions.holdings import Entry, compute
from app.modules.transactions.income_events_service import Payment
from tests import oracle as o

D = Decimal
F = Fraction
DAY0 = date(2024, 1, 1)
T0 = datetime(2024, 1, 1, tzinfo=UTC)
ASSETS = ["a", "b"]
TOL = Fraction(1, 10**30)


def close(engine: Decimal | Fraction, exact: Fraction, tol: Fraction = TOL) -> bool:
    scale = abs(exact) if abs(exact) > 1 else Fraction(1)
    return abs(o.frac(engine) - exact) <= tol * scale


# ------------------------------------------------------------------------- random ledgers

AMOUNT = st.decimals(min_value="0.01", max_value=100000, places=2)
QTY = st.decimals(min_value="0.001", max_value=500, places=3)
FX = st.decimals(min_value="0.05", max_value=200, places=6)


@st.composite
def ledgers(draw: st.DrawFn) -> list[o.Tx]:
    held: dict[str, Fraction] = {a: F(0) for a in ASSETS}
    out: list[o.Tx] = []
    for i in range(draw(st.integers(1, 25))):
        on = DAY0 + timedelta(days=i)
        kind = draw(
            st.sampled_from(
                [
                    "DEPOSIT",
                    "BUY",
                    "BUY",
                    "SELL",
                    "DIVIDEND",
                    "FEE",
                    "TRANSFER_IN",
                    "TRANSFER_OUT",
                    "WITHDRAWAL",
                    "REVERSE",
                ]
            )
        )
        asset = draw(st.sampled_from(ASSETS))
        fx = o.frac(draw(st.sampled_from([D(1), draw(FX)])))
        fees = o.frac(draw(st.sampled_from([D(0), D("1.25")])))
        if kind == "REVERSE":
            candidates = [
                t
                for t in out
                if t.kind in ("DEPOSIT", "DIVIDEND", "FEE", "WITHDRAWAL")
                and not t.reverses
                and t.id not in {x.reverses for x in out}
            ]
            if not candidates:
                continue
            target = draw(st.sampled_from(candidates))
            out.append(
                o.Tx(
                    f"t{i}",
                    target.kind,
                    on,
                    i,
                    target.asset,
                    target.quantity,
                    target.gross,
                    target.fees,
                    target.taxes,
                    target.fx,
                    target.currency,
                    reverses=target.id,
                )
            )
            continue
        if kind in ("SELL", "TRANSFER_OUT"):
            if held[asset] == 0:
                continue
            qty = min(held[asset], o.frac(draw(QTY)))
            held[asset] -= qty
        elif kind in ("BUY", "TRANSFER_IN"):
            qty = o.frac(draw(QTY))
            held[asset] += qty
        else:
            qty = F(0)
        with_asset = kind in ("BUY", "SELL", "DIVIDEND", "TRANSFER_IN", "TRANSFER_OUT")
        out.append(
            o.Tx(
                f"t{i}",
                kind,
                on,
                i,
                asset if with_asset else None,
                qty,
                o.frac(draw(AMOUNT)),
                fees,
                F(0),
                fx,
            )
        )
    return out


def to_entries(ledger: list[o.Tx]) -> list[Entry]:
    ids = {t.id: uuid.uuid5(uuid.NAMESPACE_URL, t.id) for t in ledger}
    assets = {a: uuid.uuid5(uuid.NAMESPACE_URL, a) for a in ASSETS}

    def dec(x: Fraction) -> Decimal:
        return D(x.numerator) / D(x.denominator)

    return [
        Entry(
            ids[t.id],
            t.kind,
            t.on,
            T0 + timedelta(seconds=t.order),
            assets[t.asset] if t.asset else None,
            dec(t.quantity) if t.quantity else None,
            dec(t.gross),
            dec(t.fees),
            dec(t.taxes),
            dec(t.fx),
            ids[t.reverses] if t.reverses else None,
            t.currency,
        )
        for t in ledger
    ]


@settings(max_examples=200, deadline=None)
@given(ledgers())
def test_holdings_match_the_oracle(ledger: list[o.Tx]) -> None:
    engine = compute(to_entries(ledger))
    exact = o.holdings(ledger)
    by_id = {uuid.uuid5(uuid.NAMESPACE_URL, a): a for a in ASSETS}
    assert {by_id[k] for k in engine} == set(exact)
    for asset_id, p in engine.items():
        x = exact[by_id[asset_id]]
        assert o.frac(p.quantity) == x.quantity
        for got, want in (
            (p.cost_basis, x.cost),
            (p.realized_pl, x.realized),
            (p.income, x.income),
            (p.expenses, x.expenses),
        ):
            assert close(got, want), (got, want)


@settings(max_examples=150, deadline=None)
@given(ledgers(), st.lists(AMOUNT, min_size=2, max_size=2))
def test_the_summary_matches_the_oracle(ledger: list[o.Tx], values: list[Decimal]) -> None:
    """Every posting in the portfolio currency, so cash needs no conversion."""
    ledger = [
        o.Tx(
            t.id,
            t.kind,
            t.on,
            t.order,
            t.asset,
            t.quantity,
            t.gross,
            t.fees,
            t.taxes,
            F(1),
            "USD",
            t.reverses,
        )
        for t in ledger
    ]
    entries = to_entries(ledger)
    positions = compute(entries)
    holdings_in = [
        HoldingInput(a, p.quantity, p.cost_basis, p.realized_pl, p.income, p.expenses)
        for a, p in positions.items()
    ]
    valuations = [
        ValuationInput(uuid.uuid5(uuid.NAMESPACE_URL, a), v, "USD", T0)
        for a, v in zip(ASSETS, values, strict=True)
    ]
    s = compute_summary("USD", holdings_in, valuations, entries, {})
    exact = o.holdings(ledger)
    valued = {
        a: o.frac(v)
        for a, v in zip(ASSETS, values, strict=True)
        if a not in exact or exact[a].quantity > 0
    }
    cash = o.cash(ledger).get("USD", F(0))
    assert close(s.cash, cash)
    assert close(s.holdings_value, sum(valued.values(), F(0)))
    assert close(
        s.unrealized_pl, sum((v - exact[a].cost for a, v in valued.items() if a in exact), F(0))
    )
    assert close(s.realized_pl, sum((p.realized for p in exact.values()), F(0)))
    deposits = sum((t.gross for t in o.effective(ledger) if t.kind == "DEPOSIT"), F(0))
    withdrawals = sum((t.gross for t in o.effective(ledger) if t.kind == "WITHDRAWAL"), F(0))
    assert close(s.net_contributions, deposits - withdrawals)
    # Performance: flows include transfers; gain and simple return from the same figures.
    flows = external_flows(entries)
    assert [(f.on, o.frac(f.amount)) for f in flows] == o.external_flows(ledger)
    p = performance(
        "USD",
        DAY0 + timedelta(days=60),
        s.total_value,
        flows,
        realized_pl=s.realized_pl,
        unrealized_pl=s.unrealized_pl,
        income=s.income,
        expenses=s.expenses,
        complete=True,
    )
    contributions = sum((a for _, a in o.external_flows(ledger) if a > 0), F(0))
    net = sum((a for _, a in o.external_flows(ledger)), F(0))
    gain = o.frac(s.total_value) - net
    assert close(p.total_gain, gain)
    expected = o.simple_return(gain, contributions)
    assert (p.simple_return is None) == (expected is None)
    if p.simple_return is not None and expected is not None:
        assert close(p.simple_return, expected)


@settings(max_examples=150, deadline=None)
@given(st.lists(st.decimals(min_value=0, max_value=10**7, places=2), min_size=1, max_size=12))
def test_allocation_weights_and_concentration_match_the_oracle(values: list[Decimal]) -> None:
    assume(sum(values) > 0)
    exact = [o.frac(v) for v in values]
    weights = percentages(values)
    assert weights is not None
    assert [o.frac(w) for w in weights] == o.largest_remainder(exact)
    parts = [alloc.Part(f"p{i}", v, "stock", "USD") for i, v in enumerate(values)]
    c = alloc.concentration(parts)
    assert c.hhi is not None and close(c.hhi, o.herfindahl(exact))


@settings(max_examples=120, deadline=None)
@given(
    st.decimals(min_value=0, max_value=1_000_000, places=2),
    st.decimals(min_value=0, max_value=10_000, places=2),
    st.decimals(min_value=-20, max_value=50, places=2),
    st.decimals(min_value=0, max_value=5, places=2),
    st.decimals(min_value=0, max_value=20, places=2),
    st.integers(1, 40),
    st.sampled_from(list(Frequency)),
)
def test_monthly_compounding_forecasts_match_the_oracle(
    initial: Decimal,
    contribution: Decimal,
    rate: Decimal,
    fee: Decimal,
    growth: Decimal,
    years: int,
    frequency: Frequency,
) -> None:
    inp = ForecastInput(
        "USD", initial, contribution, rate, years, growth, D(0), fee, Frequency.MONTHLY, frequency
    )
    p = project(inp)
    value, paid = o.monthly_forecast(
        o.frac(initial),
        o.frac(contribution),
        o.frac(rate),
        o.frac(fee),
        years * 12,
        every=12 // frequency.per_year,
        growth=o.frac(growth),
    )
    assert p.final_nominal == o.to_decimal(value, 2)
    assert p.total_contributions == o.to_decimal(paid, 2)
    assert p.total_growth == p.final_nominal - p.total_contributions


@settings(max_examples=120, deadline=None)
@given(
    st.decimals(min_value=0, max_value=100_000, places=2),
    st.decimals(min_value=1, max_value=10_000_000, places=2),
    st.decimals(min_value=-20, max_value=50, places=2),
    st.decimals(min_value=0, max_value=5, places=2),
    st.integers(1, 720),
)
def test_required_contributions_match_the_annuity_closed_form(
    initial: Decimal, target: Decimal, rate: Decimal, fee: Decimal, months: int
) -> None:
    inp = ForecastInput("USD", initial, D(0), rate, max(1, months // 12), D(0), D(0), fee)
    exact = o.required_monthly(o.frac(initial), o.frac(target), o.frac(rate), o.frac(fee), months)
    by_date = required_contribution_by(inp, target, months)
    assert by_date is not None and close(by_date, exact, F(1, 10**25))
    if months % 12 == 0:
        assert close(required_contribution(inp, target).exact, exact, F(1, 10**25))


@settings(max_examples=100, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.decimals(min_value="-0.9", max_value=3, places=4),
            st.decimals(min_value=-100, max_value=5000, places=2),
        ),
        min_size=1,
        max_size=15,
    ),
)
def test_time_weighted_return_matches_the_oracle(steps: list[tuple[Decimal, Decimal]]) -> None:
    value = F(1000)
    points: list[tuple[Fraction, Fraction]] = []
    for r, flow in steps:
        f = max(o.frac(flow), -value + 1)
        points.append((value, f))
        value = (value + f) * (1 + o.frac(r))
    points.append((value, F(0)))

    def dec(x: Fraction) -> Decimal:
        return D(x.numerator) / D(x.denominator)

    engine = twr(
        ValuePoint(DAY0 + timedelta(days=30 * i), dec(v), dec(f)) for i, (v, f) in enumerate(points)
    )
    assert engine.cumulative is not None
    assert close(engine.cumulative, o.twr(points), F(1, 10**25))


@settings(max_examples=80, deadline=None)
@given(
    st.lists(st.decimals(min_value=100, max_value=10000, places=2), min_size=1, max_size=6),
    st.integers(30, 1500),
    st.decimals(min_value="0.3", max_value=4, places=3),
)
def test_xirr_matches_newtons_method(
    deposits: list[Decimal], horizon: int, multiple: Decimal
) -> None:
    flows = [(DAY0 + timedelta(days=60 * i), -d) for i, d in enumerate(deposits)]
    end = DAY0 + timedelta(days=60 * len(deposits) + horizon)
    flows.append((end, (sum(deposits) * multiple).quantize(D("0.01"))))
    engine = xirr(Flow(d, a) for d, a in flows)
    assume(engine.status == XirrStatus.OK)
    newton = o.xirr_newton(flows)
    assume(newton is not None)
    assert engine.rate is not None and newton is not None
    assert abs(engine.rate - newton) < D("1e-9")


@settings(max_examples=100, deadline=None)
@given(st.lists(st.decimals(min_value="-0.9", max_value=3, places=4), min_size=2, max_size=30))
def test_volatility_matches_the_exact_variance(returns: list[Decimal]) -> None:
    period, annual = volatility(returns, 12)
    variance = o.sample_variance([o.frac(r) for r in returns])
    # Squared exactly: the engine's square roots carry 34 significant digits.
    assert close(o.frac(period) ** 2, variance, F(1, 10**30))
    assert close(o.frac(annual) ** 2, variance * 12, F(1, 10**30))


@settings(max_examples=100, deadline=None)
@given(
    st.lists(
        st.tuples(
            st.decimals(min_value=0, max_value=10000, places=2),
            st.decimals(min_value=0, max_value=100, places=2),
            st.decimals(min_value=0, max_value=100, places=2),
            st.decimals(min_value="0.01", max_value=200, places=6),
        ),
        max_size=20,
    ),
)
def test_income_totals_match_the_oracle(
    rows: list[tuple[Decimal, Decimal, Decimal, Decimal]],
) -> None:
    payments = [
        Payment(uuid.uuid4(), None, "INTEREST", DAY0, "EUR", g, f, t, fx) for g, f, t, fx in rows
    ]
    t = totals(payments)
    gross = sum((o.frac(g) * o.frac(fx) for g, _, _, fx in rows), F(0))
    fees = sum((o.frac(f) * o.frac(fx) for _, f, _, fx in rows), F(0))
    taxes = sum((o.frac(x) * o.frac(fx) for _, _, x, fx in rows), F(0))
    assert close(t.gross, gross) and close(t.fees, fees) and close(t.taxes, taxes)
    assert close(t.net, gross - fees - taxes)


@settings(max_examples=100, deadline=None)
@given(
    st.decimals(min_value=-(10**6), max_value=10**8, places=4),
    st.lists(
        st.tuples(
            st.sampled_from(["USD", "EUR"]), st.decimals(min_value=0, max_value=10**6, places=2)
        ),
        max_size=10,
    ),
)
def test_net_worth_matches_the_oracle(assets: Decimal, debts: list[tuple[str, Decimal]]) -> None:
    rate = D("1.0837")
    rates = {"EUR": Rate("EUR", rate, T0, stale=False)}
    nw = net_worth(
        "USD", assets, [Debt(uuid.uuid4(), "d", "other", c, b, DAY0) for c, b in debts], rates
    )
    lines = [o.half_up(o.frac(b) * (o.frac(rate) if c == "EUR" else 1), 2) for c, b in debts]
    assert o.frac(nw.liabilities) == sum(lines, F(0))
    assert o.frac(nw.assets) == o.half_up(o.frac(assets), 2)
    assert o.frac(nw.net_worth) == o.half_up(o.frac(assets), 2) - sum(lines, F(0))


def test_the_oracle_rounds_half_away_from_zero() -> None:
    assert o.half_up(F(1, 200), 2) == F(1, 100)  # 0.005 -> 0.01
    assert o.half_up(F(-1, 200), 2) == F(-1, 100)
    assert o.half_up(F(5, 2), 0) == 3 and o.half_up(F(-5, 2), 0) == -3
    assert o.largest_remainder([F(1), F(1), F(1)]) == [F(3334, 100), F(3333, 100), F(3333, 100)]


# -------------------------------------------------------- named vectors (financial-methods.md 15)


def test_rounding_ties_go_away_from_zero_everywhere() -> None:
    """0.41 x 2.5 = 1.025 exactly: half-up gives 1.03 (half-even would give 1.02)."""
    rates = {"EUR": Rate("EUR", D("2.5"), T0, stale=False)}
    nw = net_worth(
        "USD", D("0.005"), [Debt(uuid.uuid4(), "d", "other", "EUR", D("0.41"), DAY0)], rates
    )
    assert (nw.liabilities, nw.assets) == (D("1.03"), D("0.01"))
    assert o.half_up(F(1025, 1000), 2) == F(103, 100)
    tie = project(ForecastInput("USD", D("0.10"), D(0), D(5), 1, compounding=Frequency.YEARLY))
    assert tie.final_nominal == D("0.11")  # 0.105


def test_the_workbook_vectors() -> None:
    defaults = ForecastInput("USD", D(10000), D(500), D(8), 20, D(0), D(0), D("0.5"))
    p = project(defaults)
    value, paid = o.monthly_forecast(F(10000), F(500), F(8), F(1, 2), 240)
    assert (p.final_nominal, p.total_contributions) == (D("321473.53"), D("130000.00"))
    assert (o.to_decimal(value, 2), o.to_decimal(paid, 2)) == (D("321473.53"), D("130000.00"))

    goal = required_contribution(defaults, D(1000000))
    monthly = o.required_monthly(F(10000), F(1000000), F(8), F(1, 2), 240)
    assert goal.amount == D("1725.38")  # rounded up so it is enough (ADR-0006 exception 1)
    assert math.ceil(monthly * 100) == 172538 and o.to_decimal(monthly, 2) == D("1725.37")

    ledger = [
        o.Tx("1", "BUY", DAY0, 1, "a", F(10), F(1000), F(4), F(0), F(1)),
        o.Tx("2", "BUY", DAY0 + timedelta(days=31), 2, "a", F(10), F(1200), F(0), F(0), F(1)),
        o.Tx("3", "SELL", DAY0 + timedelta(days=60), 3, "a", F(5), F(650), F(2), F(0), F(1)),
    ]
    [(_, position)] = compute(to_entries(ledger)).items()
    exact = o.holdings(ledger)["a"]
    assert (position.quantity, position.cost_basis, position.realized_pl) == (D(15), D(1653), D(97))
    assert (exact.quantity, exact.cost, exact.realized) == (F(15), F(1653), F(97))
    assert exact.cost / exact.quantity == F(551, 5)  # 110.20

    assert percentages([D(1), D(1), D(1)]) == [D("33.34"), D("33.33"), D("33.33")]
    points = [
        ValuePoint(DAY0, D(0), D(1000)),
        ValuePoint(DAY0 + timedelta(days=100), D(1100), D(500)),
        ValuePoint(DAY0 + timedelta(days=200), D(1760)),
    ]
    assert twr(points).cumulative == D("0.21")
    assert o.sample_variance([F(1, 10), F(-1, 10), F(1, 10), F(-1, 10)]) == F(1, 75)


@settings(max_examples=100, deadline=None)
@given(
    st.decimals(min_value=1, max_value=100000, places=2),
    st.decimals(min_value=0, max_value=200000, places=2),
    st.integers(7, 40),
    st.lists(
        st.tuples(st.integers(1, 40), st.decimals(min_value=-500, max_value=5000, places=2)),
        max_size=6,
    ),
)
def test_modified_dietz_matches_the_oracle(
    start: Decimal, end: Decimal, length: int, raw: list[tuple[int, Decimal]]
) -> None:
    from app.modules.analytics.risk import Observation, period_returns

    flows = [(min(d, length), a) for d, a in raw]
    first = DAY0
    detail = tuple((first + timedelta(days=d), a) for d, a in flows)
    total = sum((a for _, a in detail), D(0))
    weighted = sum((F(length - d + 1, length) * o.frac(a) for d, a in flows), F(0))
    assume(o.frac(start) + weighted > 0)
    series = [Observation(first, start, total, True, detail),
              Observation(first + timedelta(days=length), end, D(0))]  # fmt: skip
    got = period_returns(series)
    assert got is not None
    expected = o.modified_dietz(o.frac(start), o.frac(end), length,
                                [(d, o.frac(a)) for d, a in flows])  # fmt: skip
    assert close(got[0][1], expected, F(1, 10**28))
