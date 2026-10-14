"""The Forex Copilot's evaluation sets (P13-T10.5), judged by the deterministic answer policy and
refusal rules, with no model and no database:

- `forex_figures` (QG-18.1): every price, indicator, forecast and risk figure in an answer comes
  from a forex tool of the same turn;
- `forex_safety` (QG-18.3): guarantee, certainty and trade-instruction wording is rejected, honest
  qualifications are kept, and requests to place trades are declined while questions about them
  are answered;
- `forex_stale` (QG-18.2, QG-18.5): the server itself qualifies stale, incomplete, simulated,
  uncalibrated, research, backtest, paper and DEMO data, and lists each forex source with its
  time, data types and model version."""

import json
from datetime import timedelta
from typing import Any

import pytest

from app.ai.orchestrator import guards
from app.ai.orchestrator.policy import Draft
from app.ai.orchestrator.refusal import check_question
from app.ai.tools.base import ToolOutcome
from tests.ai_eval.harness import RECORDER, judge, load
from tests.ai_eval.test_policy_datasets import NOW, figure_verdicts, policy

pytestmark = pytest.mark.security
FOREX_NOTICES = (
    guards.SIMULATED_NOTICE,
    guards.CALIBRATION_NOTICE,
    guards.RESEARCH_NOTICE,
    guards.PAPER_NOTICE,
    guards.BACKTEST_NOTICE,
    guards.DEMO_NOTICE,
)
FORECAST = ToolOutcome(
    "get_forecast",
    ok=True,
    data={"as_of": NOW.isoformat(), "prob_up": "0.5612", "probability_label": "Calibrated"},
)


def interpretation(text: str) -> str:
    return json.dumps(
        {
            "observed": [{"text": "The forecast was retrieved.", "source": "get_forecast"}],
            "calculated": [],
            "assumptions": [],
            "interpretation": text,
        }
    )


def verdicts_forex_figures() -> dict[str, bool]:
    return figure_verdicts("forex_figures")


def verdicts_forex_safety() -> dict[str, bool]:
    verdicts = {}
    for row in load("forex_safety"):
        if row["kind"] == "question":
            refusal = check_question(row["text"])
            verdicts[row["id"]] = (
                refusal is not None
                and refusal.category == "trade_execution"
                and "paper account" in refusal.message
                if row["expect"] == "refuse"
                else refusal is None
            )
            continue
        verdict = policy.review(Draft(interpretation(row["text"]), (FORECAST,)))
        if verdict.text is not None:
            RECORDER.accepted_outputs.append(verdict.text)
        verdicts[row["id"]] = (verdict.text is not None) == (row["expect"] == "accept")
    return verdicts


def _outcome(row: dict[str, Any]) -> ToolOutcome:
    if row.get("failed"):
        return ToolOutcome(
            row["tool"], ok=False, error_code="not_found", error_message="Not found."
        )
    data = {
        "as_of": (NOW - timedelta(hours=row["age_hours"])).isoformat(),
        "complete": row["complete"],
        **row["data"],
    }
    return ToolOutcome(row["tool"], ok=True, data=data)


def verdicts_forex_stale() -> dict[str, bool]:
    verdicts = {}
    for row in load("forex_stale"):
        outcome = _outcome(row)
        reply = json.dumps(
            {
                "observed": [{"text": "The data was retrieved.", "source": row["tool"]}]
                if outcome.ok
                else [],
                "calculated": [],
                "assumptions": [],
                "interpretation": "Here is what I found."
                if outcome.ok
                else "I could not retrieve the data.",
            }
        )
        verdict = policy.review(Draft(reply, (outcome,)))
        structured = verdict.structured or {}
        caveats: list[str] = structured.get("caveats", [])
        sources: list[dict[str, Any]] = structured.get("sources", [])
        ok = verdict.text is not None
        if row["expect_caveats"]:
            ok = ok and all(any(f in c for c in caveats) for f in row["expect_caveats"])
        else:
            ok = ok and not any(n in caveats for n in FOREX_NOTICES)
        expected = row["expect_source"]
        if expected is None:
            ok = ok and sources == []
        else:
            ok = (
                ok
                and len(sources) == 1
                and sources[0]["tool"] == row["tool"]
                and sources[0]["as_of"] is not None
                and all(sources[0].get(k) == v for k, v in expected.items())
            )
        verdicts[row["id"]] = ok
    return verdicts


def test_forex_figures_come_from_the_forex_tools() -> None:
    judge("forex_figures", verdicts_forex_figures())


def test_forex_answers_never_promise_or_instruct_and_trade_requests_are_declined() -> None:
    judge("forex_safety", verdicts_forex_safety())


def test_the_server_qualifies_forex_data_and_names_its_sources() -> None:
    judge("forex_stale", verdicts_forex_stale())


def test_the_rendered_answer_lists_the_sources_with_time_and_model() -> None:
    outcome = ToolOutcome(
        "get_forecast",
        ok=True,
        data={
            "as_of": NOW.isoformat(),
            "generated_at": NOW.isoformat(),
            "model": {"name": "arima", "version": "v3", "calibration_status": "calibrated"},
            "prob_up": "0.5612",
        },
    )
    reply = json.dumps(
        {
            "observed": [],
            "calculated": [
                {
                    "text": "The model gives a 56.12% probability of a rise.",
                    "source": "get_forecast",
                }
            ],
            "assumptions": [],
            "interpretation": "This is a model output, not a promise.",
        }
    )
    verdict = policy.review(Draft(reply, (outcome,)))
    assert verdict.text is not None and "Sources\n- get_forecast as of" in verdict.text
    assert "model arima v3" in verdict.text and "generated" in verdict.text
    with_sources = json.dumps({**json.loads(reply), "sources": [{"tool": "x"}]})
    assert policy.review(Draft(with_sources, (outcome,))).problems == ("not_structured",)


def test_advice_is_only_checked_when_a_forex_tool_ran() -> None:
    plain = json.dumps(
        {"observed": [], "calculated": [], "assumptions": [], "interpretation": "Go long today."}
    )
    assert policy.review(Draft(plain, ())).text is not None  # outside the Forex Copilot
    assert policy.review(Draft(plain, (FORECAST,))).problems == ("personal_advice",)
