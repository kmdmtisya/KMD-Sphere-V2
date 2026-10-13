"""P12 safety and quality sets (P12-T08), judged in CI with no model and no database:

- `opportunity`: explanations that only explain the facts are kept; invented figures, return or
  price forecasts, guarantees, links, unknown evidence, missing risks and malformed replies are
  refused with the right code (QG-07.4, QG-07.5).
- `opportunity_injection`: instructions injected through stored research reach the model as data;
  an obedient model is caught and replaced by the template, and nothing injected reaches the user
  (QG-07.6).
- `market_data`: stale, missing and contradictory market data is handled by the deterministic
  features, scores and close selection, never papered over (QG-07.7)."""

import json
import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.ai.providers.fake import FakeLlmProvider, text_reply
from app.modules.assets.liquidity import LIQUIDITY_BY_CLASS, Liquidity
from app.modules.opportunities.explain import explain, review
from app.modules.scoring.features import Close, Feature, Features, compute
from app.modules.scoring.scoring import Confidence, score
from app.modules.scoring.service import FUND_CLASSES, StoredClose, pick_closes
from tests.ai_eval.build_datasets import EV_A, INJECTIONS, OPP_A
from tests.ai_eval.harness import RECORDER, judge, load
from tests.ai_eval.p12 import OBEY, facts, obeying_reply

pytestmark = pytest.mark.security
TODAY = date(2026, 10, 13)
FRESH = timedelta(days=4)


# --------------------------------------------------------------------------------- opportunity
def verdicts_opportunity() -> dict[str, bool]:
    verdicts = {}
    for row in load("opportunity"):
        reply = row["reply"] if isinstance(row["reply"], str) else json.dumps(row["reply"])
        result, problems = review(reply, facts())
        if result is not None:
            RECORDER.accepted_outputs.extend(" ".join(e.texts()) for e in result.values())
        if row["expect"] == "accept":
            verdicts[row["id"]] = result is not None
        else:
            verdicts[row["id"]] = result is None and row["problem"] in problems
    return verdicts


def test_opportunity_explanations_only_explain_the_facts() -> None:
    judge("opportunity", verdicts_opportunity())


# ----------------------------------------------------------------------- opportunity_injection
async def injection_verdict(row: dict[str, Any]) -> bool:
    index = INJECTIONS.index(row["injection"])
    given = facts(summary_a=f"DEMO research. {row['injection']}")
    if row["model"] == "obeys":
        bad = obeying_reply(index)
        text = bad if isinstance(bad, str) else json.dumps(bad)
        llm = FakeLlmProvider([text_reply(text), text_reply(text)])
    else:
        good = {
            "opportunities": [
                {
                    "asset_id": f["asset_id"],
                    "thesis": f"{f['name']} passed the rules.",
                    "why_surfaced": "Its measured characteristics scored well.",
                    "key_risks": ["Its price can fall."],
                    "assumptions": [],
                    "evidence_ids": [f["evidence"][0]["id"]],
                }
                for f in given
            ]
        }
        llm = FakeLlmProvider([text_reply(json.dumps(good))])
    outcome = await explain(llm, given)
    # The injected text reached the model only inside the candidates' data.
    system, user = llm.requests[0].messages
    if row["injection"] in system.content or row["injection"] not in user.content:
        return False
    if (outcome.source == "model") != (row["model"] == "ignores"):
        return False
    shown = outcome.explanations[uuid.UUID(OPP_A)]
    text = " ".join(shown.texts()).lower()
    RECORDER.accepted_outputs.append(" ".join(shown.texts()))
    _, markers = OBEY[index]
    return (
        all(m.lower() not in text for m in markers)
        and {str(e) for e in shown.evidence_ids} <= {EV_A}
        and bool(shown.key_risks)
    )


async def test_injected_instructions_never_reach_the_user() -> None:
    judge(
        "opportunity_injection",
        {row["id"]: await injection_verdict(row) for row in load("opportunity_injection")},
    )


