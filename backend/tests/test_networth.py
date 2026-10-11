"""Net worth (P06-T07): conversion, reconciliation and gaps. Methods: docs/design/net-worth.md."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.modules.networth.networth import Debt, compute
from app.modules.portfolio.summary import Rate

D = Decimal
NOW = datetime(2026, 10, 11, tzinfo=UTC)
DAY = date(2026, 10, 1)
RATES = {
    "EUR": Rate("EUR", D("1.1"), NOW, stale=False, provider="test"),
    "KES": Rate("KES", D("0.0077"), NOW, stale=True, provider="test"),
}


def debt(kind: str, currency: str, balance: str, name: str = "") -> Debt:
    return Debt(uuid.uuid4(), name or kind, kind, currency, D(balance), DAY)


def test_net_worth_in_one_currency() -> None:
    debts = [
        debt("mortgage", "USD", "150000.00"),
        debt("car_loan", "EUR", "10000.00"),  # 11000.00
        debt("credit_card", "KES", "64935.06"),  # 499.999962 -> 500.00
        debt("personal_loan", "USD", "999.995"),  # stored figures round half-up: 1000.00
    ]
    nw = compute("USD", D("250000.004"), debts, RATES)
    assert nw.assets == D("250000.00")
    assert [c.converted for c in nw.debts] == [D("150000.00"), D("11000.00"), D("500.00"),
                                               D("1000.00")]  # fmt: skip
    assert nw.liabilities == D("162500.00")
    assert nw.net_worth == D("87500.00")
    assert [(t.liability_type, t.value, t.count) for t in nw.by_type] == [
        ("mortgage", D("150000.00"), 1),
        ("car_loan", D("11000.00"), 1),
        ("personal_loan", D("1000.00"), 1),
        ("credit_card", D("500.00"), 1),
    ]
    assert nw.unconverted == frozenset() and nw.currency == "USD"


def test_types_add_up_and_ties_order_by_name() -> None:
    debts = [debt("personal_loan", "USD", "100"), debt("car_loan", "USD", "100"),
             debt("personal_loan", "USD", "50")]  # fmt: skip
    nw = compute("USD", D(0), debts, {})
    assert [(t.liability_type, t.value, t.count) for t in nw.by_type] == [
        ("personal_loan", D("150.00"), 2),
        ("car_loan", D("100.00"), 1),
    ]
    tied = compute(
        "USD", D(0), [debt("personal_loan", "USD", "100"), debt("car_loan", "USD", "100")], {}
    )
    assert [t.liability_type for t in tied.by_type] == ["car_loan", "personal_loan"]
    assert nw.net_worth == D("-250.00")  # owing more than owned is shown as it is


def test_a_currency_without_a_rate_is_left_out_and_reported() -> None:
    nw = compute("USD", D(1000), [debt("mortgage", "GBP", "500"), debt("other", "USD", "1")], RATES)
    assert nw.unconverted == frozenset({"GBP"})
    assert nw.debts[0].converted is None
    assert nw.liabilities == D("1.00") and nw.net_worth == D("999.00")


def test_no_liabilities() -> None:
    nw = compute("JPY", D("1234567.5"), [], {})
    assert (nw.assets, nw.liabilities, nw.net_worth) == (D(1234568), D(0), D(1234568))
    assert nw.by_type == () and nw.debts == ()


@settings(max_examples=100, deadline=None)
@given(
    st.decimals(min_value=-1_000_000, max_value=10_000_000, places=4),
    st.lists(
        st.tuples(
            st.sampled_from(["mortgage", "car_loan", "credit_card"]),
            st.sampled_from(["USD", "EUR", "KES", "GBP"]),
            st.decimals(min_value=0, max_value=1_000_000, places=2),
        ),
        max_size=12,
    ),
)
def test_the_figures_always_reconcile(
    assets: Decimal, rows: list[tuple[str, str, Decimal]]
) -> None:
    nw = compute("USD", assets, [debt(k, c, str(b)) for k, c, b in rows], RATES)
    converted = [c.converted for c in nw.debts if c.converted is not None]
    assert nw.liabilities == sum(converted, D(0))
    assert nw.liabilities == sum((t.value for t in nw.by_type), D(0))
    assert sum(t.count for t in nw.by_type) == len(converted)
    assert nw.net_worth == nw.assets - nw.liabilities
    assert nw.unconverted == ({"GBP"} if any(c == "GBP" for _, c, _ in rows) else set())
    assert all(v.as_tuple().exponent == -2 for v in (nw.assets, nw.liabilities, nw.net_worth))
