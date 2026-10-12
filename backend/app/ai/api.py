"""/api/v1/ai: the assistant's chat (server-sent events) and the user's stored conversations
(P10-T06). The model never sees who is asking: identity comes from the access token, and every
data access goes through an allow-listed tool (docs/ai-governance.md)."""

import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.conversations.service import ConversationService
from app.ai.orchestrator.events import EVENT_TYPES, to_sse
from app.ai.orchestrator.orchestrator import Orchestrator
from app.ai.orchestrator.policy import MinimalPolicy
from app.ai.providers.base import LlmProvider
from app.ai.providers.errors import LlmNotConfigured
from app.ai.providers.registry import build_llm
from app.ai.schemas import (
    ChatRequest,
    ConversationDetailOut,
    ConversationOut,
    MessageOut,
    ToolCallOut,
)
from app.ai.tools.factory import build_tool_registry
from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.core.config import Settings
from app.core.correlation import get_correlation_id
from app.core.errors import problem
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]

CHAT_DESCRIPTION = (
    "Ask the assistant about your own portfolio, goals and net worth. The answer streams as "
    f"server-sent events of these types: {', '.join(EVENT_TYPES)}. `tool` shows which tool ran "
    "(name and status only), `source` names the data the answer rests on with its as-of time, "
    "`token` carries the answer text (the answer is checked before any of it is sent), `done` "
    "closes the turn and `error` ends it with a fixed code. Figures come from WealthSphere's "
    "tools, never from the model. Limits: 30 questions per user per 24 hours, 20 tool calls per "
    "question."
)


def _runtime(request: Request) -> Orchestrator | None:
    """The orchestrator for this app, or None when no model is configured."""
    state = request.app.state
    cached: Orchestrator | None = getattr(state, "ai_orchestrator", None)
    if cached is not None:
        return cached
    settings: Settings = state.settings
    llm: LlmProvider | None = getattr(state, "llm", None)
    if llm is None:
        if settings.ai_provider == "fake":
            return None  # the fake provider is for tests, which inject their own
        try:
            llm = build_llm(settings)
        except LlmNotConfigured:
            return None
    orchestrator = Orchestrator(llm, build_tool_registry(settings), settings, MinimalPolicy())
    state.ai_orchestrator = orchestrator
    return orchestrator


@router.post(
    "/chat",
    summary="Ask the assistant",
    description=CHAT_DESCRIPTION,
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "A stream of server-sent events",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        **UNAUTHORIZED,
        **not_found("conversation or portfolio"),
        **invalid("question"),
        503: {"description": "No assistant is configured"},
    },
)
async def chat(
    body: ChatRequest, request: Request, user: CurrentUserDep, session: SessionDep
) -> Response:
    orchestrator = _runtime(request)
    if orchestrator is None:
        return problem(
            request,
            503,
            "ai-unavailable",
            "Assistant unavailable",
            "The assistant is not available right now.",
        )
    turn = await orchestrator.prepare(
        session,
        user.id,
        body.message,
        body.conversation_id,
        body.scope.portfolio_id if body.scope else None,
        get_correlation_id(),
    )
    sessions = request.app.state.db.session_factory

    async def stream() -> AsyncIterator[str]:
        async for event in orchestrator.answer(sessions, turn):
            yield to_sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/conversations",
    response_model=list[ConversationOut],
    summary="Your conversations",
    responses=UNAUTHORIZED,
)
async def list_conversations(
    user: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[ConversationOut]:
    """Your stored conversations, most recent first. Conversations are deleted after the
    retention period (90 days by default) or when you delete them."""
    rows = await ConversationService(session).recent(user.id, limit, offset)
    return [
        ConversationOut(
            id=c.id,
            title=c.title,
            portfolio_id=c.portfolio_id,
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in rows
    ]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetailOut,
    summary="One conversation with its messages",
    responses={**UNAUTHORIZED, **not_found("conversation")},
)
async def get_conversation(
    conversation_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> ConversationDetailOut:
    """The conversation with its messages in order and the tools that ran (name and status)."""
    service = ConversationService(session)
    c = await service.get(user.id, conversation_id)
    messages = await service.messages(user.id, c.id)
    calls = await service.tool_calls(user.id, c.id)
    return ConversationDetailOut(
        id=c.id,
        title=c.title,
        portfolio_id=c.portfolio_id,
        created_at=c.created_at,
        updated_at=c.updated_at,
        messages=[
            MessageOut(
                id=m.id,
                position=m.position,
                role=m.role,
                content=m.content,
                structured=m.structured,
                model=m.model,
                created_at=m.created_at,
            )
            for m in messages
        ],
        tool_calls=[
            ToolCallOut(
                tool_name=t.tool_name,
                status=t.status,
                error_code=t.error_code,
                message_id=t.message_id,
            )
            for t in calls
        ],
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    summary="Delete one conversation",
    responses={**UNAUTHORIZED, **not_found("conversation")},
)
async def delete_conversation(
    conversation_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> Response:
    """Deletes the conversation with its messages and tool-call records."""
    await ConversationService(session).delete(user.id, conversation_id)
    await session.commit()
    return Response(status_code=204)


@router.delete(
    "/conversations",
    status_code=204,
    summary="Delete all your conversations",
    responses=UNAUTHORIZED,
)
async def delete_all_conversations(user: CurrentUserDep, session: SessionDep) -> Response:
    """Deletes every conversation you have, with its messages and tool-call records."""
    await ConversationService(session).delete_all(user.id)
    await session.commit()
    return Response(status_code=204)