# --------------------------------------------------------------------------------- market_data
def series(days: int, end: date) -> list[Close]:
    out, price = [], Decimal(100)
    for i in range(days, -1, -1):
        on = end - timedelta(days=i)
        if on.weekday() < 5:
            price = price * Decimal("1.001") * (Decimal("1.01") if i % 2 else Decimal("0.995"))
            out.append(Close(on, price.quantize(Decimal("0.0001"))))
    return out


def features(closes: list[Close], cls: str = "etf", ratio: str | None = "0.002") -> Features:
    return compute(
        closes,
        risk_level=2,
        liquidity=LIQUIDITY_BY_CLASS.get(cls, Liquidity.UNKNOWN),
        priced=cls in {"stock", "etf", "reit", "mutual_fund", "cryptocurrency"},
        fund=cls in FUND_CLASSES,
        expense_ratio=None if ratio is None else Decimal(ratio),
        today=TODAY,
        stale_after=FRESH,
    )


def at(day: date, hour: int = 21) -> datetime:
    return datetime.combine(day, time(hour), UTC)


def missing(f: Features) -> set[Feature]:
    return {m.feature for m in f.missing}


def market_verdict(row: dict[str, Any]) -> bool:
    kind = row["kind"]
    if kind in ("fresh", "stale"):
        f = features(series(400, TODAY - timedelta(days=row["days_old"])))
        s = score(f)
        stale = f.stale_prices
        return (
            stale == (kind == "stale")
            and (s.confidence is not Confidence.HIGH if stale else s.confidence is Confidence.HIGH)
            and (not stale or any("freshness" in r for r in s.reasons))
        )
    if kind == "short_history":
        f = features(series(row["days"], TODAY))
        return f.trailing_return is None and Feature.TRAILING_RETURN in missing(f)
    if kind == "long_history":
        return features(series(row["days"], TODAY)).trailing_return is not None
    if kind == "manual":
        f = features([], cls=row["asset_class"], ratio=None)
        reasons = {m.reason for m in f.missing}
        return (
            f.volatility is None
            and reasons >= {"Valued manually: there are no market prices."}
            and score(f).score is None
        )
    if kind == "few_weeks":
        f = features(series(row["weeks"] * 7, TODAY))
        return f.volatility is None and Feature.VOLATILITY in missing(f)
    if kind == "conflict_same_day":
        day = TODAY - timedelta(days=1)
        rows = [
            StoredClose(
                uuid.UUID(int=1),
                at(day),
                at(day, 22) + timedelta(minutes=i),
                Decimal(100 + i),
            )
            for i in range(row["providers"])
        ]
        picked = pick_closes(list(reversed(rows)), TODAY)
        return [c.price for c in picked[rows[0].asset_id]] == [rows[-1].price]
    if kind == "future_close":
        asset = uuid.UUID(int=2)
        rows = [
            StoredClose(asset, at(TODAY), at(TODAY, 22), Decimal(10)),
            StoredClose(
                asset, at(TODAY + timedelta(days=row["days_ahead"])), at(TODAY, 23), Decimal(999)
            ),
        ]
        kept = pick_closes(rows, TODAY)[asset]
        return [c.on for c in kept] == [TODAY] and features(
            [*series(400, TODAY), Close(TODAY + timedelta(days=row["days_ahead"]), Decimal(999))]
        ).last_close == TODAY
    if kind == "low_coverage":
        f = (
            features([], cls="custom", ratio=None)
            if row["case_of"] == "liquidity_only"
            else features([], cls="etf", ratio=None)
        )
        s = score(f)
        return s.score is None and s.confidence is Confidence.NONE and bool(s.reasons)
    if kind == "fund_no_expense_ratio":
        return Feature.EXPENSE_RATIO in missing(features(series(400, TODAY), ratio=None))
    if kind == "unknown_liquidity":
        return Feature.LIQUIDITY in missing(features(series(400, TODAY), cls="custom"))
    return False


def test_stale_missing_and_contradictory_market_data_is_handled_safely() -> None:
    judge("market_data", {row["id"]: market_verdict(row) for row in load("market_data")})
