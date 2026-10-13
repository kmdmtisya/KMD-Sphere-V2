"""Hard eligibility rules (P12-T02): which universe instruments opportunity analysis may consider
for a user. Pure and deterministic. An instrument is eligible only when every rule passes; each
rule says why it passed or failed, so an exclusion is never silent.

Rules:
- **Jurisdiction:** the user's country of residence is a supported launch jurisdiction (Kenya and
  the UAE, approved for P12) and the source says the instrument is offered there. Jurisdiction
  rules are **not legally reviewed** until P12-T10 (DEC-10), and every result says so.
- **Risk:** the instrument's risk level (1-5) is within the user's risk tolerance.
- **Liquidity:** money locked until maturity needs a horizon of at least 1 year, illiquid assets
  at least 5 years; without a stated horizon only cash-like and listed assets pass.
- **Active:** the instrument is active in the universe.

Eligibility is a filter for analysis, not a recommendation: an eligible instrument is merely one
that is not excluded."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.modules.assets.liquidity import Liquidity


class Rule(StrEnum):
    JURISDICTION = "jurisdiction"
    RISK = "risk"
    LIQUIDITY = "liquidity"
    ACTIVE = "active"


@dataclass(frozen=True)
class JurisdictionRules:
    """Per supported country: asset classes excluded there (none by default)."""

    country: str
    excluded_classes: frozenset[str] = frozenset()
    legally_reviewed: bool = False  # until P12-T10 (DEC-10)


LAUNCH_JURISDICTIONS: dict[str, JurisdictionRules] = {
    "KE": JurisdictionRules("KE"),
    "AE": JurisdictionRules("AE"),
}
JURISDICTION_NOTICE = (
    "Jurisdiction rules have not been legally reviewed yet; availability comes from the "
    "instrument source."
)

# The highest instrument risk level each tolerance accepts.
MAX_RISK_LEVEL: dict[str, int] = {"conservative": 2, "balanced": 3, "growth": 4, "aggressive": 5}

# The shortest horizon (years) at which money can be tied up this way.
MIN_HORIZON_YEARS: dict[Liquidity, int] = {
    Liquidity.IMMEDIATE: 0,
    Liquidity.MARKET: 0,
    Liquidity.TERM: 1,
    Liquidity.ILLIQUID: 5,
    Liquidity.UNKNOWN: 5,
}


@dataclass(frozen=True)
class Investor:
    """What eligibility needs to know about the user."""

    residence_country: str | None
    risk_tolerance: str | None  # from the latest risk profile; None without one
    horizon_years: int | None


@dataclass(frozen=True)
class Instrument:
    asset_class: str
    risk_level: int
    liquidity: Liquidity
    jurisdictions: Sequence[str]
    is_active: bool = True


@dataclass(frozen=True)
class RuleOutcome:
    rule: Rule
    passed: bool
    reason: str
    legally_reviewed: bool | None = None  # jurisdiction rules only


@dataclass(frozen=True)
class Eligibility:
    eligible: bool
    outcomes: tuple[RuleOutcome, ...]

    @property
    def reasons(self) -> list[str]:
        """Why it is excluded (empty when eligible)."""
        return [o.reason for o in self.outcomes if not o.passed]


def jurisdiction(
    investor: Investor,
    instrument: Instrument,
    rules: dict[str, JurisdictionRules] = LAUNCH_JURISDICTIONS,
) -> RuleOutcome:
    country = investor.residence_country
    if country is None:
        return RuleOutcome(
            Rule.JURISDICTION, False, "No country of residence is set.", legally_reviewed=False
        )
    rule = rules.get(country)
    if rule is None:
        return RuleOutcome(
            Rule.JURISDICTION,
            False,
            f"{country} is not a supported jurisdiction yet.",
            legally_reviewed=False,
        )
    if country not in instrument.jurisdictions:
        return RuleOutcome(
            Rule.JURISDICTION, False, f"Not offered in {country}.", rule.legally_reviewed
        )
    if instrument.asset_class in rule.excluded_classes:
        return RuleOutcome(
            Rule.JURISDICTION,
            False,
            f"{instrument.asset_class} is excluded in {country}.",
            rule.legally_reviewed,
        )
    return RuleOutcome(Rule.JURISDICTION, True, f"Offered in {country}.", rule.legally_reviewed)


def risk(investor: Investor, instrument: Instrument) -> RuleOutcome:
    tolerance = investor.risk_tolerance
    if tolerance is None or tolerance not in MAX_RISK_LEVEL:
        return RuleOutcome(Rule.RISK, False, "No risk profile is set.")
    ceiling = MAX_RISK_LEVEL[tolerance]
    if instrument.risk_level > ceiling:
        return RuleOutcome(
            Rule.RISK,
            False,
            f"Risk level {instrument.risk_level} is above the {ceiling} a {tolerance} profile "
            "accepts.",
        )
    return RuleOutcome(
        Rule.RISK, True, f"Risk level {instrument.risk_level} is within a {tolerance} profile."
    )


def liquidity(investor: Investor, instrument: Instrument) -> RuleOutcome:
    needed = MIN_HORIZON_YEARS[instrument.liquidity]
    if needed == 0:
        return RuleOutcome(Rule.LIQUIDITY, True, f"{instrument.liquidity.value} liquidity.")
    horizon = investor.horizon_years
    if horizon is None:
        return RuleOutcome(
            Rule.LIQUIDITY,
            False,
            f"{instrument.liquidity.value} liquidity needs a stated horizon of at least "
            f"{needed} years.",
        )
    if horizon < needed:
        return RuleOutcome(
            Rule.LIQUIDITY,
            False,
            f"{instrument.liquidity.value} liquidity needs a horizon of at least {needed} "
            f"years; the profile states {horizon}.",
        )
    return RuleOutcome(
        Rule.LIQUIDITY,
        True,
        f"{instrument.liquidity.value} liquidity fits a {horizon}-year horizon.",
    )


def active(instrument: Instrument) -> RuleOutcome:
    if instrument.is_active:
        return RuleOutcome(Rule.ACTIVE, True, "Active in the universe.")
    return RuleOutcome(Rule.ACTIVE, False, "No longer in the universe.")


def evaluate(
    investor: Investor,
    instrument: Instrument,
    rules: dict[str, JurisdictionRules] = LAUNCH_JURISDICTIONS,
) -> Eligibility:
    """Every rule, in a fixed order; eligible only when all pass."""
    outcomes = (
        jurisdiction(investor, instrument, rules),
        risk(investor, instrument),
        liquidity(investor, instrument),
        active(instrument),
    )
    return Eligibility(all(o.passed for o in outcomes), outcomes)
