"""The checks an answer must pass before the user sees any of it (P10-T08.2).

Each guard returns short problem codes, never the offending text: a code can be logged, audited and
fed back to the model without carrying content. The checks are deterministic string rules; they are
a floor under the model's own instructions, not a replacement for them."""

import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.ai.orchestrator.answer import StructuredAnswer
from app.ai.tools.base import ToolOutcome

FORECAST_TOOLS = frozenset({"run_compound_forecast", "run_goal_forecast", "get_goal_progress"})

# --------------------------------------------------------------------------- number provenance
_NUMBER = re.compile(
    r"(?<![\w.:/])(?<!\w-)(?P<cur>[€$£]?)(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?"
    r"(?!\d|[:/]\d)"
    r"(?:\s?(?P<suffix>%|k\b|m\b|bn\b|b\b|thousand\b|million\b|billion\b))?",
    re.IGNORECASE,
)
_SCALE = {
    "k": Decimal(1_000),
    "thousand": Decimal(1_000),
    "m": Decimal(1_000_000),
    "million": Decimal(1_000_000),
    "b": Decimal(1_000_000_000),
    "bn": Decimal(1_000_000_000),
    "billion": Decimal(1_000_000_000),
}
SMALL_INTEGER = 10
YEARS = range(1900, 2101)


def _quantum(places: int) -> Decimal:
    return Decimal(1).scaleb(-places)


def _numbers_in(text: str) -> Iterable[Decimal]:
    for match in _NUMBER.finditer(text):
        try:
            yield Decimal(match["int"].replace(",", "") + (match["frac"] or ""))
        except InvalidOperation:  # pragma: no cover - the pattern only matches digits
            continue


def collect_evidence(values: Iterable[Any]) -> set[Decimal]:
    """Every number found in tool results, tool arguments and the user's own messages."""
    found: set[Decimal] = set()

    def walk(value: Any) -> None:
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, Decimal)):
            found.add(abs(Decimal(value)))
        elif isinstance(value, float):
            found.add(abs(Decimal(str(value))))
        elif isinstance(value, str):
            found.update(_numbers_in(value))
        elif isinstance(value, Mapping):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for value in values:
        walk(value)
    return found


def _supported(
    evidence: set[Decimal], value: Decimal, places: int, scale: Decimal, pct: bool
) -> bool:
    quantum = _quantum(places)
    for known in evidence:
        for candidate in (known / scale, known * 100 / scale) if pct else (known / scale,):
            if candidate.quantize(quantum, rounding=ROUND_HALF_UP) == value:
                return True
    return False


def unsupported_numbers(texts: Iterable[str], evidence: set[Decimal]) -> int:
    """How many figures in `texts` appear in no tool result, tool argument or user message of the
    turn. A figure counts as supported when it equals a known one, or a known one rounded to the
    precision shown ("5,505" for 5505.37; "5.5k" for 5505.37; "12.5%" for 12.5 or 0.125). Bare
    small integers (counts, ordinals), years and the digits inside dates, ids and words such as
    "Q4" are not figures."""
    bad = 0
    for text in texts:
        for match in _NUMBER.finditer(text):
            frac = match["frac"] or ""
            digits = match["int"].replace(",", "")
            value = Decimal(digits + frac)
            suffix = (match["suffix"] or "").lower()
            plain = not match["cur"] and not suffix and not frac
            if plain and (value <= SMALL_INTEGER or int(value) in YEARS):
                continue
            places = len(frac) - 1 if frac else 0
            scale = _SCALE.get(suffix, Decimal(1))
            if not _supported(evidence, value, places, scale, suffix == "%"):
                bad += 1
    return bad


