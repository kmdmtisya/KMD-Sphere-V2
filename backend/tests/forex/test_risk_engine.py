"""The risk calculator without a database (P13-T07, QG-16.1 to 16.5): reference cases worked by
hand (USD, JPY and cross pairs, never a fixed pip value), an independent Fraction oracle,
property tests (the planned loss with costs never exceeds the risk amount, and one more lot step
would), margin, leverage and the warnings, the disclosures, the conversion paths, and the
contract specification file."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from math import floor
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.ai.orchestrator.guards import guarantee_problems
from app.modules.forex.instruments.registry import load_registry
from app.modules.forex.marketdata.repository import StoredQuote
from app.modules.forex.risk import engine as en
from app.modules.forex.risk.conversion import NoConversionRate, Rate, rates_from, resolve
from app.modules.forex.risk.specs import SpecValues, compare_with_provider, load_file

D = Decimal
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
STALE = timedelta(seconds=60)
LIMITS = en.Limits(max_risk_percent=D(2), max_leverage=D(30), max_margin_use_percent=D(50))
# No slippage or commission, so the reference cases can be checked by hand.
PLAIN = SpecValues(D(100000), D("0.01"), D("0.01"), D(100), D("0.0333"), D(0), D(0))
SAME = en.Conversion(D(1), "same currency", None, ())
TRADABLE = ("tradable_quote",)


def trade(**changes: object) -> en.Trade:
    base: dict[str, object] = {
        "instrument": "EUR_USD",
        "direction": "long",
        "entry": D("1.10000"),
        "stop": D("1.09500"),
        "target": D("1.11000"),
        "balance": D(10000),
        "account_currency": "USD",
        "risk_percent": D(1),
        "spread": D(0),
    }
    base.update(changes)
    return en.Trade(**base)  # type: ignore[arg-type]


def calc(
    t: en.Trade,
    spec: SpecValues = PLAIN,
    pip_location: int = -4,
    conversion: en.Conversion = SAME,
    reviewed: bool = True,
    tier: str = "major",
) -> en.Result:
    return en.calculate(t, spec, pip_location, 5, conversion, LIMITS, reviewed, tier)


def rate(mid: str, types: tuple[str, ...] = TRADABLE, per: str = "1") -> en.Conversion:
    return en.Conversion(D(mid), "test", NOW, types, denominator=D(per))


# ------------------------------------------------------------------------- reference cases
def test_eur_usd_in_a_usd_account() -> None:
    r = calc(trade())
    assert r.pip_size == D("0.0001") and r.pip_value_per_lot_quote == D(10)
    assert r.pip_value_per_lot_account == D("10.0000")
    assert r.units == D(20000) and r.lots == D("0.20") and r.status == "sized"
    assert r.stop_pips == D("50.0") and r.target_pips == D("100.0")
    assert r.risk_amount == D("100.00") and r.loss_before_costs == D("100.00")
    assert r.loss_after_costs == D("100.00") and r.profit_before_costs == D("200.00")
    assert r.risk_reward_before_costs == D("2.00") and r.risk_reward_after_costs == D("2.00")
    assert r.notional == D("22000.00") and r.margin == D("732.60")
    assert r.position_leverage == D("2.20") and r.max_leverage == D("30.03")
    assert r.account_impact_percent == D("1.00") and r.margin_use_percent == D("7.33")
    assert r.exposure == {"EUR": D("20000.00000"), "USD": D("-22000.00000")}
    assert r.warnings == []


def test_usd_jpy_in_a_usd_account_converts_the_pip_value() -> None:
    t = trade(instrument="USD_JPY", entry=D("150.000"), stop=D("149.500"), target=D("151.000"))
    r = calc(t, pip_location=-2, conversion=rate("1", per="150"))  # 1 / USD_JPY
    assert r.pip_value_per_lot_quote == D(1000)  # JPY
    assert r.pip_value_per_lot_account == D("6.6667")  # USD at 150: not 10, not a constant
    assert r.units == D(30000) and r.lots == D("0.30")
    assert r.loss_before_costs == D("100.00") and r.stop_pips == D("50.0")
    assert r.exposure["USD"] == D(30000) and r.exposure["JPY"] == D("-4500000.00000")


def test_eur_gbp_in_a_usd_account_converts_through_gbp_usd() -> None:
    t = trade(instrument="EUR_GBP", entry=D("0.85000"), stop=D("0.84500"), target=D("0.86000"))
    r = calc(t, conversion=rate("1.25"))
    assert r.pip_value_per_lot_quote == D(10) and r.pip_value_per_lot_account == D("12.5000")
    assert r.units == D(16000) and r.lots == D("0.16")
    assert r.loss_before_costs == D("100.00")


def test_the_same_trade_in_another_account_currency_differs() -> None:
    usd = calc(trade())
    eur = calc(trade(account_currency="EUR"), conversion=rate("1", per="1.1"))
    assert eur.pip_value_per_lot_account == D("9.0909")
    assert eur.units == D(22000) and eur.units != usd.units


def test_a_short_position_mirrors_a_long_one() -> None:
    long = calc(trade())
    short = calc(trade(direction="short", stop=D("1.10500"), target=D("1.09000")))
    assert short.units == long.units and short.loss_after_costs == long.loss_after_costs
    assert short.exposure == {"EUR": D("-20000.00000"), "USD": D("22000.00000")}


def test_costs_reduce_the_size_and_the_reward() -> None:
    spec = replace(PLAIN, slippage_pips=D("0.5"), commission_per_lot_side=D("3.5"))
    r = calc(trade(spread=D("0.00012")), spec=spec)
    # per unit: 0.005 + 0.00012 spread + 2 x 0.5 pips + 2 x 3.5 / 100000 = 0.00529
    assert r.units == D(18000)
    assert r.costs == {
        "spread": D("2.16"),
        "slippage": D("1.80"),
        "commission": D("1.26"),
        "total": D("5.22"),
    }
    assert r.loss_before_costs == D("90.00") and r.loss_after_costs == D("95.22")
    assert r.profit_before_costs == D("180.00") and r.profit_after_costs == D("174.78")
    assert r.risk_reward_before_costs == D("2.00") and r.risk_reward_after_costs == D("1.84")


def test_without_a_target_there_is_no_profit_or_reward() -> None:
    r = calc(trade(target=None))
    assert r.profit_before_costs is None and r.profit_after_costs is None
    assert r.risk_reward_before_costs is None and r.target_pips is None


# ------------------------------------------------------------------------ the Fraction oracle
def oracle(t: en.Trade, spec: SpecValues, pip_location: int, rate_: Decimal) -> dict[str, Fraction]:
    """Written separately from the engine, with exact fractions."""
    f = Fraction
    pip = f(10) ** pip_location
    cost = f(t.spread or 0) + 2 * f(spec.slippage_pips) * pip
    cost += 2 * f(spec.commission_per_lot_side) / f(spec.contract_size)
    risk = f(t.balance) * f(t.risk_percent) / 100
    step = f(spec.lot_step) * f(spec.contract_size)
    distance = abs(f(t.entry) - f(t.stop))
    units = floor(risk / ((distance + cost) * f(rate_)) / step) * step
    if units < f(spec.min_lots) * f(spec.contract_size):
        units = f(0)
    units = min(units, f(spec.max_lots) * f(spec.contract_size))
    notional = units * f(t.entry) * f(rate_)
    return {
        "units": f(units),
        "loss_after": units * (distance + cost) * f(rate_),
        "margin": notional * f(spec.margin_rate),
        "risk": risk,
    }


def near(value: Decimal, exact: Fraction, places: int = 2) -> bool:
    return abs(Fraction(value) - exact) <= Fraction(1, 2 * 10**places)


@pytest.mark.parametrize(
    ("instrument", "loc", "entry", "stop", "mid", "spread"),
    [
        ("EUR_USD", -4, "1.08734", "1.08391", "1", "0.00011"),
        ("USD_JPY", -2, "149.817", "150.263", "0.006674", "0.014"),
        ("GBP_JPY", -2, "191.402", "190.118", "0.0052187", "0.031"),
        ("USD_KES", -2, "129.40", "131.75", "0.0077280", "0.35"),
        ("AUD_USD", -4, "0.65512", "0.65788", "1", "0.00009"),
    ],
)
def test_the_engine_agrees_with_the_oracle(
    instrument: str, loc: int, entry: str, stop: str, mid: str, spread: str
) -> None:
    direction = "long" if D(stop) < D(entry) else "short"
    spec = replace(PLAIN, slippage_pips=D("0.7"), commission_per_lot_side=D("2.5"))
    t = trade(
        instrument=instrument,
        direction=direction,
        entry=D(entry),
        stop=D(stop),
        target=None,
        spread=D(spread),
        balance=D("25431.17"),
        risk_percent=D("0.75"),
    )
    r = calc(t, spec=spec, pip_location=loc, conversion=rate(mid))
    o = oracle(t, spec, loc, D(mid))
    assert Fraction(r.units) == o["units"]
    assert near(r.loss_after_costs, o["loss_after"]) and near(r.margin, o["margin"])
    assert o["loss_after"] <= o["risk"]


# --------------------------------------------------------------------------- property tests
prices = st.decimals(min_value=D("0.5"), max_value=D("200"), places=5)
distances = st.decimals(min_value=D("0.0005"), max_value=D("5"), places=5)


@settings(max_examples=300, deadline=None)
@given(
    entry=prices,
    distance=distances,
    balance=st.decimals(min_value=D(100), max_value=D(5_000_000), places=2),
    risk=st.decimals(min_value=D("0.01"), max_value=D(5), places=2),
    spread=st.decimals(min_value=D(0), max_value=D("0.05"), places=5),
    slippage=st.decimals(min_value=D(0), max_value=D(10), places=1),
    commission=st.decimals(min_value=D(0), max_value=D(10), places=2),
    mid=st.decimals(min_value=D("0.001"), max_value=D(500), places=6),
    short=st.booleans(),
    inverse=st.booleans(),
)
def test_the_planned_loss_never_exceeds_the_risk_and_the_size_is_the_largest(
    entry: Decimal,
    distance: Decimal,
    balance: Decimal,
    risk: Decimal,
    spread: Decimal,
    slippage: Decimal,
    commission: Decimal,
    mid: Decimal,
    short: bool,
    inverse: bool,
) -> None:
    if not short and distance >= entry:
        return
    spec = replace(PLAIN, slippage_pips=slippage, commission_per_lot_side=commission)
    t = trade(
        direction="short" if short else "long",
        entry=entry,
        stop=entry + distance if short else entry - distance,
        target=None,
        balance=balance,
        risk_percent=risk,
        spread=spread,
    )
    conversion = rate("1", per=str(mid)) if inverse else rate(str(mid))
    r = calc(t, spec=spec, conversion=conversion)
    f = Fraction
    per_unit = (
        f(distance) + f(spread) + 2 * f(slippage) / 10_000 + 2 * f(commission) / 100_000
    ) * (1 / f(mid) if inverse else f(mid))
    allowed = f(balance) * f(risk) / 100
    assert f(r.units) * per_unit <= allowed  # exact, before display rounding
    step = 1000
    assert f(r.units) % step == 0 and r.units >= 0
    if r.status == "sized":
        assert (f(r.units) + step) * per_unit > allowed  # rounded down, not further
    if r.status == "below_minimum":
        assert r.units == 0 and per_unit * step > allowed and r.warnings
    assert near(r.loss_after_costs, f(r.units) * per_unit)


# ------------------------------------------------------------------ limits, margin, warnings
def test_the_minimum_and_maximum_sizes() -> None:
    tiny = calc(trade(balance=D(100), risk_percent=D("0.1")))
    assert tiny.status == "below_minimum" and tiny.units == 0 and tiny.lots == 0
    assert any("too small" in w for w in tiny.warnings)
    huge = calc(
        trade(balance=D(100_000_000), risk_percent=D(2)), spec=replace(PLAIN, max_lots=D(5))
    )
    assert huge.status == "capped_at_maximum" and huge.lots == D("5.00")
    assert any("capped" in w for w in huge.warnings)


def test_leverage_and_margin_warnings() -> None:
    tight = trade(stop=D("1.09990"), target=D("1.10100"), risk_percent=D(2))  # one pip stop
    r = calc(tight)
    assert r.units == D(2_000_000) and r.position_leverage == D("220.00")
    joined = " ".join(r.warnings)
    assert "leverage 220.00x is above the limit of 30x" in joined
    assert "Insufficient margin" in joined
    middling = calc(
        trade(stop=D("1.09900"), target=D("1.10200")), spec=replace(PLAIN, margin_rate=D("0.05"))
    )
    # 100,000 units: notional 110,000, margin 5,500 = 55% of 10,000
    assert middling.margin == D("5500.00") and middling.margin_use_percent == D("55.00")
    assert any("margin call" in w for w in middling.warnings)


def test_rate_quality_specification_and_tier_warnings() -> None:
    r = calc(
        trade(risk_percent=D(3), spread=None),
        conversion=en.Conversion(D(1), "x", NOW, ("indicative_rate", "simulated"), stale=True),
        reviewed=False,
        tier="exotic",
    )
    joined = " ".join(r.warnings)
    for phrase in (
        "above the limit of 2%",
        "indicative_rate, simulated, not a tradable quote",
        "stale",
        "spread is unknown",
        "unreviewed defaults",
        "less liquid pair",
    ):
        assert phrase in joined


def test_disclosures_are_always_present_and_promise_nothing() -> None:
    r = calc(trade())
    assert any("gap or slip" in d for d in r.disclosures)
    assert any("Leverage amplifies losses" in d for d in r.disclosures)
    texts = [*r.disclosures, *calc(trade(risk_percent=D(3), spread=None), reviewed=False).warnings]
    assert guarantee_problems(texts, forecast_used=False) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"entry": D(0)},
        {"balance": D(-1)},
        {"risk_percent": D(0)},
        {"risk_percent": D(101)},
        {"stop": D("1.10500")},  # long with the stop above the entry
        {"direction": "short"},  # short with the stop below the entry
        {"target": D("1.09000")},  # long with the target below the entry
        {"target": D(0)},
        {"spread": D("-0.0001")},
        {"entry": D("NaN")},
    ],
)
def test_bad_trades_are_refused(changes: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        trade(**changes)


def test_bad_rates_and_distances_are_refused() -> None:
    with pytest.raises(ValueError):
        calc(trade(), conversion=en.Conversion(D(0), "x", NOW, TRADABLE))
    with pytest.raises(ValueError):
        en.size(D(100), D(0), PLAIN)


def test_the_helpers() -> None:
    assert en.pip_size(-4) == D("0.0001") and en.pip_size(0) == D(1)
    assert en.pip_value_per_lot(PLAIN, -2, D("0.5")) == (D(1000), D(500))
    spec = replace(PLAIN, slippage_pips=D(1), commission_per_lot_side=D(5))
    assert en.cost_per_unit(spec, -4, D("0.0001")) == (D("0.0001"), D("0.0002"), D("0.0001"))
    assert en.exposure("USD_JPY", "short", D(1000), D(150)) == {"USD": D(-1000), "JPY": D(150000)}


# -------------------------------------------------------------------------------- conversion
def rates(**mids: str) -> dict[str, Rate]:
    return {k: Rate(D(v), NOW - timedelta(seconds=5), frozenset(TRADABLE)) for k, v in mids.items()}


def test_conversion_paths() -> None:
    table = rates(USD_JPY="150", GBP_USD="1.25", EUR_USD="1.1", EUR_GBP="0.88")
    assert resolve("USD", "USD", table, NOW, STALE) == SAME
    jpy = resolve("JPY", "USD", table, NOW, STALE)
    assert jpy.path == "1 / USD_JPY mid" and (jpy.numerator, jpy.denominator) == (D(1), D(150))
    gbp = resolve("GBP", "USD", table, NOW, STALE)
    assert (
        gbp.rate == D("1.25")
        and gbp.denominator == 1
        and gbp.path == "GBP_USD mid"
        and gbp.data_types == TRADABLE
    )
    cross = resolve("JPY", "GBP", table, NOW, STALE)
    assert cross.path == "1 / USD_JPY mid x 1 / GBP_USD mid"
    assert (cross.numerator, cross.denominator) == (D(1), D("187.5"))
    direct = resolve("GBP", "EUR", table, NOW, STALE)
    assert direct.path == "1 / EUR_GBP mid"  # a direct pair is preferred to the cross
    assert not jpy.stale and jpy.as_of == NOW - timedelta(seconds=5)


def test_a_missing_rate_is_refused_never_assumed() -> None:
    table = rates(USD_JPY="150")
    with pytest.raises(NoConversionRate):
        resolve("CHF", "USD", table, NOW, STALE)
    with pytest.raises(NoConversionRate):
        resolve("JPY", "SEK", table, NOW, STALE)
    with pytest.raises(NoConversionRate):
        resolve("GBP", "EUR", table, NOW, STALE)  # the USD legs are missing


def test_stale_and_indicative_rates_are_marked() -> None:
    def quote(code: str, mid: str, age: int) -> StoredQuote:
        at = NOW - timedelta(seconds=age)
        return StoredQuote(
            "fake", code, D(mid), D(mid), D(mid), at, at, "simulated", "ok", "connected"
        )

    table = rates_from(
        {
            "USD_KES": quote("USD_KES", "129", 120),
            "EUR_USD": quote("EUR_USD", "1.1", 5),
            "BAD_USD": quote("BAD_USD", "0", 5),
        },
        {"USD_KES"},
    )
    assert "BAD_USD" not in table
    kes = resolve("KES", "EUR", table, NOW, STALE)
    assert kes.stale and kes.as_of == NOW - timedelta(seconds=120)
    assert kes.data_types == ("indicative_rate", "simulated")
    r = calc(
        trade(instrument="USD_KES", entry=D("129.00"), stop=D("128.00"), target=None),
        pip_location=-2,
        conversion=kes,
        tier="exotic",
    )
    assert any("indicative_rate" in w for w in r.warnings) and any("stale" in w for w in r.warnings)


# ------------------------------------------------------------------------ the specification
def test_the_specification_file_covers_the_registry_and_is_unreviewed() -> None:
    version, review, specs = load_file()
    assert version >= 1 and review == "unreviewed"
    assert set(specs) == {s.code for s in load_registry().specs}
    for spec in specs.values():
        assert spec.contract_size > 0 and D(0) < spec.margin_rate <= 1


def test_a_bad_specification_file_is_refused(tmp_path: Path) -> None:
    item = {
        "code": "EUR_USD",
        "contract_size": "100000",
        "lot_step": "0.01",
        "min_lots": "0.01",
        "max_lots": "100",
        "margin_rate": "0.0333",
        "commission_per_lot_side": "0",
        "slippage_pips": "0.2",
    }
    for bad, field in (
        ({**item, "margin_rate": "0"}, "margin"),
        ({**item, "max_lots": "0.001"}, "sizes"),
        ({**item, "slippage_pips": "-1"}, "costs"),
    ):
        path = tmp_path / f"{field}.json"
        path.write_text(
            json.dumps({"version": 1, "review_status": "unreviewed", "instruments": [bad]})
        )
        with pytest.raises(ValueError):
            load_file(path)
    twice = tmp_path / "twice.json"
    twice.write_text(
        json.dumps({"version": 1, "review_status": "unreviewed", "instruments": [item, item]})
    )
    with pytest.raises(ValueError, match="unique"):
        load_file(twice)


def test_provider_differences_are_reported_not_applied() -> None:
    found = compare_with_provider(
        PLAIN, {"margin_rate": D("0.05"), "lot_step": D("0.01"), "swap": D(1)}
    )
    assert found == ["margin_rate: ours 0.0333, provider 0.05"]
    assert PLAIN.margin_rate == D("0.0333")
