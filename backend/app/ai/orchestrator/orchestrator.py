"""The tool-calling loop (P10-T06).

One question: store it, ask the model with the allow-listed tools, run the tools the model asks for
(only through the registry, with the caller's identity and the chat's scope), feed the results back,
repeat within the call and round limits, review the final answer and only then stream it. Nothing
here logs a prompt, an answer or a tool result."""

import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.conversations.models import Message as StoredMessage
from app.ai.conversations.service import ConversationService, RecordedToolCall
from app.ai.orchestrator.events import (
    ERROR_MESSAGES,
    DoneEvent,
    ErrorEvent,
    SourceEvent,
    TokenEvent,
    ToolEvent,
)
from app.ai.orchestrator.policy import AnswerPolicy, Draft, correction_message
from app.ai.orchestrator.prompt import system_prompt
from app.ai.orchestrator.refusal import Refusal, check_question
from app.ai.orchestrator.scope import OutOfScopeError, Scope, apply_scope
from app.ai.providers.base import LlmProvider
from app.ai.providers.errors import LlmError
from app.ai.providers.models import ChatRequest, Message, ToolCall, Usage
from app.ai.tools.base import ToolContext, ToolOutcome, ToolSpec
from app.ai.tools.registry import ToolRegistry
from app.core.audit import Actor, AuditWriter, Outcome, hash_arguments
from app.core.config import Settings
from app.core.errors import InvalidValueError
from app.core.ratelimit import RateLimitedError
from app.modules.portfolio.service import PortfolioService

logger = logging.getLogger(__name__)

AUDIT_ACTION = "ai.chat.answer"
REFUSED_ACTION = "ai.chat.refused"
REJECTED_ACTION = "ai.chat.rejected"
CHUNK_CHARS = 48
DAY = timedelta(hours=24)
TITLE_CHARS = 60

_REFUSALS = {
    "out_of_scope": "This chat is limited to one portfolio.",
    "limit_reached": "The tool-call limit for this question has been reached.",
}
STREAM_EVENT = ToolEvent | SourceEvent | TokenEvent | DoneEvent | ErrorEvent


@dataclass(frozen=True)
class Turn:
    """A question that has been accepted and stored."""

    user_id: uuid.UUID
    conversation_id: uuid.UUID
    scope: Scope
    correlation_id: str | None
    refusal: Refusal | None = None


@dataclass
class _Ran:
    name: str
    arguments: dict[str, Any]
    arguments_hash: str
    outcome: ToolOutcome
    duration_ms: int


def refusal(name: str, code: str) -> ToolOutcome:
    return ToolOutcome(name, ok=False, error_code=code, error_message=_REFUSALS[code])


def chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Pieces of about `size` characters that keep words whole; joined, they equal `text`."""
    out: list[str] = []
    current = ""
    for word in re.findall(r"\S+\s*|\s+", text):
        if current and len(current) + len(word) > size:
            out.append(current)
            current = ""
        current += word
    if current:
        out.append(current)
    return out


class Orchestrator:
    def __init__(
        self,
        llm: LlmProvider,
        registry: ToolRegistry,
        settings: Settings,
        policy: AnswerPolicy,
    ) -> None:
        self._llm = llm
        self._registry = registry
        self._settings = settings
        self._policy = policy

    # ------------------------------------------------------------------- accepting
    async def prepare(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        question: str,
        conversation_id: uuid.UUID | None,
        portfolio_id: uuid.UUID | None,
        correlation_id: str | None,
    ) -> Turn:
        """Checks everything that can be refused with an ordinary HTTP error, then stores the
        question. Raises `ResourceNotFoundError` for a conversation or portfolio that is not the
        caller's, `InvalidValueError` for a scope that contradicts the conversation and
        `RateLimitedError` over the daily limit."""
        conversations = ConversationService(session)
        if conversation_id is None:
            if portfolio_id is not None:
                await PortfolioService(session).get(user_id, portfolio_id)  # 404 if not theirs
            scope_id = portfolio_id
        else:
            existing = await conversations.get(user_id, conversation_id)
            if portfolio_id is not None and portfolio_id != existing.portfolio_id:
                raise InvalidValueError("The scope of an existing conversation cannot change.")
            scope_id = existing.portfolio_id
        await self._check_daily_limit(session, user_id)
        if conversation_id is None:
            created = await conversations.create(user_id, question[:TITLE_CHARS], scope_id)
            conversation_id = created.id
        await conversations.append(user_id, conversation_id, "user", question)
        await session.commit()
        return Turn(
            user_id, conversation_id, Scope(scope_id), correlation_id, check_question(question)
        )

    async def _check_daily_limit(self, session: AsyncSession, user_id: uuid.UUID) -> None:
        since = datetime.now(UTC) - DAY
        count, oldest = (
            await session.execute(
                select(func.count(), func.min(StoredMessage.created_at)).where(
                    StoredMessage.user_id == user_id,
                    StoredMessage.role == "user",
                    StoredMessage.created_at > since,
                )
            )
        ).one()
        if count >= self._settings.ai_questions_per_day and oldest is not None:
            wait = int((oldest + DAY - datetime.now(UTC)).total_seconds())
            raise RateLimitedError(max(wait, 1))

    # -------------------------------------------------------------------- answering
    async def answer(
        self, sessions: async_sessionmaker[AsyncSession], turn: Turn
    ) -> AsyncIterator[STREAM_EVENT]:
        async with sessions() as session:
            async for event in self._answer(session, turn):
                yield event

    async def _answer(self, session: AsyncSession, turn: Turn) -> AsyncIterator[STREAM_EVENT]:
        settings = self._settings
        conversations = ConversationService(session)
        if turn.refusal is not None:
            async for event in self._refuse(session, conversations, turn, turn.refusal):
                yield event
            return
        history = await conversations.messages(
            turn.user_id, turn.conversation_id, limit=max(settings.ai_history_messages, 1)
        )
        messages: list[Message] = [
            Message("system", system_prompt(datetime.now(UTC).date(), turn.scope.portfolio_id))
        ]
        messages += [self._as_message(m) for m in history]
        user_texts = tuple(m.content for m in history if m.role == "user")
        context = ToolContext(
            turn.user_id, session, turn.correlation_id, self._llm.model, self._llm.name
        )
        specs = {s.name: s for s in self._registry.specs()}
        ran: list[_Ran] = []
        usage = Usage()
        provider, model = self._llm.name, self._llm.model
        final = ""

        for round_number in range(settings.ai_max_model_rounds):
            # On the last round, or once the call budget is spent, the model must answer.
            exhausted = len(ran) >= settings.ai_max_tool_calls_per_question
            last_round = round_number == settings.ai_max_model_rounds - 1
            offered = () if exhausted or last_round else tuple(specs.values())
            try:
                response = await self._llm.complete(
                    ChatRequest(tuple(messages), offered, settings.ai_max_output_tokens)
                )
            except LlmError as error:
                logger.warning("llm failed: %s", type(error).__name__)
                yield self._error("ai_unavailable")
                return
            provider, model = response.provider or provider, response.model or model
            usage = Usage(
                usage.input_tokens + response.usage.input_tokens,
                usage.output_tokens + response.usage.output_tokens,
            )
            if not response.tool_calls or not offered:
                final = response.content
                break
            messages.append(Message("assistant", response.content, response.tool_calls))
            for call in response.tool_calls:
                async for event in self._run_tool(call, specs, context, turn, ran, messages):
                    yield event
        else:  # pragma: no cover - the last round offers no tools, so the loop always breaks
            yield self._error("invalid_answer")
            return

        retries = 0
        while True:
            verdict = self._policy.review(
                Draft(
                    final,
                    tuple(r.outcome for r in ran),
                    tuple(r.arguments for r in ran),
                    user_texts,
                )
            )
            if verdict.text is not None:
                break
            if retries >= settings.ai_max_answer_retries:
                await self._audit_rejected(
                    session, turn, verdict.problems, retries, model, provider
                )
                yield self._error("invalid_answer")
                return
            retries += 1
            messages += [
                Message("assistant", final),
                Message("user", correction_message(verdict.problems)),
            ]
            try:
                response = await self._llm.complete(
                    ChatRequest(tuple(messages), (), settings.ai_max_output_tokens)
                )
            except LlmError as error:
                logger.warning("llm failed: %s", type(error).__name__)
                yield self._error("ai_unavailable")
                return
            usage = Usage(
                usage.input_tokens + response.usage.input_tokens,
                usage.output_tokens + response.usage.output_tokens,
            )
            final = response.content

        for tool in dict.fromkeys(r.name for r in ran if r.outcome.ok):
            data = next(r.outcome.data for r in ran if r.name == tool and r.outcome.ok)
            as_of = (data or {}).get("as_of")
            yield SourceEvent(
                tool=tool,
                as_of=datetime.fromisoformat(as_of) if isinstance(as_of, str) else None,
                complete=bool((data or {}).get("complete", True)),
            )
        for piece in chunks(verdict.text):
            yield TokenEvent(text=piece)

        stored = await conversations.append(
            turn.user_id,
            turn.conversation_id,
            "assistant",
            verdict.text,
            structured=verdict.structured,
            model=model,
            provider=provider,
        )
        for r in ran:
            await conversations.record_tool_call(
                turn.user_id,
                turn.conversation_id,
                RecordedToolCall(
                    r.name,
                    r.arguments_hash,
                    r.outcome.ok,
                    r.outcome.error_code,
                    r.duration_ms,
                    turn.correlation_id,
                ),
                stored.id,
            )
        await AuditWriter(session).record(
            AUDIT_ACTION,
            Actor.ai(turn.user_id),
            resource_type="ai_conversation",
            resource_id=turn.conversation_id,
            outcome=Outcome.SUCCESS,
            details={
                "model": model,
                "provider": provider,
                "tool_calls": len(ran),
                "retries": retries,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "correlation_id": turn.correlation_id,
            },
        )
        await session.commit()
        yield DoneEvent(
            conversation_id=turn.conversation_id,
            message_id=stored.id,
            model=model,
            provider=provider,
            tool_calls=len(ran),
            structured=verdict.structured,
        )

    async def _run_tool(
        self,
        call: ToolCall,
        specs: dict[str, ToolSpec],
        context: ToolContext,
        turn: Turn,
        ran: list[_Ran],
        messages: list[Message],
    ) -> AsyncIterator[ToolEvent]:
        yield ToolEvent(name=call.name[:64], status="running")
        started = time.monotonic()
        arguments = dict(call.arguments)
        if len(ran) >= self._settings.ai_max_tool_calls_per_question:
            outcome = refusal(call.name, "limit_reached")
        else:
            spec = specs.get(call.name)
            try:
                if spec is not None:
                    arguments = apply_scope(spec, arguments, turn.scope)
                outcome = await self._registry.execute(call.name, arguments, context)
            except OutOfScopeError:
                outcome = refusal(call.name, "out_of_scope")
        ran.append(
            _Ran(
                call.name[:64],
                arguments,
                hash_arguments(arguments),
                outcome,
                round((time.monotonic() - started) * 1000),
            )
        )
        messages.append(
            Message("tool", json.dumps(outcome.for_model(), default=str), tool_call_id=call.id)
        )
        yield ToolEvent(
            name=call.name[:64],
            status="ok" if outcome.ok else "error",
            error_code=outcome.error_code,
        )

    @staticmethod
    def _as_message(stored: StoredMessage) -> Message:
        """Earlier turns as the model should see them: its own answers in the JSON shape it was
        asked for (without the server's caveats), not the rendered text."""
        if stored.role == "user":
            return Message("user", stored.content)
        if stored.structured and "refusal" not in stored.structured:
            shown = {k: v for k, v in stored.structured.items() if k != "caveats"}
            return Message("assistant", json.dumps(shown))
        return Message("assistant", stored.content)

    async def _refuse(
        self,
        session: AsyncSession,
        conversations: ConversationService,
        turn: Turn,
        refusal: Refusal,
    ) -> AsyncIterator[STREAM_EVENT]:
        """Answers a request the product declines without asking the model."""
        for piece in chunks(refusal.message):
            yield TokenEvent(text=piece)
        stored = await conversations.append(
            turn.user_id,
            turn.conversation_id,
            "assistant",
            refusal.message,
            structured={"refusal": refusal.category},
        )
        await AuditWriter(session).record(
            REFUSED_ACTION,
            Actor.ai(turn.user_id),
            resource_type="ai_conversation",
            resource_id=turn.conversation_id,
            outcome=Outcome.DENIED,
            details={"category": refusal.category, "correlation_id": turn.correlation_id},
        )
        await session.commit()
        yield DoneEvent(
            conversation_id=turn.conversation_id,
            message_id=stored.id,
            model=self._llm.model,
            provider=self._llm.name,
            tool_calls=0,
            structured=stored.structured,
        )

    @staticmethod
    async def _audit_rejected(
        session: AsyncSession,
        turn: Turn,
        problems: tuple[str, ...],
        retries: int,
        model: str,
        provider: str,
    ) -> None:
        await AuditWriter(session).record(
            REJECTED_ACTION,
            Actor.ai(turn.user_id),
            resource_type="ai_conversation",
            resource_id=turn.conversation_id,
            outcome=Outcome.FAILURE,
            details={
                "problems": list(problems),
                "retries": retries,
                "model": model,
                "provider": provider,
                "correlation_id": turn.correlation_id,
            },
        )
        await session.commit()

    @staticmethod
    def _error(code: str) -> ErrorEvent:
        return ErrorEvent(code=code, message=ERROR_MESSAGES[code])
