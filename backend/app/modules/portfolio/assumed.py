"""Assumed deposits (P06-T10 review, decision 1): pure.

Many people record purchases without the deposits that paid for them. Performance and risk need
to know how much the investor put in, so wherever a posting would take a currency's cash below
zero, the shortfall is treated as a deposit made on that date, in that currency, at that
posting's rate. These deposits are never stored and never shown as transactions; performance and
risk report them separately and say they are assumed. The summary does not assume anything: it
shows negative cash as it is (docs/design/portfolio-summary.md, section 3).
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from app.modules.portfolio.summary import cash_effect
from app.modules.transactions.holdings import Entry, effective

ZERO = Decimal(0)
NAMESPACE = uuid.UUID("5a3e1f0e-6d52-4b8e-9d0b-2f4e1c9a7b11")


@dataclass(frozen=True)
class Assumption:
    """A shortfall covered by an assumed deposit."""

    on_entry: uuid.UUID  # the posting that needed the cash
    currency: str
    amount: Decimal  # in `currency`
    fx: Decimal  # to the portfolio currency (the posting's rate)

    @property
    def base_amount(self) -> Decimal:
        return self.amount * self.fx


def with_assumed_deposits(entries: Iterable[Entry]) -> tuple[list[Entry], list[Assumption]]:
    """The entries plus an assumed DEPOSIT just before every posting that would overdraw its
    currency, and the assumptions made."""
    entries = list(entries)
    cash: dict[str, Decimal] = defaultdict(lambda: ZERO)
    extra: list[Entry] = []
    made: list[Assumption] = []
    for e in effective(entries):
        cash[e.currency] += cash_effect(e)
        if cash[e.currency] < 0:
            shortfall = -cash[e.currency]
            cash[e.currency] = ZERO
            extra.append(
                Entry(
                    id=uuid.uuid5(NAMESPACE, str(e.id)),
                    transaction_type="DEPOSIT",
                    trade_date=e.trade_date,
                    created_at=e.created_at - timedelta(microseconds=1),
                    asset_id=None,
                    quantity=None,
                    gross_amount=shortfall,
                    fees=ZERO,
                    taxes=ZERO,
                    fx=e.fx,
                    currency=e.currency,
                )
            )
            made.append(Assumption(e.id, e.currency, shortfall, e.fx))
    return [*entries, *extra], made
