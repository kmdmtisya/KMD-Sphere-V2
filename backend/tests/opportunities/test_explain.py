"""Opportunity explanations (P12-T06): the model may only explain the facts it is given. Invented
figures, forecasts, guarantees, links and unknown evidence are refused; one correction, then the
deterministic template."""

import json
import uuid
from typing import Any

from app.ai.providers.errors import LlmUnavailable
from app.ai.providers.fake import FakeLlmProvider, text_reply
from app.modules.opportunities.explain import explain, review, template

A, B = uuid.UUID(int=1), uuid.UUID(int=2)
EA, EB = uuid.UUID(int=11), uuid.UUID(int=12)


def candidate(asset: uuid.UUID, evidence: uuid.UUID, name: str) -> dict[str, Any]:
    return {
        "asset_id": str(asset),
        "symbol": name.upper()[:8],
        "name": name,
        "asset_class": "etf",
        "currency": "USD",
        "risk_level": 2,
        "liquidity": "market",
        "is_demo": True,
        "score": {
            "score": "71.5",
            "coverage_percent": "100",
            "confidence": "high",
            "factors": [
                {
                    "factor": "stability",
                    "status": "used",
                    "contribution": "20.1",
                    "explanation": "Volatility of 12% a year over the last year: 80/100.",
                },
                {
                    "factor": "cost",
                    "status": "used",
                    "contribution": "9",
                    "explanation": "Expense ratio 0.2% a year: 90/100.",
                },
            ],
            "reasons": [],
        },
        "prices_as_of": "2026-10-12",
        "universe_as_of": "2026-10-13T00:00:00+00:00",
        "evidence": [
            {
                "id": str(evidence),
                "title": "DEMO note",
                "summary": "Rates move prices.",
                "source": "demo",
                "licence_status": "demo",
                "published_at": "2026-09-01T00:00:00+00:00",
            }
        ],
        "compatibility": None,
    }


FACTS = [candidate(A, EA, "Demo Bond Fund"), candidate(B, EB, "Demo Gold Tracker")]


def entry(asset: uuid.UUID, evidence: uuid.UUID | None, **changes: Any) -> dict[str, Any]:
    base = {
        "asset_id": str(asset),
        "thesis": "A diversified fund that passed the eligibility rules.",
        "why_surfaced": "Its volatility of 12% a year and its 0.2% expense ratio scored well.",
        "key_risks": ["Prices fall when interest rates rise."],
        "assumptions": ["Scores describe the past."],
        "evidence_ids": [str(evidence)] if evidence else [],
    }
    return base | changes


def reply(*entries: dict[str, Any]) -> str:
    return json.dumps({"opportunities": list(entries)})


GOOD = reply(entry(A, EA), entry(B, EB))


def test_a_reply_that_only_explains_the_facts_passes() -> None:
    result, problems = review(GOOD, FACTS)
    assert problems == () and result is not None and set(result) == {A, B}


def test_each_kind_of_overreach_is_refused_with_its_code() -> None:
    cases = {
        "unsupported_figure": entry(A, EA, thesis="It returned 14.7% last year."),
        "return_forecast": entry(A, EA, thesis="It is expected to rise as rates fall."),
        "guarantee_language": entry(A, EA, thesis="Income is guaranteed."),
        "link_in_answer": entry(A, EA, thesis="See https://example.com for more."),
        "unknown_evidence": entry(A, EB),
        "missing_risks": entry(A, EA, key_risks=[]),
    }
    for code, bad in cases.items():
        _, problems = review(reply(bad, entry(B, EB)), FACTS)
        assert code in problems, (code, problems)
    _, missing = review(reply(entry(A, EA)), FACTS)
    assert missing == ("wrong_instruments",)
    _, prose = review("Here are your opportunities!", FACTS)
    assert prose == ("not_structured",)
    _, extra = review(reply(entry(A, EA, advice="buy now"), entry(B, EB)), FACTS)
    assert extra == ("not_structured",), "unknown fields are refused"


async def test_one_correction_then_the_model_explanation_is_used() -> None:
    llm = FakeLlmProvider(
        [
            text_reply(reply(entry(A, EA, thesis="It will rise 37%."), entry(B, EB))),
            text_reply(GOOD),
        ]
    )
    outcome = await explain(llm, FACTS)
    assert outcome.source == "model" and outcome.model == "fake-1"
    assert set(outcome.problems) == {"return_forecast", "unsupported_figure"}
    correction = llm.requests[1].messages[-1].content
    assert "do not forecast returns or prices" in correction
    assert "20%" not in correction, "only fixed wording goes back, never the reply"


async def test_two_bad_replies_or_no_model_or_an_outage_fall_back_to_the_template() -> None:
    bad = text_reply("not json")
    twice = await explain(FakeLlmProvider([bad, bad]), FACTS)
    assert twice.source == "template" and twice.problems == ("not_structured",)
    assert twice.explanations == template(FACTS)
    none = await explain(None, FACTS)
    assert none.source == "template" and none.problems == ("no_model",)
    down = await explain(FakeLlmProvider([LlmUnavailable("down")]), FACTS)
    assert down.source == "template" and down.problems == ("model_unavailable",)


async def test_the_model_sees_the_facts_and_nothing_else() -> None:
    llm = FakeLlmProvider([text_reply(GOOD)])
    await explain(llm, FACTS)
    system, user = llm.requests[0].messages
    assert system.role == "system" and "Use ONLY the facts" in system.content
    sent = json.loads(user.content)
    assert sent == {"candidates": FACTS}


def test_the_template_is_deterministic_cites_the_evidence_and_gives_no_advice() -> None:
    first, again = template(FACTS), template(FACTS)
    assert first == again
    t = first[A]
    assert "71.5 out of 100" in t.thesis and t.evidence_ids == [EA]
    assert "Volatility of 12% a year" in t.why_surfaced
    assert any("past movements do not predict future returns" in r for r in t.key_risks)
    text = " ".join(t.texts()).lower()
    for word in ("should", "buy", "guarantee", "will rise", "expected return"):
        assert word not in text, word
    _, problems = review(
        json.dumps({"opportunities": [e.model_dump(mode="json") for e in first.values()]}), FACTS
    )
    assert problems == (), "the template passes the same checks as the model"
