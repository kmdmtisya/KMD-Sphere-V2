"""Holdings calculation (P05-T05, ADR-0012): golden vectors and properties."""

import json
import random
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.money import round_half_up
from app.modules.transactions.holdings import (
    Entry,
    InconsistentLedger,
    compute,
    effective,
    never_negative,
)

VECTORS = json.loads((Path(__file__).parent / "golden" / "holdings_vectors.json").read_text())
ASSET = uuid.UUID("00000000-0000-4000-8000-0000000000aa")
DAY0 = date(2026, 1, 1)
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def entries_from(spec: list[dict[str, Any]]) -> list[Entry]:
    ids = {e["label"]: uuid.uuid5(uuid.NAMESPACE_URL, e["label"]) for e in spec}
    return [
        Entry(
            id=ids[e["label"]],
            transaction_type=e["type"],
            trade_date=DAY0 + timedelta(days=e["day"]),
            created_at=T0 + timedelta(seconds=i),
            asset_id=ASSET,
            quantity=Decimal(e["qty"]) if "qty" in e else None,
            gross_amount=Decimal(e["gross"]),
            fees=Decimal(e.get("fees", "0")),
            taxes=Decimal(e.get("taxes", "0")),
            fx=Decimal(e.get("fx", "1")),
            reverses=ids[e["reverses"]] if "reverses" in e else None,
        )
        for i, e in enumerate(spec)
    ]


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=lambda v: v["name"])
def test_golden_vectors(vector: dict[str, Any]) -> None:
    position = compute(entries_from(vector["entries"]))[ASSET]
    expected = vector["expected"]
    for field in ("quantity", "cost_basis", "realized_pl", "income", "expenses"):
        got = round_half_up(getattr(position, field), 8)
        assert got == Decimal(expected[field]), f"{field}: {got} != {expected[field]}"


def test_average_cost() -> None:
    first = VECTORS["vectors"][0]
    position = compute(entries_from(first["entries"]))[ASSET]
    assert round_half_up(position.average_cost or Decimal(0), 8) == Decimal("107.66666667")
    emptied = compute(entries_from(VECTORS["vectors"][1]["entries"]))[ASSET]
    assert emptied.average_cost is None


def test_selling_more_than_held_on_the_date_is_inconsistent() -> None:
    spec = [
        {"label": "s1", "type": "SELL", "day": 1, "qty": "1", "gross": "10"},
        {"label": "b1", "type": "BUY", "day": 2, "qty": "5", "gross": "50"},
    ]
    with pytest.raises(InconsistentLedger):
        compute(entries_from(spec))
    assert not never_negative(entries_from(spec))


def test_same_day_entries_apply_in_entry_order() -> None:
    spec = [
        {"label": "b1", "type": "BUY", "day": 1, "qty": "5", "gross": "50"},
        {"label": "s1", "type": "SELL", "day": 1, "qty": "5", "gross": "60"},
    ]
    assert compute(entries_from(spec))[ASSET].realized_pl == 10
    reordered = list(reversed(entries_from(spec)))  # input order does not matter
    assert compute(reordered)[ASSET].realized_pl == 10


def test_entries_without_an_asset_are_ignored() -> None:
    cash = Entry(
        id=uuid.uuid4(),
        transaction_type="DEPOSIT",
        trade_date=DAY0,
        created_at=T0,
        asset_id=None,
        quantity=None,
        gross_amount=Decimal("100"),
        fees=Decimal(0),
        taxes=Decimal(0),
        fx=Decimal(1),
    )
    assert compute([cash]) == {}


# ---------------------------------------------------------------------------- properties

amounts = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"), places=2)
quantities = st.decimals(min_value=Decimal("0.001"), max_value=Decimal("1000"), places=3)
rates = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("200"), places=6)


