"""What a tool is, and what the model may see of one (P10-T02).

A tool is a small, read-only function over an existing authorised service. The model supplies
arguments; it never supplies who is asking. That comes from the `ToolContext`, which only the
orchestrator can build (from the authenticated request).
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

# The complete allow-list (docs/ai-governance.md section 1). tests/ai/test_tool_allow_list.py
# keeps this, the document and the registry identical.
ALLOWED_TOOLS: frozenset[str] = frozenset(
    {
        "get_portfolio_summary",
        "get_portfolio_allocation",
        "get_portfolio_performance",
        "get_net_worth",
        "get_goal_progress",
        "run_compound_forecast",
        "run_goal_forecast",
        "get_market_snapshot",
        "search_investment_universe",
        "get_asset_research",
        "compare_assets",
        "run_portfolio_risk_analysis",
    }
)


@dataclass(frozen=True)
class ToolContext:
    """Who is asking, and how to read their data. Built by the orchestrator, never by the model."""

    user_id: uuid.UUID
    session: AsyncSession
    correlation_id: str | None = None
    # Recorded in the audit event of every call (docs/ai-governance.md).
    model: str | None = None
    provider: str | None = None
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))


class ToolArguments(BaseModel):
    """Base of every tool's arguments: unknown fields are refused, so the model cannot smuggle in
    a `user_id` or anything else the tool did not declare."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ToolData(BaseModel):
    """Base of every tool's result: structured, with the time the data applies and whether it is
    complete (docs/ai-governance.md section 1)."""

    model_config = ConfigDict(extra="forbid")

    as_of: datetime
    complete: bool = True

    @field_validator("as_of")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        """Always carries a time zone. A few services report a day as midnight without a zone:
        those are UTC days, so that is what is stated."""
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


Handler = Callable[[ToolContext, Any], Awaitable[ToolData]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    arguments: type[ToolArguments]
    result: type[ToolData]
    handler: Handler
    timeout_seconds: float | None = None  # None: the configured default


@dataclass(frozen=True)
class ToolSpec:
    """What the model is told about a tool: its name, purpose and argument schema. Nothing else."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolOutcome:
    """The result of one call, as the orchestrator and the model see it. Never carries an
    exception or its text: `error` is a short code and a fixed, safe message."""

    tool: str
    ok: bool
    data: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None

    def for_model(self) -> dict[str, Any]:
        if self.ok:
            return {"tool": self.tool, "ok": True, "data": self.data}
        return {
            "tool": self.tool,
            "ok": False,
            "error": {"code": self.error_code, "message": self.error_message},
        }


class ToolRefusedError(Exception):
    """A call that must not run (unknown tool, no user context, over budget). `code` is stable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message
