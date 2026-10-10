"""Data access for identity. Provisioning is idempotent and safe under concurrent first requests."""

import uuid
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authz import owned_by
from app.modules.identity.models import RiskProfile, User, UserProfile


class IdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_user(self, issuer: str, subject: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.issuer == issuer, User.subject == subject)
        )
        return result.scalar_one_or_none()

    async def upsert_user(
        self, issuer: str, subject: str, email: str | None, email_verified: bool
    ) -> uuid.UUID:
        """Inserts the user, or refreshes email and last-seen if it exists. Returns its id.

        ON CONFLICT makes concurrent first requests for the same user safe: one insert wins and
        the others update the same row."""
        stmt = (
            insert(User)
            .values(
                issuer=issuer,
                subject=subject,
                email=email,
                email_verified=email_verified,
                last_seen_at=text("now()"),
            )
            .on_conflict_do_update(
                constraint="uq_users_issuer_subject",
                set_={
                    "email": email,
                    "email_verified": email_verified,
                    "last_seen_at": text("now()"),
                    "updated_at": text("now()"),
                },
            )
            .returning(User.id)
        )
        user_id: uuid.UUID = (await self._session.execute(stmt)).scalar_one()
        await self._session.execute(
            insert(UserProfile).values(user_id=user_id).on_conflict_do_nothing()
        )
        return user_id

    async def touch(self, user_id: uuid.UUID) -> None:
        await self._session.execute(
            update(User).where(User.id == user_id).values(last_seen_at=text("now()"))
        )

    async def get_user(self, user_id: uuid.UUID) -> User:
        result = await self._session.execute(
            select(User).where(User.id == user_id).execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def get_profile(self, user_id: uuid.UUID) -> UserProfile:
        result = await self._session.execute(
            select(UserProfile)
            .where(UserProfile.user_id == user_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one()

    async def update_profile(self, user_id: uuid.UUID, values: dict[str, Any]) -> None:
        if values:
            await self._session.execute(
                update(UserProfile)
                .where(UserProfile.user_id == user_id)
                .values(**values, updated_at=text("now()"))
            )

    # ----------------------------------------------------------------- risk profiles (owned)

    async def add_risk_profile(
        self, user_id: uuid.UUID, risk_tolerance: str, horizon_years: int | None
    ) -> RiskProfile:
        row = RiskProfile(
            user_id=user_id, risk_tolerance=risk_tolerance, horizon_years=horizon_years
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def list_risk_profiles(self, user_id: uuid.UUID) -> list[RiskProfile]:
        result = await self._session.execute(
            owned_by(RiskProfile, user_id).order_by(
                RiskProfile.assessed_at.desc(), RiskProfile.created_at.desc()
            )
        )
        return list(result.scalars())

    async def get_risk_profile(
        self, user_id: uuid.UUID, profile_id: uuid.UUID
    ) -> RiskProfile | None:
        """The caller's risk profile, or None if it does not exist or belongs to someone else."""
        result = await self._session.execute(
            owned_by(RiskProfile, user_id)
            .where(RiskProfile.id == profile_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def update_risk_profile(
        self, user_id: uuid.UUID, profile_id: uuid.UUID, values: dict[str, Any]
    ) -> bool:
        """Updates only a row owned by `user_id` (the WHERE clause enforces it). Returns found."""
        result = await self._session.execute(
            update(RiskProfile)
            .where(RiskProfile.id == profile_id, RiskProfile.user_id == user_id)
            .values(**values, updated_at=text("now()"))
            .returning(RiskProfile.id)
        )
        return result.scalar_one_or_none() is not None