# ------------------------------------------------------------------------ guarantee language
_SENTENCE = re.compile(r"(?<=[.!?;])\s+|\n+")
_NEGATION = re.compile(
    r"\b(not|no|nothing|none|never|neither|nor|without|cannot|can't|isn't|aren't|doesn't|don't|won't)\b|n't",
    re.IGNORECASE,
)
# Wording that can appear in a denial ("this is not a guarantee"), so a negation excuses it.
_GUARANTEE = re.compile(
    r"\b(guarantee[sd]?|guaranteeing|risk[- ]free|riskless|assured|surefire|foolproof|"
    r"(?:is|are) certain)\b",
    re.IGNORECASE,
)
# Wording that is never acceptable, negated or not.
_CERTAINTY = re.compile(
    r"\b(no risk|can(?:no|')t lose|cannot lose|sure (?:thing|bet|win)|definitely will|"
    r"will definitely|certain to|certainly will|no chance of (?:loss|losing))\b",
    re.IGNORECASE,
)
_FUTURE = re.compile(
    r"\b(?:will|is going to|are going to)\s+(?:\w+\s+){0,3}"
    r"(?:reach|be worth|have|grow|earn|become|hit|total|double|triple)\b",
    re.IGNORECASE,
)
_HEDGE = re.compile(
    r"\b(could|might|may|would|if|assum\w*|illustrat\w*|scenario|estimate\w*|project\w*|"
    r"expected|approximately|about|roughly|under|based on)\b",
    re.IGNORECASE,
)


def guarantee_problems(texts: Iterable[str], forecast_used: bool) -> list[str]:
    problems: list[str] = []
    for text in texts:
        for sentence in _SENTENCE.split(text):
            if _CERTAINTY.search(sentence):
                problems.append("certainty_language")
            if _GUARANTEE.search(sentence) and not _NEGATION.search(sentence):
                problems.append("guarantee_language")
            if forecast_used and _FUTURE.search(sentence) and not _HEDGE.search(sentence):
                problems.append("unhedged_forecast")
    return sorted(set(problems))


# ------------------------------------------------------------------------------ links, sources
_LINK = re.compile(r"(https?://|www\.|\bftp://|\bdata:|\bjavascript:)", re.IGNORECASE)


def link_problems(texts: Iterable[str]) -> list[str]:
    return ["link_in_answer"] if any(_LINK.search(t) for t in texts) else []


def source_problems(answer: StructuredAnswer, ok_tools: set[str]) -> list[str]:
    cited = [*answer.observed, *answer.calculated]
    return ["source_not_used"] if any(c.source not in ok_tools for c in cited) else []


# -------------------------------------------------------------------------- stale / incomplete
STALE_NOTICE = (
    "Some of the data behind this answer is stale or incomplete ({tools}); figures may not "
    "reflect current values."
)
FORECAST_NOTICE = (
    "Forecasts and goal estimates are illustrations under the stated assumptions, not "
    "predictions or guaranteed returns."
)
NO_DATA_NOTICE = "Some data could not be retrieved ({tools}); this answer covers only what could."


def _as_of(outcome: ToolOutcome) -> datetime | None:
    raw = (outcome.data or {}).get("as_of")
    if not isinstance(raw, str):
        return None
    try:
        value = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def caveats_for(
    outcomes: Iterable[ToolOutcome], now: datetime, stale_after: timedelta
) -> list[str]:
    """The qualifications the server adds itself, whatever the model wrote."""
    outcomes = list(outcomes)
    stale = sorted(
        {
            o.tool
            for o in outcomes
            if o.ok
            and (
                (o.data or {}).get("complete") is False
                or ((as_of := _as_of(o)) is not None and now - as_of > stale_after)
            )
        }
    )
    failed = sorted({o.tool for o in outcomes if not o.ok})
    notes: list[str] = []
    if stale:
        notes.append(STALE_NOTICE.format(tools=", ".join(stale)))
    if failed:
        notes.append(NO_DATA_NOTICE.format(tools=", ".join(failed)))
    if any(o.ok and o.tool in FORECAST_TOOLS for o in outcomes):
        notes.append(FORECAST_NOTICE)
    return notes
