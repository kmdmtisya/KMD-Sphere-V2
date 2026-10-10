"""Asset queries. Every read of assets goes through `visible_to`: the global catalogue plus the
caller's own user-defined assets, never another user's (ADR-0011)."""

import uuid
from typing import Any

from sqlalchemy import ColumnElement, Select, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assets.models import Asset, AssetClass, AssetMetadata


def visible_to(user_id: uuid.UUID) -> ColumnElement[bool]:
    return or_(Asset.owner_user_id.is_(None), Asset.owner_user_id == user_id)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class AssetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_classes(self) -> list[AssetClass]:
        result = await self._session.execute(
            select(AssetClass).where(AssetClass.is_active).order_by(AssetClass.name)
        )
        return list(result.scalars())

    async def class_by_code(self, code: str) -> AssetClass | None:
        result = await self._session.execute(
            select(AssetClass).where(AssetClass.code == code, AssetClass.is_active)
        )
        return result.scalar_one_or_none()

    def _visible(self, user_id: uuid.UUID) -> Select[Asset, AssetClass]:
        return (
            select(Asset, AssetClass)
            .join(AssetClass, Asset.asset_class_id == AssetClass.id)
            .where(visible_to(user_id), Asset.is_active)
        )

    async def search(
        self, user_id: uuid.UUID, query: str, class_code: str | None, limit: int
    ) -> list[tuple[Asset, AssetClass]]:
        """Symbol or name match, best first: exact symbol, symbol prefix, then name; ties by name
        and id so the order is deterministic."""
        stmt = self._visible(user_id)
        q = query.strip()
        if q:
            pattern = f"%{_escape_like(q)}%"
            prefix = f"{_escape_like(q)}%"
            stmt = stmt.where(
                or_(
                    Asset.symbol.ilike(pattern, escape="\\"),
                    Asset.name.ilike(pattern, escape="\\"),
                )
            ).order_by(
                case(
                    (func.upper(Asset.symbol) == q.upper(), 0),
                    (Asset.symbol.ilike(prefix, escape="\\"), 1),
                    (Asset.name.ilike(prefix, escape="\\"), 2),
                    else_=3,
                )
            )
        if class_code:
            stmt = stmt.where(AssetClass.code == class_code)
        stmt = stmt.order_by(Asset.name, Asset.id).limit(limit)
        result = await self._session.execute(stmt)
        return [(asset, cls) for asset, cls in result.all()]

    async def get_visible(
        self, user_id: uuid.UUID, asset_id: uuid.UUID
    ) -> tuple[Asset, AssetClass] | None:
        result = await self._session.execute(self._visible(user_id).where(Asset.id == asset_id))
        row = result.first()
        return (row[0], row[1]) if row else None

    async def metadata(self, asset_id: uuid.UUID) -> dict[str, Any]:
        result = await self._session.execute(
            select(AssetMetadata.key, AssetMetadata.value)
            .where(AssetMetadata.asset_id == asset_id)
            .order_by(AssetMetadata.key)
        )
        return {key: value for key, value in result.all()}  # noqa: C416 (Row to tuple)

    async def add_user_asset(
        self,
        owner_id: uuid.UUID,
        asset_class: AssetClass,
        fields: dict[str, Any],
        metadata: dict[str, Any],
    ) -> Asset:
        asset = Asset(owner_user_id=owner_id, asset_class_id=asset_class.id, **fields)
        self._session.add(asset)
        await self._session.flush()
        for key, value in metadata.items():
            self._session.add(AssetMetadata(asset_id=asset.id, key=key, value=value, source="user"))
        await self._session.flush()
        await self._session.refresh(asset)
        return asset
