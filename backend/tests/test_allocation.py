"""Allocation and concentration maths (P06-T04): a hand-computed portfolio, edge cases and
properties. Methods: docs/design/allocation.md."""

import ast
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.analytics.allocation import (
    TOP,
    Dimension,
    Part,
    allocate,
    cash,
    concentration,
    herfindahl,
)
from app.modules.assets.service import Classification
from app.modules.portfolio.allocation_service import measure
from app.modules.portfolio.summary import Summary

D = Decimal

# A 10,000 portfolio (base currency USD), hand-computed.
PARTS = [
    Part("a", D(5000), "stock", "USD", "US", "Technology"),
    Part("b", D(2000), "stock", "USD", "US", "Technology"),
    Part("c", D(2000), "etf", "USD", "IE"),
    Part("d", D(600), "bond", "KES", "KE"),
    cash("USD", D(300)),
    cash("EUR", D(100)),
]


def table(dimension: Dimension) -> list[tuple[str | None, Decimal, Decimal | None, int]]:
    return [(s.key, s.value, s.weight_percent, s.parts) for s in allocate(PARTS, dimension).slices]


def test_by_asset_class() -> None:
    assert table(Dimension.ASSET_CLASS) == [
        ("stock", D(7000), D("70.00"), 2),
        ("etf", D(2000), D("20.00"), 1),
        ("bond", D(600), D("6.00"), 1),
        ("cash", D(400), D("4.00"), 2),
    ]
    # 0.7^2 + 0.2^2 + 0.06^2 + 0.04^2
    assert allocate(PARTS, Dimension.ASSET_CLASS).hhi == D("0.5352")


def test_by_currency_of_the_valuation_and_of_cash() -> None:
    assert table(Dimension.CURRENCY) == [
        ("USD", D(9300), D("93.00"), 4),
        ("KES", D(600), D("6.00"), 1),
        ("EUR", D(100), D("1.00"), 1),
    ]


def test_by_country_with_cash_unclassified() -> None:
    assert table(Dimension.COUNTRY) == [
        ("US", D(7000), D("70.00"), 2),
        ("IE", D(2000), D("20.00"), 1),
        ("KE", D(600), D("6.00"), 1),
        (None, D(400), D("4.00"), 2),
    ]


def test_by_sector_from_metadata() -> None:
    assert table(Dimension.SECTOR) == [
        ("Technology", D(7000), D("70.00"), 2),
        (None, D(3000), D("30.00"), 4),
    ]


def test_every_dimension_adds_up_to_the_same_total() -> None:
    for d in Dimension:
        a = allocate(PARTS, d)
        assert a.total == D(10000) and a.dimension == d
        assert sum(s.value for s in a.slices) == a.total
        assert sum(s.weight_percent or 0 for s in a.slices) == D("100.00")
        assert sum(s.parts for s in a.slices) == len(PARTS)


def test_concentration_of_positions() -> None:
    c = concentration(PARTS)
    # Shares 0.5, 0.2, 0.2, 0.06, 0.03, 0.01.
    assert c.positions == 6
    assert c.hhi == D("0.3346")
    assert c.effective_positions is not None
    assert abs(c.effective_positions * c.hhi - 1) < D("1e-45")  # 1 / 0.3346 = 2.98864...
    assert str(c.effective_positions).startswith("2.98864315600717")
    assert c.top == {1: D("0.5"), 3: D("0.9"), 5: D("0.99")}
    assert c.largest == "a"


def test_largest_remainder_and_deterministic_order() -> None:
    parts = [Part("x", D(1), "stock", "USD", "ZZ"), Part("y", D(1), "etf", "USD"),
             Part("z", D(1), "bond", "USD", "AA")]  # fmt: skip
    by_class = allocate(parts, Dimension.ASSET_CLASS)
    # Equal values: ordered by key; the first gets the remainder.
    assert [(s.key, s.weight_percent) for s in by_class.slices] == [
        ("bond", D("33.34")),
        ("etf", D("33.33")),
        ("stock", D("33.33")),
    ]
    by_country = allocate(parts, Dimension.COUNTRY)
    assert [s.key for s in by_country.slices] == ["AA", "ZZ", None]  # unclassified last


def test_a_negative_cash_balance_leaves_shares_undefined() -> None:
    parts = [Part("a", D(500), "stock", "USD"), cash("USD", D(-100))]
    for d in Dimension:
        a = allocate(parts, d)
        assert a.total == D(400)
        assert all(s.weight_percent is None for s in a.slices) and a.hhi is None
    c = concentration(parts)
    assert (c.hhi, c.effective_positions, c.largest) == (None, None, None)
    assert c.top == dict.fromkeys(TOP) and c.positions == 2


def test_nothing_to_allocate() -> None:
    for parts in ([], [Part("a", D(0), "stock", "USD")]):
        a = allocate(parts, Dimension.ASSET_CLASS)
        assert a.hhi is None
        assert all(s.weight_percent is None for s in a.slices)
        assert concentration(parts).hhi is None
    assert (
        herfindahl([]) is None and herfindahl([D(0)]) is None and herfindahl([D(-1), D(2)]) is None
    )


def test_a_zero_valued_position_gets_zero_weight() -> None:
    parts = [Part("a", D(100), "stock", "USD"), Part("b", D(0), "etf", "USD")]
    a = allocate(parts, Dimension.ASSET_CLASS)
    assert [(s.key, s.weight_percent) for s in a.slices] == [
        ("stock", D("100.00")),
        ("etf", D("0.00")),
    ]
    assert concentration(parts).hhi == 1


def test_fewer_positions_than_the_top_n() -> None:
    c = concentration([Part("a", D(3), "stock", "USD"), Part("b", D(1), "etf", "USD")])
    assert c.top == {1: D("0.75"), 3: D(1), 5: D(1)}


