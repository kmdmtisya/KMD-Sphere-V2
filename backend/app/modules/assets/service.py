"""Asset use cases: classes, search, detail and user-defined assets."""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, AuditWriter
from app.core.authz import require_found
from app.core.errors import InvalidValueError
from app.modules.assets.catalogue import MetadataError, validate_metadata
from app.modules.assets.models import Asset, AssetClass
from app.modules.assets.repository import AssetRepository
from app.modules.assets.schemas import (
    AssetClassOut,
    AssetCreate,
    AssetOut,
    AssetSearchResult,
    AssetSummary,
    MetadataField,
)

MAX_RESULTS = 50


class AssetService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AssetRepository(session)
        self._audit = AuditWriter(session)

    async def classes(self) -> list[AssetClassOut]:
        return [
            AssetClassOut(
                code=c.code,
                name=c.name,
                valuation_mode=c.valuation_mode,
                metadata_fields={
                    key: MetadataField.model_validate(spec)
                    for key, spec in c.metadata_schema.get("fields", {}).items()
                },
            )
            for c in await self._repo.list_classes()
        ]

    async def search(
        self, user_id: uuid.UUID, query: str, class_code: str | None, limit: int
    ) -> AssetSearchResult:
        rows = await self._repo.search(user_id, query, class_code, min(limit, MAX_RESULTS))
        return AssetSearchResult(items=[_summary(a, c, user_id) for a, c in rows])

    async def get(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> AssetOut:
        asset, asset_class = require_found(await self._repo.get_visible(user_id, asset_id), "asset")
        return await self._detail(asset, asset_class, user_id)

    async def is_visible(self, user_id: uuid.UUID, asset_id: uuid.UUID) -> bool:
        """Whether the user may use this asset (an active catalogue asset or one of theirs)."""
        return await self._repo.get_visible(user_id, asset_id) is not None

    async def create(self, user_id: uuid.UUID, body: AssetCreate) -> AssetOut:
        asset_class = await self._repo.class_by_code(body.asset_class)
        if asset_class is None:
            raise InvalidValueError(f"unknown asset class: {body.asset_class}")
        try:
            metadata = validate_metadata(asset_class.metadata_schema, body.metadata)
        except MetadataError as e:
            raise InvalidValueError(str(e)) from e
        fields: dict[str, Any] = {
            "name": body.name.strip(),
            "currency": body.currency,
            "symbol": body.symbol,
            "subtype": body.subtype,
            "country": body.country,
        }
        asset = await self._repo.add_user_asset(user_id, asset_class, fields, metadata)
        await self._audit.record(
            "assets.asset.created",
            Actor.user(user_id),
            resource_type="asset",
            resource_id=asset.id,
            details={"asset_class": asset_class.code, "fields": sorted(metadata)},
        )
        await self._session.commit()
        return await self._detail(asset, asset_class, user_id)

    async def _detail(self, asset: Asset, asset_class: AssetClass, user_id: uuid.UUID) -> AssetOut:
        summary = _summary(asset, asset_class, user_id)
        return AssetOut(
            **summary.model_dump(),
            asset_class_name=asset_class.name,
            valuation_mode=asset_class.valuation_mode,
            metadata=await self._repo.metadata(asset.id),
        )


def _summary(asset: Asset, asset_class: AssetClass, user_id: uuid.UUID) -> AssetSummary:
    return AssetSummary(
        id=asset.id,
        asset_class=asset_class.code,
        symbol=asset.symbol,
        name=asset.name,
        subtype=asset.subtype,
        currency=asset.currency,
        country=asset.country,
        is_custom=asset.owner_user_id == user_id,
    )
