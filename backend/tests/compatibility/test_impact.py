"""Compatibility (P12-T04): adding a hypothetical amount re-measures the portfolio with the same
rules; the verdict follows eligibility, the minimum investment and what gets materially worse."""

import uuid
from decimal import Decimal

from app.modules.assets.liquidity import Liquidity
from app.modules.compatibility.impact import Candidate, Verdict, add, assess, measure
from app.modules.doctor.rules import Check, Holding, Inputs, Severity
from app.modules.universe.eligibility import Instrument, Investor, evaluate

D = Decimal
STOCK = uuid.UUID(int=1)
BONDS = uuid.UUID(int=2)
NEW = uuid.UUID(int=9)
OK = evaluate(Investor("KE", "balanced", 3), Instrument("etf", 2, Liquidity.MARKET, ["KE"]))
TOO_RISKY = evaluate(Investor("KE", "balanced", 3), Instrument("etf", 5, Liquidity.MARKET, ["KE"]))


def portfolio() -> Inputs:
    """1,000 USD: a 500 stock, a 400 bond ETF and 100 cash."""
    return Inputs(
        "USD",
        D(1000),
        [
            Holding(STOCK, D(500), "stock", "USD", "US", "Tech"),
            Holding(BONDS, D(400), "etf", "USD"),
        ],
        {"USD": D(100)},
        complete=True,
    )


def etf(asset_id: uuid.UUID = NEW, currency: str = "USD") -> Candidate:
    return Candidate(asset_id, "etf", currency)


def test_adding_new_money_creates_or_enlarges_a_holding() -> None:
    new = add(portfolio(), etf(), D(100))
    assert new.total == D(1100) and len(new.holdings) == 3
    more = add(portfolio(), etf(BONDS), D(100))
    assert more.total == D(1100) and len(more.holdings) == 2
    assert next(h.value for h in more.holdings if h.asset_id == BONDS) == D(500)
    assert portfolio().total == D(1000), "the original is unchanged"


def test_measures_before_and_after() -> None:
    before = measure(portfolio(), etf(currency="EUR"))
    after = measure(add(portfolio(), etf(currency="EUR"), D(250)), etf(currency="EUR"))
    assert (before.candidate_share, after.candidate_share) == (D(0), D("0.2"))
    assert (before.largest_holding, after.largest_holding) == (D("0.5"), D("0.4"))
    assert after.foreign_currency == D("0.2") and after.class_share == D("0.52")
    assert after.accessible == D(1), "all listed or cash"


def test_a_small_diversifying_addition_fits() -> None:
    a = assess(portfolio(), etf(), D(100), OK, minimum=None, amount_in_instrument_currency=D(100))
    assert a.verdict is Verdict.FITS and a.reasons == ()
    # Sector concentration improves; the unknown-country share passes 50% (an info finding),
    # which is not a reason for caution.
    changes = {c.check: (c.before, c.after) for c in a.changes}
    assert changes[Check.SECTOR_CONCENTRATION] == (Severity.HIGH, Severity.MEDIUM)
    assert changes[Check.GEOGRAPHIC_CONCENTRATION] == (Severity.OK, Severity.INFO)


def test_an_ineligible_instrument_is_not_suitable_with_the_rules_reasons() -> None:
    a = assess(
        portfolio(), etf(), D(100), TOO_RISKY, minimum=None, amount_in_instrument_currency=D(100)
    )
    assert a.verdict is Verdict.NOT_SUITABLE
    assert [r.code for r in a.reasons] == ["eligibility_risk"]


def test_the_minimum_investment_blocks_or_cannot_be_checked() -> None:
    below = assess(
        portfolio(), etf(), D(100), OK, minimum=D(500), amount_in_instrument_currency=D(100)
    )
    assert below.verdict is Verdict.NOT_SUITABLE and below.reasons[0].code == "below_minimum"
    enough = assess(
        portfolio(), etf(), D(100), OK, minimum=D(100), amount_in_instrument_currency=D(100)
    )
    assert enough.verdict is Verdict.FITS
    unknown = assess(
        portfolio(), etf(), D(100), OK, minimum=D(50), amount_in_instrument_currency=None
    )
    assert unknown.verdict is Verdict.CAUTION and unknown.reasons[0].code == "minimum_unchecked"


def test_an_amount_that_makes_a_check_materially_worse_calls_for_caution() -> None:
    a = assess(
        portfolio(),
        etf(currency="EUR"),
        D(1500),
        OK,
        minimum=None,
        amount_in_instrument_currency=D(1500),
    )
    assert a.verdict is Verdict.CAUTION
    codes = {r.code for r in a.reasons}
    assert "large_holding" in codes and "worsens_currency_exposure" in codes
    change = next(c for c in a.changes if c.check is Check.CURRENCY_EXPOSURE)
    assert (change.before, change.after) == (Severity.OK, Severity.MEDIUM)
    assert a.after.candidate_share == D("0.6")


def test_the_same_question_always_gets_the_same_answer() -> None:
    args = (portfolio(), etf(), D(300), OK)
    kw = {"minimum": None, "amount_in_instrument_currency": D(300)}
    assert assess(*args, **kw) == assess(*args, **kw)  # type: ignore[arg-type]
