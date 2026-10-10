"""Portfolio summary (pure; P05-T08): totals reconcile with hand-computed fixtures.

Scenario (USD portfolio). The working for every expected figure is written next to it.
  e1  DEPOSIT 10000 USD
  e2  BUY A 10 for 1000 + 10 fees USD                 cash USD -1010
  e3  DEPOSIT 1000 EUR at 1.10                        cash EUR +1000, contribution 1100
  e4  BUY B (EUR) 5 for 500 + 5 fees EUR at 1.10      cash EUR -505, cost 555.5
  e5  DIVIDEND A 20, withholding 3 USD                cash +17, income 20, expenses 3
  e6  FEE (no asset) 2 USD                            cash -2, expenses 2
  e7  INTEREST (no asset) 4 EUR at 1.12               cash EUR +4, income 4.48
  e8  WITHDRAWAL 100 USD                              cash -100, contribution -100
  e9  SELL A 4 for 480 - 2 fees USD                   cash +478; A cost 606, realised 74
  e10 BUY D 2 for 50 USD                              cash -50 (D has no valuation)
Valuations: A 900 USD; B 600 EUR; C (a house, no ledger) 250000 KES.
Latest FX to USD: EUR 1.08; KES 0.0077 (stale).
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.money import percentages, round_half_up
from app.modules.portfolio.summary import (
    HoldingInput,
    Rate,
    Summary,
    ValuationInput,
    compute_summary,
    consolidate,
)
from app.modules.transactions.holdings import Entry

A, B, C, D = (uuid.UUID(int=i) for i in (1, 2, 3, 4))
T0 = datetime(2026, 10, 1, tzinfo=UTC)


def at(hours: int) -> datetime:
    return T0 + timedelta(hours=hours)


def entry(
    n: int,
    kind: str,
    gross: str,
    currency: str = "USD",
    *,
    asset: uuid.UUID | None = None,
    qty: str | None = None,
    fees: str = "0",
    taxes: str = "0",
    fx: str = "1",
    reverses: uuid.UUID | None = None,
) -> Entry:
    return Entry(
        id=uuid.UUID(int=1000 + n),
        transaction_type=kind,
        trade_date=date(2026, 9, n if n <= 28 else 28),
        created_at=at(n),
        asset_id=asset,
        quantity=Decimal(qty) if qty else None,
        gross_amount=Decimal(gross),
        fees=Decimal(fees),
        taxes=Decimal(taxes),
        fx=Decimal(fx),
        reverses=reverses,
        currency=currency,
    )


ENTRIES = [
    entry(1, "DEPOSIT", "10000"),
    entry(2, "BUY", "1000", asset=A, qty="10", fees="10"),
    entry(3, "DEPOSIT", "1000", "EUR", fx="1.10"),
    entry(4, "BUY", "500", "EUR", asset=B, qty="5", fees="5", fx="1.10"),
    entry(5, "DIVIDEND", "20", asset=A, taxes="3"),
    entry(6, "FEE", "2"),
    entry(7, "INTEREST", "4", "EUR", fx="1.12"),
    entry(8, "WITHDRAWAL", "100"),
    entry(9, "SELL", "480", asset=A, qty="4", fees="2"),
    entry(10, "BUY", "50", asset=D, qty="2"),
]
HOLDINGS = [
    # A: 1010 for 10; sell 4 removes 404; proceeds 478 -> realised 74; 606 for 6.
    HoldingInput(A, Decimal(6), Decimal(606), Decimal(74), Decimal(20), Decimal(3)),
    # B: (500 + 5) x 1.10 = 555.5 for 5.
    HoldingInput(B, Decimal(5), Decimal("555.5"), Decimal(0), Decimal(0), Decimal(0)),
    HoldingInput(D, Decimal(2), Decimal(50), Decimal(0), Decimal(0), Decimal(0)),
]
VALUATIONS = [
    ValuationInput(A, Decimal(900), "USD", at(100)),
    ValuationInput(B, Decimal(600), "EUR", at(101)),
    ValuationInput(C, Decimal(250000), "KES", at(50)),
]
RATES = {
    "EUR": Rate("EUR", Decimal("1.08"), at(200), stale=False),
    "KES": Rate("KES", Decimal("0.0077"), at(20), stale=True),
}


def scenario() -> Summary:
    return compute_summary("USD", HOLDINGS, VALUATIONS, ENTRIES, RATES)


def test_totals_reconcile_with_the_hand_computed_figures() -> None:
    s = scenario()
    # 900 + 600 x 1.08 + 250000 x 0.0077 = 900 + 648 + 1925
    assert s.holdings_value == Decimal("3473")
    # USD 10000 - 1010 + 17 - 2 - 100 + 478 - 50 = 9333; EUR 1000 - 505 + 4 = 499 -> 538.92
    assert s.native == {"USD": Decimal("10233"), "EUR": Decimal("1099"), "KES": Decimal("250000")}
    assert s.cash == Decimal("9871.92")
    assert s.total_value == Decimal("13344.92")
    # Valued positions with a ledger cost: A 606 + B 555.5 (C has no ledger; D is unpriced).
    assert s.cost_basis == Decimal("1161.5")
    # (900 - 606) + (648 - 555.5)
    assert s.unrealized_pl == Decimal("386.5")
    assert s.realized_pl == Decimal("74")
    # A's dividend 20 + interest 4 x 1.12
    assert s.income == Decimal("24.48")
    # withholding 3 + fee 2
    assert s.expenses == Decimal("5")
    # 10000 + 1000 x 1.10 - 100
    assert s.net_contributions == Decimal("11000")
    assert s.valued_positions == 3


def test_the_breakdown_adds_up_to_the_total() -> None:
    s = scenario()
    # USD 900 + 9333; EUR (600 + 499) x 1.08; KES 1925
    assert s.converted == {
        "USD": Decimal("10233"),
        "EUR": Decimal("1186.92"),
        "KES": Decimal("1925"),
    }
    assert sum(s.converted.values()) == s.total_value
    shares = percentages([s.converted[c] for c in ("EUR", "KES", "USD")])
    # 8.894..., 14.424..., 76.680... -> floors 8.89 + 14.42 + 76.68 = 99.99; the largest
    # remainder (KES, 0.0049...) gets the last hundredth.
    assert shares == [Decimal("8.89"), Decimal("14.43"), Decimal("76.68")]


def test_freshness_and_completeness() -> None:
    s = scenario()
    assert s.data_as_of(datetime.now(UTC)) == at(20)  # the oldest input: the KES rate
    assert s.stale_fx == {"KES"}
    assert s.unpriced_assets == [D]
    assert s.unconverted_currencies == set()
    assert s.complete is False


def test_amounts_without_a_rate_are_left_out_and_reported() -> None:
    jpy = ValuationInput(C, Decimal(1_000_000), "JPY", at(5))
    s = compute_summary("USD", [], [jpy], [entry(1, "DEPOSIT", "100")], {})
    assert s.holdings_value == 0
    assert s.cash == Decimal(100)
    assert s.unconverted_currencies == {"JPY"}
    assert s.complete is False


def test_a_closed_position_is_not_valued_even_with_a_valuation() -> None:
    closed = HoldingInput(A, Decimal(0), Decimal(0), Decimal(10), Decimal(0), Decimal(0))
    s = compute_summary("USD", [closed], [VALUATIONS[0]], [], {})
    assert (s.holdings_value, s.valued_positions, s.realized_pl) == (Decimal(0), 0, Decimal(10))
    assert s.complete is True


def test_reversed_entries_do_not_count() -> None:
    deposit = entry(1, "DEPOSIT", "500")
    reversal = entry(2, "DEPOSIT", "500", reverses=deposit.id)
    s = compute_summary("USD", [], [], [deposit, reversal, entry(3, "DEPOSIT", "70")], {})
    assert (s.cash, s.net_contributions) == (Decimal(70), Decimal(70))


def test_negative_cash_is_shown_as_it_is() -> None:
    s = compute_summary("USD", [], [], [entry(1, "BUY", "100", asset=A, qty="1")], {})
    assert s.cash == Decimal(-100)
    assert percentages([s.converted["USD"]]) is None


# --------------------------------------------------------------------------- consolidation


def test_consolidation_converts_each_portfolio_and_reconciles() -> None:
    usd = scenario()
    kes = compute_summary(
        "KES",
        [],
        [ValuationInput(C, Decimal(100000), "KES", at(60))],
        [entry(1, "DEPOSIT", "5000", "KES")],
        {},
    )
    rates = {
        "USD": Rate("USD", Decimal("0.92"), at(300), stale=False),
        "KES": Rate("KES", Decimal("0.0071"), at(10), stale=False),
    }
    s = consolidate("EUR", [usd, kes], rates)
    # USD figures x 0.92 plus KES figures x 0.0071
    assert s.total_value == usd.total_value * Decimal("0.92") + Decimal(105000) * Decimal("0.0071")
    assert s.unrealized_pl == Decimal("386.5") * Decimal("0.92")
    assert s.net_contributions == Decimal(11000) * Decimal("0.92") + Decimal(5000) * Decimal(
        "0.0071"
    )
    assert sum(s.converted.values()) == s.total_value
    assert s.native["KES"] == Decimal(250000 + 105000)
    assert s.data_as_of(datetime.now(UTC)) == at(10)
    assert s.unpriced_assets == [D]


def test_a_portfolio_whose_currency_cannot_be_converted_is_reported() -> None:
    s = consolidate("EUR", [scenario()], {})
    assert s.total_value == 0
    assert s.unconverted_currencies == {"USD"}
    assert s.complete is False


# ------------------------------------------------------------------------- percentages


@pytest.mark.parametrize(
    ("parts", "expected"),
    [
        (["1", "1", "1"], ["33.34", "33.33", "33.33"]),  # ties: the first part gets the extra
        (["2", "1"], ["66.67", "33.33"]),
        (["50", "50"], ["50.00", "50.00"]),
        (["1"], ["100.00"]),
    ],
)
def test_percentages_add_up_to_exactly_100(parts: list[str], expected: list[str]) -> None:
    got = percentages([Decimal(p) for p in parts])
    assert got == [Decimal(e) for e in expected]
    assert got is not None and sum(got) == Decimal("100.00")


@pytest.mark.parametrize("parts", [[], ["0"], ["-1", "2"], ["0", "0"]])
def test_percentages_are_none_when_meaningless(parts: list[str]) -> None:
    assert percentages([Decimal(p) for p in parts]) is None


def test_published_figures_round_half_up() -> None:
    assert round_half_up(Decimal("13344.925"), 2) == Decimal("13344.93")


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        # gross 100, fees 3, taxes 2 (docs/design/portfolio-summary.md, section 3)
        ("DEPOSIT", "95"),
        ("WITHDRAWAL", "-105"),
        ("BUY", "-105"),
        ("SELL", "95"),
        ("DIVIDEND", "95"),
        ("INTEREST", "95"),
        ("COUPON", "95"),
        ("RENT", "95"),
        ("DISTRIBUTION", "95"),
        ("FEE", "-105"),
        ("TAX", "-105"),
        ("TRANSFER_IN", "-5"),
        ("TRANSFER_OUT", "-5"),
        ("VALUATION_ADJUSTMENT", "0"),
    ],
)
def test_cash_effect_of_every_type(kind: str, expected: str) -> None:
    from app.modules.portfolio.summary import cash_effect

    e = entry(1, kind, "100", fees="3", taxes="2")
    assert cash_effect(e) == Decimal(expected)
