"""GET /api/v1/research (P12-T05): search public research evidence, or list an instrument's.
Retrieval is user-agnostic: sign-in is required, but no user data is read and every user gets the
same answer. Source URLs are provenance for the user to open; the app never fetches them."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid
from app.core.config import Settings
from app.core.errors import InvalidValueError
from app.core.money import DecimalString
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep
from app.modules.research.embedding import build_embedder
from app.modules.research.service import Evidence, ResearchService

router = APIRouter(prefix="/api/v1/research", tags=["research"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
NOTICE = (
    "Research is information, not advice. DEMO items are fictional. Check each item's source, "
    "licence status and date."
)


class EvidenceOut(BaseModel):
    id: uuid.UUID
    title: str
    summary: str
    kind: str
    source: str
    source_url: str | None = Field(description="Where the source publishes it (provenance)")
    licence_status: Literal["demo", "public_domain", "unconfirmed", "licensed"]
    is_demo: bool
    published_at: datetime = Field(description="The source's time (as-of)")
    retrieved_at: datetime = Field(description="When WealthSphere obtained it")
    asset_id: uuid.UUID | None
    symbol: str | None
    relevance: DecimalString | None = Field(
        description="0 to 1 for a search: the mean of embedding similarity and text rank"
    )


class ResearchOut(BaseModel):
    items: list[EvidenceOut]
    notice: str = NOTICE


def evidence_out(e: Evidence) -> EvidenceOut:
    return EvidenceOut(
        id=e.id,
        title=e.title,
        summary=e.summary,
        kind=e.kind,
        source=e.source,
        source_url=e.source_url,
        licence_status=e.licence_status,
        is_demo=e.is_demo,
        published_at=e.published_at,
        retrieved_at=e.retrieved_at,
        asset_id=e.asset_id,
        symbol=e.symbol,
        relevance=e.relevance,
    )


@router.get(
    "",
    response_model=ResearchOut,
    summary="Search research evidence",
    responses={**UNAUTHORIZED, **invalid("query")},
)
async def research(
    request: Request,
    user: CurrentUserDep,
    session: SessionDep,
    q: Annotated[str | None, Query(min_length=2, max_length=200, description="Search text")] = None,
    asset_id: Annotated[
        uuid.UUID | None, Query(description="Only research about this instrument")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> ResearchOut:
    """With `q`: the most relevant items (embedding similarity and full-text rank), optionally for
    one instrument. Without `q`: an instrument's research, newest first (`asset_id` required).
    Every item carries its source, licence status and times."""
    settings: Settings = request.app.state.settings
    service = ResearchService(session, build_embedder(settings.research_embedder))
    if q is not None:
        items = await service.search(q, asset_id, limit)
    elif asset_id is not None:
        items = await service.for_asset(asset_id, limit)
    else:
        raise InvalidValueError("Give a search text (q) or an instrument (asset_id).")
    return ResearchOut(items=[evidence_out(e) for e in items])
