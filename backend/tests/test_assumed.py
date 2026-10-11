"""Assumed deposits (P06-T10 review, decision 1): where a posting overdraws a currency, the
shortfall is treated as a deposit on that date at that posting's rate."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.analytics.performance import external_flows
from app.modules.portfolio.assumed import with_assumed_deposits
from app.modules.portfolio.summary import cash_effect
from app.modules.transactions.holdings import Entry, effective

D = Decimal
DAY0 = date(2025, 1, 1)
T0 = datetime(2025, 1, 1, tzinfo=UTC)
ASSET = uuid.UUID(int=9)


def entry(
    kind: str,
    day: int,
    gross: str,
    *,
    fees: str = "0",
    currency: str = "USD",
    fx: str = "1",
    reverses: uuid.UUID | None = None,
    eid: uuid.UUID | None = None,
) -> Entry:
    qty = D(1) if kind in ("BUY", "SELL") else None
    on, at = DAY0 + timedelta(days=day), T0 + timedelta(seconds=day)
    asset = ASSET if qty else None
    return Entry(
        eid or uuid.uuid4(),
        kind,
        on,
        at,
        asset,
        qty,
        D(gross),
        D(fees),
        D(0),
        D(fx),
        reverses,
        currency,
    )


def test_a_purchase_without_a_deposit_is_covered() -> None:
    buy = entry("BUY", 3, "100", fees="2")
    entries, made = with_assumed_deposits([buy])
    [a] = made
    assert (a.on_entry, a.currency, a.amount, a.fx, a.base_amount) == (
        buy.id,
        "USD",
        D(102),
        D(1),
        D(102),
    )
    [deposit] = [e for e in entries if e.transaction_type == "DEPOSIT"]
    assert (deposit.gross_amount, deposit.trade_date, deposit.currency) == (
        D(102),
        buy.trade_date,
        "USD",
    )
    assert deposit.created_at < buy.created_at  # applied just before the purchase
    assert deposit.id != buy.id and deposit.reverses is None
    # With the assumption the purchase leaves exactly nothing in cash.
    assert sum((cash_effect(e) for e in effective(entries)), D(0)) == 0


def test_only_the_shortfall_is_assumed() -> None:
    ledger = [entry("DEPOSIT", 0, "120"), entry("BUY", 1, "100"), entry("BUY", 2, "100")]
    entries, made = with_assumed_deposits(ledger)
    assert [(a.amount, a.on_entry) for a in made] == [(D(80), ledger[2].id)]
    assert len(entries) == 4


def test_nothing_is_assumed_when_cash_suffices() -> None:
    ledger = [entry("DEPOSIT", 0, "500"), entry("BUY", 1, "100"), entry("SELL", 2, "120"),
              entry("WITHDRAWAL", 3, "300")]  # fmt: skip
    entries, made = with_assumed_deposits(ledger)
    assert made == [] and entries == ledger


def test_each_currency_has_its_own_cash_and_the_postings_rate() -> None:
    ledger = [entry("DEPOSIT", 0, "1000"), entry("BUY", 1, "100", currency="EUR", fx="1.1")]
    _, made = with_assumed_deposits(ledger)
    [a] = made
    assert (a.currency, a.amount, a.fx, a.base_amount) == ("EUR", D(100), D("1.1"), D("110.0"))


def test_income_and_sales_add_cash_before_a_later_purchase() -> None:
    ledger = [entry("BUY", 0, "100"), entry("SELL", 5, "60"), entry("BUY", 6, "100")]
    _, made = with_assumed_deposits(ledger)
    assert [a.amount for a in made] == [D(100), D(40)]  # the sale's 60 covers part of the 100
    covered = [entry("BUY", 0, "100"), entry("SELL", 5, "130"), entry("BUY", 6, "100")]
    assert [a.amount for a in with_assumed_deposits(covered)[1]] == [D(100)]  # 130 covers it


def test_reversed_entries_are_ignored() -> None:
    bad = uuid.uuid4()
    ledger = [entry("BUY", 1, "900", eid=bad), entry("BUY", 2, "900", reverses=bad),
              entry("DEPOSIT", 3, "50"), entry("BUY", 4, "20")]  # fmt: skip
    _, made = with_assumed_deposits(ledger)
    assert made == []  # the reversed purchase and its reversal never happened


def test_a_withdrawal_beyond_the_balance_is_covered_too() -> None:
    _, made = with_assumed_deposits([entry("DEPOSIT", 0, "100"), entry("WITHDRAWAL", 1, "150")])
    assert [a.amount for a in made] == [D(50)]


def test_the_ids_are_stable() -> None:
    ledger = [entry("BUY", 1, "10")]
    first = with_assumed_deposits(ledger)[0][-1].id
    assert with_assumed_deposits(ledger)[0][-1].id == first


@settings(max_examples=150, deadline=None)
@given(
    st.lists(
        st.tuples(st.sampled_from(["DEPOSIT", "BUY", "SELL", "WITHDRAWAL", "DIVIDEND"]),
                  st.decimals(min_value="0.01", max_value=1000, places=2),
                  st.sampled_from(["USD", "EUR"])),
        min_size=1, max_size=20),
)  # fmt: skip
def test_cash_never_goes_negative_and_deposits_are_the_total_shortfall(
    rows: list[tuple[str, Decimal, str]],
) -> None:
    ledger = [entry(k, i, str(g), currency=c, fx="1.25" if c == "EUR" else "1")
              for i, (k, g, c) in enumerate(rows)]  # fmt: skip
    entries, made = with_assumed_deposits(ledger)
    balance: dict[str, Decimal] = {}
    for e in effective(entries):
        balance[e.currency] = balance.get(e.currency, D(0)) + cash_effect(e)
        assert balance[e.currency] >= 0
    final = {c: D(0) for c in ("USD", "EUR")}
    for e in effective(ledger):
        final[e.currency] += cash_effect(e)
    for currency in ("USD", "EUR"):
        assumed = sum((a.amount for a in made if a.currency == currency), D(0))
        # Real cash plus assumed deposits equals the covered balance.
        assert balance.get(currency, D(0)) == final[currency] + assumed
    assert all(a.base_amount > 0 for a in made) and len(made) <= len(ledger)
    # The assumed deposits are external flows (in the base currency, at the posting's rate).
    inflow = sum((f.amount for f in external_flows(entries) if f.amount > 0), D(0))
    recorded = sum((f.amount for f in external_flows(ledger) if f.amount > 0), D(0))
    assert inflow == recorded + sum((a.base_amount for a in made), D(0))
