"""The hook where an answer is checked before any of it reaches the user (docs/ai-governance.md,
section 4). P10-T06 ships the minimal policy (an answer must not be empty); P10-T08 replaces it with
the structured-output, number-provenance, guarantee-language and stale-data checks."""

from dataclasses import dataclass
from typing import Protocol

from app.ai.tools.base import ToolOutcome


@dataclass(frozen=True)
class Draft:
    """What the model produced and the trusted results of the same turn it may rest on."""

    text: str
    outcomes: tuple[ToolOutcome, ...]


@dataclass(frozen=True)
class Verdict:
    """`text` is what the user may see; None means the draft is rejected."""

    text: str | None
    structured: dict[str, object] | None = None


class AnswerPolicy(Protocol):
    def review(self, draft: Draft) -> Verdict: ...


class MinimalPolicy:
    def review(self, draft: Draft) -> Verdict:
        text = draft.text.strip()
        return Verdict(text=text or None)
