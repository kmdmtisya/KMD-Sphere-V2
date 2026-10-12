"""Datasets judged by the deterministic answer policy and refusal rules (P10-T09.3, T09.4): numeric
fidelity, invented market data, guarantee language, stale or missing data, refusal appropriateness.
They run in CI and need no model and no database. The `verdicts_*` functions are also what the
regression meta-tests re-run with a defence removed."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.ai.orchestrator.guards import caveats_for
from app.ai.orchestrator.policy import Draft, SafetyPolicy
from app.ai.orchestrator.refusal import check_question
from app.ai.tools.base import ToolOutcome
from tests.ai_eval.harness import RECORDER, judge, load

pytestmark = pytest.mark.security
NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)
policy = SafetyPolicy(clock=lambda: NOW)


def answer(observed: list[dict[str, str]] | None = None, interpretation: str = "") -> str:
    return json.dumps(
        {
            "observed": observed or [],
            "calculated": [],
            "assumptions": [],
            "interpretation": interpretation,
        }
    )


def review_figure(row: dict[str, Any]) -> tuple[bool, tuple[str, ...]]:
    outcome = ToolOutcome(row["tool"], ok=True, data={"as_of": NOW.isoformat(), **row["data"]})
    verdict = policy.review(
        Draft(answer([{"text": row["text"], "source": row["tool"]}]), (outcome,))
    )
    if verdict.text is not None:
        RECORDER.accepted_outputs.append(verdict.text)
    return verdict.text is not None, verdict.problems


def figure_verdicts(dataset: str) -> dict[str, bool]:
    verdicts = {}
    for row in load(dataset):
        accepted, problems = review_figure(row)
        verdicts[row["id"]] = (
            accepted
            if row["expect"] == "accept"
            else (not accepted and "unsupported_figure" in problems)
        )
    return verdicts


def verdicts_numeric() -> dict[str, bool]:
    return figure_verdicts("numeric")


def verdicts_invented() -> dict[str, bool]:
    return figure_verdicts("invented")


def verdicts_fx() -> dict[str, bool]:
    return figure_verdicts("fx")


def verdicts_guarantee() -> dict[str, bool]:
    verdicts = {}
    for row in load("guarantee"):
        verdict = policy.review(Draft(answer(interpretation=row["text"]), ()))
        if verdict.text is not None:
            RECORDER.accepted_outputs.append(verdict.text)
        verdicts[row["id"]] = (verdict.text is not None) == (row["expect"] == "accept")
    return verdicts


def verdicts_stale() -> dict[str, bool]:
    verdicts = {}
    for row in load("stale"):
        outcomes = tuple(
            ToolOutcome(
                o["tool"],
                ok=True,
                data={
                    "as_of": (NOW - timedelta(hours=o["age_hours"])).isoformat(),
                    "complete": o["complete"],
                },
            )
            if o["ok"]
            else ToolOutcome(
                o["tool"], ok=False, error_code="not_found", error_message="Not found."
            )
            for o in row["outcomes"]
        )
        ok_tools = [o.tool for o in outcomes if o.ok]
        reply = answer(
            [{"text": "The data was retrieved.", "source": ok_tools[0]}] if ok_tools else None,
            "I could not retrieve all of your data." if not ok_tools else "Here is what I found.",
        )
        verdict = policy.review(Draft(reply, outcomes))
        caveats = caveats_for(outcomes, NOW, timedelta(hours=48))
        if row["expect_caveat"] is None:
            correct = verdict.text is not None and not any(
                "stale" in c or "could not be retrieved" in c for c in caveats
            )
        else:
            correct = (
                verdict.text is not None
                and any(row["expect_caveat"] in c for c in caveats)
                and any(row["expect_caveat"] in c for c in (verdict.structured or {})["caveats"])
            )
        verdicts[row["id"]] = correct
    return verdicts


def verdicts_refusal() -> dict[str, bool]:
    verdicts = {}
    for row in load("refusal"):
        refusal = check_question(row["question"])
        if row["expect"] == "answer":
            verdicts[row["id"]] = refusal is None
        else:
            verdicts[row["id"]] = refusal is not None and refusal.category == row["expect"]
    return verdicts


def test_numeric_fidelity_every_figure_traces_to_a_tool_result() -> None:
    judge("numeric", verdicts_numeric())


def test_invented_market_data_is_never_stated_and_supported_data_is() -> None:
    judge("invented", verdicts_invented())


def test_guarantee_and_certainty_language_is_rejected_and_denials_are_kept() -> None:
    judge("guarantee", verdicts_guarantee())


def test_stale_incomplete_and_missing_data_is_qualified_by_the_server() -> None:
    judge("stale", verdicts_stale())


def test_unsafe_requests_are_declined_and_legitimate_ones_answered() -> None:
    judge("refusal", verdicts_refusal())


def test_fx_rates_and_conversions_in_answers_come_from_the_fx_tool() -> None:
    judge("fx", verdicts_fx())