@st.composite
def histories(draw: st.DrawFn) -> list[Entry]:
    """A valid buy/sell history for one asset (sales never exceed the units held)."""
    held = Decimal(0)
    out: list[Entry] = []
    for i in range(draw(st.integers(min_value=1, max_value=25))):
        sell = held > 0 and draw(st.booleans())
        qty = draw(quantities)
        if sell:
            qty = min(qty, held) if draw(st.booleans()) else held
        out.append(
            Entry(
                id=uuid.UUID(int=i + 1),
                transaction_type="SELL" if sell else "BUY",
                trade_date=DAY0 + timedelta(days=i),
                created_at=T0 + timedelta(seconds=i),
                asset_id=ASSET,
                quantity=qty,
                gross_amount=draw(amounts),
                fees=draw(st.decimals(min_value=0, max_value=50, places=2)),
                taxes=draw(st.decimals(min_value=0, max_value=50, places=2)),
                fx=draw(rates),
            )
        )
        held += -qty if sell else qty
    return out


def _cost(e: Entry) -> Decimal:
    return (e.gross_amount + e.fees + e.taxes) * e.fx


def _proceeds(e: Entry) -> Decimal:
    return (e.gross_amount - e.fees - e.taxes) * e.fx


# Divisions inside the calculation carry 50 significant digits.
TOLERANCE = Decimal("1e-40")


@settings(max_examples=300, deadline=None)
@given(histories())
def test_quantity_is_units_bought_minus_units_sold(history: list[Entry]) -> None:
    position = compute(history)[ASSET]
    bought = sum((e.quantity or 0 for e in history if e.transaction_type == "BUY"), Decimal(0))
    sold = sum((e.quantity or 0 for e in history if e.transaction_type == "SELL"), Decimal(0))
    assert position.quantity == bought - sold


@settings(max_examples=300, deadline=None)
@given(histories())
def test_cost_is_conserved(history: list[Entry]) -> None:
    """Every unit of cost either remains in the cost basis or has left through a sale:
    cost_basis + (proceeds - realised) == total cost of purchases."""
    position = compute(history)[ASSET]
    with localcontext() as ctx:
        ctx.prec = 80  # the check itself must not round
        bought = sum((_cost(e) for e in history if e.transaction_type == "BUY"), Decimal(0))
        sold = sum((_proceeds(e) for e in history if e.transaction_type == "SELL"), Decimal(0))
        drift = abs(position.cost_basis + sold - position.realized_pl - bought)
    assert drift < TOLERANCE


@settings(max_examples=300, deadline=None)
@given(histories())
def test_no_units_means_no_cost(history: list[Entry]) -> None:
    position = compute(history)[ASSET]
    assert position.quantity >= 0
    if position.quantity == 0:
        assert position.cost_basis == 0


@settings(max_examples=200, deadline=None)
@given(histories(), st.integers(min_value=0, max_value=10_000))
def test_reversing_a_buy_equals_never_posting_it(history: list[Entry], pick: int) -> None:
    buys = [e for e in history if e.transaction_type == "BUY"]
    target = buys[pick % len(buys)]
    without = [e for e in history if e.id != target.id]
    if not never_negative(without):
        return  # later sales relied on it: the ledger would refuse this reversal
    reversal = Entry(
        id=uuid.uuid4(),
        transaction_type=target.transaction_type,
        trade_date=target.trade_date + timedelta(days=400),  # posted much later
        created_at=T0 + timedelta(days=400),
        asset_id=ASSET,
        quantity=target.quantity,
        gross_amount=target.gross_amount,
        fees=target.fees,
        taxes=target.taxes,
        fx=target.fx,
        reverses=target.id,
    )
    assert compute([*history, reversal]) == compute(without)
    assert target not in effective([*history, reversal])


@settings(max_examples=200, deadline=None)
@given(histories(), st.randoms(use_true_random=False))
def test_input_order_does_not_matter(history: list[Entry], rnd: random.Random) -> None:
    shuffled = list(history)
    rnd.shuffle(shuffled)
    assert compute(shuffled) == compute(history)
