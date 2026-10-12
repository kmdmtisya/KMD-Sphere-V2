"""The scope of a chat, enforced on the server (P10-T06.2).

The client may ask to narrow a chat to one portfolio. The orchestrator first checks that the
portfolio is the caller's, then applies the scope to every tool call itself: a tool that takes a
portfolio gets the scoped one, and a call naming another portfolio is refused. The model is told the
scope in the prompt, but nothing depends on it obeying."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.ai.tools.base import ToolSpec

SCOPE_ARGUMENT = "portfolio_id"


@dataclass(frozen=True)
class Scope:
    portfolio_id: uuid.UUID | None = None


class OutOfScopeError(Exception):
    """A tool call named something outside the chat's scope."""


def takes_portfolio(spec: ToolSpec) -> bool:
    return SCOPE_ARGUMENT in spec.parameters.get("properties", {})


def apply_scope(spec: ToolSpec, arguments: Mapping[str, Any], scope: Scope) -> dict[str, Any]:
    """The arguments to run with. Raises `OutOfScopeError` when they name another portfolio."""
    out = dict(arguments)
    if scope.portfolio_id is None or not takes_portfolio(spec):
        return out
    wanted = out.get(SCOPE_ARGUMENT)
    if wanted is not None and str(wanted).lower() != str(scope.portfolio_id).lower():
        raise OutOfScopeError(spec.name)
    out[SCOPE_ARGUMENT] = str(scope.portfolio_id)
    return out