def test_measure_reads_the_summary() -> None:
    a1, a2 = uuid.uuid4(), uuid.uuid4()
    s = Summary("USD", holdings_value=D(900), cash=D(100))
    s.positions = {a1: D(600), a2: D(300)}
    s.position_currencies = {a1: "EUR", a2: "USD"}
    s.cash_balances = {"USD": D(100)}
    s.unpriced_assets = [uuid.uuid4()]
    s.inputs_as_of = [datetime.now(UTC)]
    classes = {
        a1: Classification("stock", "DE", "Industrials", "USD"),  # valued in EUR
        a2: Classification("reit", "US", None, "USD"),
    }
    result = measure(s, classes)
    assert result.total == D(1000) and result.currency == "USD"
    assert not result.complete and result.unpriced_assets == tuple(s.unpriced_assets)
    assert [(x.key, x.value) for x in result.by[Dimension.CURRENCY].slices] == [
        ("EUR", D(600)),
        ("USD", D(400)),
    ]
    assert [x.key for x in result.by[Dimension.SECTOR].slices] == ["Industrials", None]
    assert result.concentration.largest == str(a1)
    assert set(result.by) == set(Dimension)


# ----------------------------------------------------------------------------------- properties

VALUE = st.decimals(min_value=0, max_value=10_000_000, places=2)
KEY = st.sampled_from(["A", "B", "C", None])


@st.composite
def portfolios(draw: st.DrawFn) -> list[Part]:
    n = draw(st.integers(1, 15))
    parts = [
        Part(f"p{i}", draw(VALUE), draw(st.sampled_from(["stock", "etf", "bond"])),
             draw(st.sampled_from(["USD", "EUR"])), draw(KEY), draw(KEY))
        for i in range(n)
    ]  # fmt: skip
    if sum(p.value for p in parts) == 0:
        parts.append(Part("pos", D("0.01"), "stock", "USD"))
    return parts


@settings(max_examples=150, deadline=None)
@given(portfolios())
def test_weights_always_add_up_to_exactly_100(parts: list[Part]) -> None:
    total = sum(p.value for p in parts)
    for d in Dimension:
        a = allocate(parts, d)
        weights = [s.weight_percent for s in a.slices]
        assert all(w is not None for w in weights)
        assert sum(w for w in weights if w is not None) == D("100.00")
        for s in a.slices:
            assert s.weight_percent is not None
            assert abs(s.weight_percent - s.value * 100 / total) < D("0.01")  # within one unit
        values = [s.value for s in a.slices]
        assert values == sorted(values, reverse=True)


@settings(max_examples=150, deadline=None)
@given(portfolios())
def test_concentration_bounds(parts: list[Part]) -> None:
    c = concentration(parts)
    n = len(parts)
    assert c.hhi is not None and c.effective_positions is not None
    assert D(1) / n - D("1e-25") <= c.hhi <= 1
    assert 1 - D("1e-25") <= c.effective_positions <= n + D("1e-25")
    shares = [c.top[k] for k in TOP]
    assert all(x is not None for x in shares)
    top1, top3, top5 = (x for x in shares if x is not None)
    assert top1 <= top3 <= top5 <= 1
    assert top1 >= D(1) / n - D("1e-25")  # the largest is at least the average
    largest = max(parts, key=lambda p: (p.value, [-ord(ch) for ch in p.key]))
    assert c.largest is not None
    assert next(p for p in parts if p.key == c.largest).value == largest.value


@settings(max_examples=80, deadline=None)
@given(portfolios(), st.permutations(range(15)))
def test_the_order_of_the_parts_does_not_matter(parts: list[Part], order: list[int]) -> None:
    shuffled = [parts[i] for i in order if i < len(parts)] + parts[15:]
    for d in Dimension:
        assert allocate(shuffled, d) == allocate(parts, d)
    assert concentration(shuffled) == concentration(parts)


def test_no_float_or_io_in_the_maths() -> None:
    tree = ast.parse(
        (Path(__file__).parents[1] / "app/modules/analytics/allocation.py").read_text("utf-8")
    )
    assert "float" not in {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not [
        n for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, float)
    ]


def test_the_consolidated_summary_keeps_positions_and_cash() -> None:
    """Each portfolio's positions and cash are converted from its base currency and added."""
    from app.modules.portfolio.summary import Rate, consolidate

    shared, own = uuid.uuid4(), uuid.uuid4()
    usd = Summary("USD", holdings_value=D(100), cash=D(10))
    usd.positions, usd.position_currencies = {shared: D(100)}, {shared: "USD"}
    usd.cash_balances = {"USD": D(10)}
    eur = Summary("EUR", holdings_value=D(300), cash=D(20))
    eur.positions = {shared: D(200), own: D(100)}
    eur.position_currencies = {shared: "EUR", own: "GBP"}
    eur.cash_balances = {"EUR": D(20)}
    rate = Rate("EUR", D("1.5"), datetime.now(UTC), stale=False)
    total = consolidate("USD", [usd, eur], {"EUR": rate})
    assert total.positions == {shared: D(400), own: D(150)}  # 100 + 200 x 1.5; 100 x 1.5
    assert total.position_currencies == {shared: "USD", own: "GBP"}  # the first seen
    assert total.cash_balances == {"USD": D(10), "EUR": D(30)}
    assert sum(total.positions.values()) + sum(total.cash_balances.values()) == total.total_value


def test_sectors_are_trimmed_text() -> None:
    from app.modules.assets.service import _sector

    assert _sector("  Health care ") == "Health care"
    assert _sector("   ") is None
    assert _sector("") is None
    assert _sector(None) is None
    assert _sector(5) is None
