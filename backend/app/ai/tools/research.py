"""Research tool (P12-T05): the public research evidence about an instrument, for the assistant to
cite. Every item carries its source, licence status and times; the model may quote only what is
returned, never fetch the source URL, and says "none" when there is nothing."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.ai.tools.base import Tool, ToolArguments, ToolContext, ToolData
from app.ai.tools.registry import ToolRegistry
from app.core.authz import ResourceNotFoundError
from app.core.config import get_settings
from app.modules.assets.service import AssetService
from app.modules.research.embedding import build_embedder
from app.modules.research.service import ResearchService


class AssetResearchArguments(ToolArguments):
    asset_id: uuid.UUID = Field(description="An instrument the user can see")


class EvidenceItem(BaseModel):
    title: str
    summary: str
    source: str
    source_url: str | None
    licence_status: str
    is_demo: bool
    published_at: datetime
    retrieved_at: datetime


class AssetResearchResult(ToolData):
    asset_id: uuid.UUID
    items: list[EvidenceItem]
    none: bool = Field(description="True when there is no research for this instrument")


async def get_asset_research(ctx: ToolContext, args: AssetResearchArguments) -> AssetResearchResult:
    if not await AssetService(ctx.session).is_visible(ctx.user_id, args.asset_id):
        raise ResourceNotFoundError("asset")
    service = ResearchService(ctx.session, build_embedder(get_settings().research_embedder))
    found = await service.for_asset(args.asset_id)
    items = [
        EvidenceItem(
            title=e.title,
            summary=e.summary,
            source=e.source,
            source_url=e.source_url,
            licence_status=e.licence_status,
            is_demo=e.is_demo,
            published_at=e.published_at,
            retrieved_at=e.retrieved_at,
        )
        for e in found
    ]
    newest = max((e.published_at for e in found), default=ctx.now())
    return AssetResearchResult(as_of=newest, asset_id=args.asset_id, items=items, none=not items)


def register_research_tools(registry: ToolRegistry) -> None:
    registry.register(
        Tool(
            "get_asset_research",
            "Stored research evidence about one instrument (newest first), each with source, "
            "licence status and dates; DEMO items are fictional. Quote only what is returned and "
            "never fetch a source URL; say there is none when `none` is true.",
            AssetResearchArguments,
            AssetResearchResult,
            get_asset_research,
        )
    )
