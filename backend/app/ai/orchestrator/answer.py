"""The structured answer (P10-T08.1): what the model must produce and how it is shown.

Every answer separates what was observed (trusted data with its source), what WealthSphere
calculated, the assumptions used, and the model's own interpretation (docs/ai-governance.md,
section 4). Facts and calculations must name the tool that supplied them; the policy checks that
the tool ran in the same turn."""

import json
import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
Source = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
MAX_ITEMS = 12

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


class Cited(BaseModel):
    """A fact or a calculated figure, with the tool that returned it."""

    model_config = ConfigDict(extra="forbid")

    text: Text
    source: Source


class StructuredAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed: list[Cited] = Field(default_factory=list, max_length=MAX_ITEMS)
    calculated: list[Cited] = Field(default_factory=list, max_length=MAX_ITEMS)
    assumptions: list[Text] = Field(default_factory=list, max_length=MAX_ITEMS)
    interpretation: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1500)] = ""
    # Added by the server, never by the model: fixed qualifications (stale data, forecasts).
    caveats: list[Text] = Field(default_factory=list, max_length=MAX_ITEMS)

    def is_empty(self) -> bool:
        return not (self.observed or self.calculated or self.assumptions or self.interpretation)

    def texts(self) -> list[str]:
        """Every piece of text the model wrote."""
        return [
            *(c.text for c in self.observed),
            *(c.text for c in self.calculated),
            *self.assumptions,
            self.interpretation,
        ]


class NotAnAnswer(Exception):
    """The reply is not the required JSON object (no details: they could echo model output)."""


def parse_answer(reply: str) -> StructuredAnswer:
    """The reply as a `StructuredAnswer`. Accepts the bare JSON object, optionally in a code fence;
    anything else (prose, extra keys, wrong types, over-long text) is `NotAnAnswer`."""
    text = reply.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except ValueError as error:
        raise NotAnAnswer from error
    if not isinstance(data, dict) or "caveats" in data:
        raise NotAnAnswer  # the model does not write caveats
    try:
        answer = StructuredAnswer.model_validate(data)
    except ValidationError as error:
        raise NotAnAnswer from error
    if answer.is_empty():
        raise NotAnAnswer
    return answer


def render(answer: StructuredAnswer) -> str:
    """Plain text for display and streaming. The mobile app renders `structured` itself; this is
    the fallback and what the stored message holds."""
    parts: list[str] = []

    def section(title: str, lines: list[str]) -> None:
        if lines:
            parts.append(title + "\n" + "\n".join(f"- {line}" for line in lines))

    section("Observed", [f"{c.text} [{c.source}]" for c in answer.observed])
    section("Calculated", [f"{c.text} [{c.source}]" for c in answer.calculated])
    section("Assumptions", answer.assumptions)
    if answer.interpretation:
        parts.append("Interpretation\n" + answer.interpretation)
    section("Please note", answer.caveats)
    return "\n\n".join(parts)
