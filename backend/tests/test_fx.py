"""FX conversion rounding and rate-selection rules (pure; P05-T06)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.market_data.fx import (
    HISTORICAL_MAX_AGE,
    FxRateUnavailable,
    StoredRate,
    convert,
    convert_exact,
    end_of_day,
    select,
)

NOW = datetime(2026, 10, 10, 12, tzinfo=UTC)


def rate(
    base: str,
    quote: str,
    value: str,
    hours_ago: float,
    provider: str = "p1",
    retrieved_hours_ago: float | None = None,
) -> StoredRate:
    ts = NOW - timedelta(hours=hours_ago)
    retrieved = NOW - timedelta(
        hours=retrieved_hours_ago if retrieved_hours_ago is not None else hours_ago
    )
    return StoredRate(base, quote, Decimal(value), provider, ts, retrieved)


# ---------------------------------------------------------------------------- conversion


@pytest.mark.parametrize(
    ("amount", "fx", "to", "expected"),
    [
        ("10.01", "129.995", "KES", "1301.25"),  # 1301.24995 -> half up
        ("1.00", "0.005", "USD", "0.01"),  # 0.005 tie -> up
        ("1.00", "0.0049999", "USD", "0.00"),
        ("10.50", "151.237", "JPY", "1588"),  # 1587.9885 -> 0 decimals
        ("2.00", "151.25", "JPY", "303"),  # 302.5 tie -> up
        ("100.00", "0.30705", "KWD", "30.705"),  # 3 decimals
        ("-10.01", "129.995", "KES", "-1301.25"),  # ties away from zero for losses too
    ],
)
def test_conversion_rounds_half_up_to_the_target_minor_units(
    amount: str, fx: str, to: str, expected: str
) -> None:
    assert convert(Decimal(amount), Decimal(fx), to) == Decimal(expected)


def test_exact_conversion_keeps_every_digit() -> None:
    assert convert_exact(Decimal("10.01"), Decimal("129.995")) == Decimal("1301.24995")
    third = convert_exact(Decimal("1"), Decimal(1) / Decimal(3))
    assert third == Decimal(1) / Decimal(3)


# ------------------------------------------------------------------------------ selection


def test_same_currency_is_one() -> None:
    q = select("USD", "USD", [], NOW, now=NOW)
    assert (q.rate, q.inverted, q.stale) == (Decimal(1), False, False)


def test_the_newest_rate_at_or_before_the_moment_wins() -> None:
    rates = [
        rate("USD", "KES", "129.10", 30),
        rate("USD", "KES", "129.50", 2),
        rate("USD", "KES", "130.00", -1),  # in the future: never used
    ]
    q = select("USD", "KES", rates, NOW, now=NOW)
    assert q.rate == Decimal("129.50")
    assert q.as_of == NOW - timedelta(hours=2)
    assert not q.stale and not q.inverted


def test_a_historical_date_uses_that_days_rate() -> None:
    rates = [rate("USD", "KES", "129.10", 30), rate("USD", "KES", "129.50", 2)]
    yesterday = end_of_day(date(2026, 10, 9))
    q = select("USD", "KES", rates, yesterday, now=NOW)
    assert q.rate == Decimal("129.10")


def test_rates_older_than_the_window_are_not_used() -> None:
    old = rate("USD", "KES", "120", HISTORICAL_MAX_AGE.total_seconds() / 3600 + 1)
    with pytest.raises(FxRateUnavailable):
        select("USD", "KES", [old], NOW, now=NOW)
    weekend = rate("USD", "KES", "129", 72)  # three days old: still within the window
    assert select("USD", "KES", [weekend], NOW, now=NOW).stale


def test_the_opposite_pair_is_inverted_only_when_needed() -> None:
    inverse_only = [rate("KES", "USD", "0.008", 1)]
    q = select("USD", "KES", inverse_only, NOW, now=NOW)
    assert q.inverted and q.rate == Decimal(125)
    both = [rate("KES", "USD", "0.008", 1), rate("USD", "KES", "129", 5)]
    q = select("USD", "KES", both, NOW, now=NOW)
    assert not q.inverted and q.rate == Decimal(129)  # a direct rate is preferred


def test_ties_are_broken_by_retrieval_then_provider() -> None:
    rates = [
        rate("USD", "KES", "129.1", 1, "zeta", retrieved_hours_ago=0.5),
        rate("USD", "KES", "129.2", 1, "aa", retrieved_hours_ago=0.9),  # earlier retrieval loses
        rate("USD", "KES", "129.3", 1, "beta", retrieved_hours_ago=0.5),
        rate("USD", "KES", "129.4", 1, "ab", retrieved_hours_ago=0.5),
    ]
    q = select("USD", "KES", rates, NOW, now=NOW)
    assert (q.rate, q.provider) == (Decimal("129.4"), "ab")
    assert select("USD", "KES", list(reversed(rates)), NOW, now=NOW).provider == "ab"


def test_non_positive_rates_are_ignored() -> None:
    with pytest.raises(FxRateUnavailable):
        select("USD", "KES", [rate("USD", "KES", "0", 1)], NOW, now=NOW)


def test_end_of_day_is_the_last_instant_in_utc() -> None:
    eod = end_of_day(date(2026, 10, 9))
    assert eod.tzinfo == UTC
    assert eod + timedelta(microseconds=1) == datetime(2026, 10, 10, tzinfo=UTC)
