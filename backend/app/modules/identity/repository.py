"""Data access for identity. Provisioning is idempotent and safe under concurrent first requests."""

import uuid
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import User, UserProfile


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
