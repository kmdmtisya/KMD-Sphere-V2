"""/api/v1/assets and /api/v1/asset-classes."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, invalid, not_found
from app.db.session import get_session
from app.modules.assets.schemas import AssetClassOut, AssetCreate, AssetOut, AssetSearchResult
from app.modules.assets.service import MAX_RESULTS, AssetService
from app.modules.identity.dependencies import CurrentUserDep

router = APIRouter(prefix="/api/v1/assets", tags=["assets"])
classes_router = APIRouter(prefix="/api/v1/asset-classes", tags=["assets"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@classes_router.get("", response_model=list[AssetClassOut], responses=UNAUTHORIZED)
async def list_asset_classes(user: CurrentUserDep, session: SessionDep) -> list[AssetClassOut]:
    """The asset classes and the metadata each one accepts."""
    return await AssetService(session).classes()


@router.get(
    "/search",
    response_model=AssetSearchResult,
    responses={**UNAUTHORIZED, **invalid("search parameters")},
)
async def search_assets(
    user: CurrentUserDep,
    session: SessionDep,
    q: Annotated[str, Query(max_length=100, description="Symbol or name, any part")] = "",
    asset_class: Annotated[
        str | None, Query(pattern=r"^[a-z][a-z0-9_]{1,39}$", description="Class code filter")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_RESULTS)] = 20,
) -> AssetSearchResult:
    """Searches the global catalogue and the caller's own assets."""
    return await AssetService(session).search(user.id, q, asset_class, limit)


@router.get(
    "/{asset_id}", response_model=AssetOut, responses={**UNAUTHORIZED, **not_found("asset")}
)
async def get_asset(asset_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> AssetOut:
    """A catalogue asset, or one of the caller's own assets, with its metadata."""
    return await AssetService(session).get(user.id, asset_id)


@router.post(
    "",
    response_model=AssetOut,
    status_code=201,
    responses={**UNAUTHORIZED, **invalid("asset")},
)
async def create_asset(body: AssetCreate, user: CurrentUserDep, session: SessionDep) -> AssetOut:
    """Creates a user-defined asset (only the caller sees it)."""
    return await AssetService(session).create(user.id, body)
