"""The tool registry and the one place a tool call is executed (P10-T02).

`ToolRegistry.execute` is the only door. For every call it:

1. refuses a call with no user context;
2. refuses an unknown tool (and audits the attempt);
3. checks the per-user call budget;
4. validates the arguments with the tool's Pydantic model (unknown fields are refused);
5. runs the handler with a timeout;
6. checks the result against the tool's result model and the size limit;
7. writes one audit event: tool, the AI actor on behalf of the user, a hash of the arguments (not
   the arguments), status, model and provider, duration and correlation id.

Whatever goes wrong, the model gets a short code and a fixed message, never an exception text or a
stack trace. A foreign or missing resource answers "not_found", exactly as the API does.
"""

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from app.ai.tools.base import (
    ALLOWED_TOOLS,
    Tool,
    ToolContext,
    ToolOutcome,
    ToolRefusedError,
    ToolSpec,
)
from app.core.audit import Actor, AuditWriter, Outcome, hash_arguments
from app.core.authz import ResourceNotFoundError
from app.core.correlation import correlation_id_var
from app.core.errors import InvalidValueError

logger = logging.getLogger(__name__)

AUDIT_ACTION = "ai.tool.call"

_MESSAGES = {
    "no_user_context": "This tool needs a signed-in user.",
    "unknown_tool": "There is no such tool.",
    "rate_limited": "Too many tool calls. Try again shortly.",
    "invalid_arguments": "The arguments are not valid for this tool.",
    "not_found": "Not found.",
    "invalid": "The request is not valid.",
    "timeout": "The tool took too long.",
    "too_large": "The result is too large to return.",
    "internal": "The tool could not complete.",
}


def _failure(tool: str, code: str) -> ToolOutcome:
    return ToolOutcome(tool, ok=False, error_code=code, error_message=_MESSAGES[code])


class CallBudget:
    """At most `limit` calls per user per minute. Per process (a multi-process deployment keeps
    one budget per worker, so the effective ceiling is higher but still bounded)."""

    def __init__(self, limit: int, clock: Any = time.monotonic) -> None:
        self._limit = limit
        self._clock = clock
        self._calls: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = float(self._clock())
        window = self._calls.setdefault(key, deque())
        while window and now - window[0] >= 60:
            window.popleft()
        if len(window) >= self._limit:
            return False
        window.append(now)
        return True


class ToolRegistry:
    def __init__(
        self,
        *,
        calls_per_minute: int = 60,
        default_timeout_seconds: float = 10.0,
        max_result_bytes: int = 32_768,
        clock: Any = time.monotonic,
    ) -> None:
        self._tools: dict[str, Tool] = {}
        self._budget = CallBudget(calls_per_minute, clock)
        self._timeout = default_timeout_seconds
        self._max_bytes = max_result_bytes

    # ---------------------------------------------------------------------- registration
    def register(self, tool: Tool) -> None:
        if tool.name not in ALLOWED_TOOLS:
            raise ValueError(f"{tool.name!r} is not on the AI tool allow-list")
        if tool.name in self._tools:
            raise ValueError(f"{tool.name!r} is already registered")
        self._tools[tool.name] = tool

    @property
    def names(self) -> frozenset[str]:
        return frozenset(self._tools)

    def specs(self) -> list[ToolSpec]:
        """What the model is told. Argument schemas never contain a user id: tools do not take
        one."""
        return [
            ToolSpec(t.name, t.description, t.arguments.model_json_schema())
            for t in sorted(self._tools.values(), key=lambda t: t.name)
        ]

    # ------------------------------------------------------------------------ execution
    async def execute(
        self,
        name: str,
        raw_arguments: Mapping[str, Any] | None,
        context: ToolContext | None,
    ) -> ToolOutcome:
        if context is None:
            # Nobody to audit it against: refuse (the orchestrator logs the bug).
            logger.error("tool call %r without a user context", name)
            return _failure(name, "no_user_context")
        started = time.monotonic()
        arguments = dict(raw_arguments or {})
        outcome = await self._run(name, arguments, context)
        await self._audit(name, arguments, context, outcome, time.monotonic() - started)
        return outcome

    async def _run(self, name: str, arguments: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
        tool = self._tools.get(name)
        if tool is None:
            return _failure(name, "unknown_tool")
        if not self._budget.allow(str(ctx.user_id)):
            return _failure(name, "rate_limited")
        try:
            parsed = tool.arguments.model_validate(arguments)
        except ValidationError:
            return _failure(name, "invalid_arguments")
        try:
            result = await asyncio.wait_for(
                tool.handler(ctx, parsed), timeout=tool.timeout_seconds or self._timeout
            )
            checked = tool.result.model_validate(result.model_dump())
        except TimeoutError:
            await ctx.session.rollback()
            return _failure(name, "timeout")
        except ResourceNotFoundError:
            await ctx.session.rollback()
            return _failure(name, "not_found")
        except (InvalidValueError, ToolRefusedError):
            await ctx.session.rollback()
            return _failure(name, "invalid")
        except Exception:
            # Never return exception text to the model: it could carry data or internals.
            logger.exception("tool %s failed", name)
            await ctx.session.rollback()
            return _failure(name, "internal")
        data = json.loads(checked.model_dump_json())
        if len(json.dumps(data, separators=(",", ":"))) > self._max_bytes:
            return _failure(name, "too_large")
        return ToolOutcome(name, ok=True, data=data)

    async def _audit(
        self,
        name: str,
        arguments: dict[str, Any],
        ctx: ToolContext,
        outcome: ToolOutcome,
        seconds: float,
    ) -> None:
        # The audit row takes its correlation id from the request context; the orchestrator's
        # context carries the same id when the call runs outside the request task.
        token = correlation_id_var.set(ctx.correlation_id) if ctx.correlation_id else None
        status = "ok" if outcome.ok else (outcome.error_code or "error")
        denied = status in ("unknown_tool", "not_found", "rate_limited", "invalid_arguments")
        try:
            await AuditWriter(ctx.session).record(
                AUDIT_ACTION,
                Actor.ai(ctx.user_id),
                resource_type="ai_tool",
                resource_id=name if len(name) <= 100 else name[:100],
                outcome=Outcome.SUCCESS
                if outcome.ok
                else (Outcome.DENIED if denied else Outcome.FAILURE),
                details={
                    "tool": name[:100],
                    "arguments_hash": hash_arguments(arguments),
                    "status": status,
                    "model": ctx.model,
                    "provider": ctx.provider,
                    "duration_ms": round(seconds * 1000),
                    "correlation_id": ctx.correlation_id,
                },
            )
            await ctx.session.commit()
        except Exception:
            # An audit that cannot be written must not hand the model a result unaudited.
            logger.exception("could not audit tool call")
            await ctx.session.rollback()
            raise
        finally:
            if token is not None:
                correlation_id_var.reset(token)
