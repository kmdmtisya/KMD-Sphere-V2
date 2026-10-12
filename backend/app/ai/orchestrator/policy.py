"""The policy an answer must satisfy before any of it reaches the user (docs/ai-governance.md,
section 4; P10-T08).

`review` turns the model's reply into a validated `StructuredAnswer` or a list of problem codes.
Problems go back to the model once, as codes only; a reply that still fails is refused. The server
adds its own qualifications (stale or missing data, forecasts), so none depends on the model."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from app.ai.orchestrator.answer import NotAnAnswer, StructuredAnswer, parse_answer, render
from app.ai.orchestrator.guards import (
    FORECAST_TOOLS,
    caveats_for,
    collect_evidence,
    guarantee_problems,
    link_problems,
    source_problems,
    unsupported_numbers,
)
from app.ai.tools.base import ToolOutcome


@dataclass(frozen=True)
class Draft:
    """The model's reply and everything of the same turn it may rest on."""

    text: str
    outcomes: tuple[ToolOutcome, ...]
    arguments: tuple[Mapping[str, Any], ...] = ()
    user_texts: tuple[str, ...] = ()


@dataclass(frozen=True)
class Verdict:
    """`text` is what the user may see; None means rejected, with the reasons in `problems`."""

    text: str | None
    structured: dict[str, Any] | None = None
    problems: tuple[str, ...] = field(default_factory=tuple)


class AnswerPolicy(Protocol):
    def review(self, draft: Draft) -> Verdict: ...


class SafetyPolicy:
    def __init__(
        self,
        stale_after: timedelta = timedelta(hours=48),
        clock: Any = lambda: datetime.now(UTC),
    ) -> None:
        self._stale_after = stale_after
        self._clock = clock

    def review(self, draft: Draft) -> Verdict:
        try:
            answer = parse_answer(draft.text)
        except NotAnAnswer:
            return Verdict(None, problems=("not_structured",))

        texts = answer.texts()
        ok_tools = {o.tool for o in draft.outcomes if o.ok}
        evidence = collect_evidence(
            [
                *(o.data for o in draft.outcomes if o.ok),
                *draft.arguments,
                *draft.user_texts,
            ]
        )
        problems = [
            *source_problems(answer, ok_tools),
            *link_problems(texts),
            *guarantee_problems(texts, forecast_used=bool(ok_tools & FORECAST_TOOLS)),
        ]
        if unsupported_numbers(texts, evidence):
            problems.append("unsupported_figure")
        if problems:
            return Verdict(None, problems=tuple(sorted(set(problems))))

        final = StructuredAnswer(
            **answer.model_dump(exclude={"caveats"}),
            caveats=caveats_for(draft.outcomes, self._clock(), self._stale_after),
        )
        return Verdict(render(final), structured=final.model_dump(mode="json"))


CORRECTIONS = {
    "not_structured": "reply with only the JSON object described, no other text",
    "source_not_used": "cite only tools that returned data in this turn",
    "link_in_answer": "do not include links or web addresses",
    "guarantee_language": "do not describe any outcome as guaranteed",
    "certainty_language": "do not describe any outcome as certain or free of risk",
    "unhedged_forecast": "describe forecasts as illustrations under the stated assumptions",
    "unsupported_figure": "state only figures that a tool returned in this turn or that the user "
    "gave; remove or replace any other figure",
}


def correction_message(problems: tuple[str, ...]) -> str:
    """Fixed wording per problem code: nothing the model or the user wrote is repeated."""
    rules = "; ".join(CORRECTIONS.get(p, p) for p in problems)
    return f"Your reply was not accepted. Reply again as the JSON object only: {rules}."
