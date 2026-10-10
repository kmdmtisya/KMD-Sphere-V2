"""Identity use cases: provisioning the current user and reading/updating their profile."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, AuditWriter
from app.core.auth import TokenClaims
from app.core.authz import ResourceNotFoundError, require_found
from app.modules.identity.models import RiskProfile
from app.modules.identity.repository import IdentityRepository
from app.modules.identity.schemas import (
    MeResponse,
    Preferences,
    PreferencesUpdate,
    RiskProfileCreate,
    RiskProfileOut,
    RiskProfileUpdate,
)

# Refresh last_seen_at at most this often, so ordinary reads do not write on every request.
_TOUCH_INTERVAL = timedelta(hours=1)
_PROFILE_FIELDS = ("display_name", "base_currency", "locale", "timezone")
_REQUIRED_PROFILE_FIELDS = ("base_currency", "locale", "timezone")
_UI_FIELDS = ("theme_mode", "dashboard_layout")


@dataclass(frozen=True)
class CurrentUser:
    """The authenticated user, available to every protected endpoint."""

    id: uuid.UUID
    subject: str
    email: str | None
    roles: frozenset[str]


class UserDisabledError(Exception):
    pass


class InvalidProfileChangeError(ValueError):
    pass


class IdentityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = IdentityRepository(session)
        self._audit = AuditWriter(session)

    async def provision(self, claims: TokenClaims) -> CurrentUser:
        """Returns the user for these claims, creating it on first sight (idempotent)."""
        user = await self._repo.find_user(claims.issuer, claims.subject)
        changed = user is None or (
            user.email != claims.email or user.email_verified != claims.email_verified
        )
        if changed:
            user_id = await self._repo.upsert_user(
                claims.issuer, claims.subject, claims.email, claims.email_verified
            )
            await self._session.commit()
            user = await self._repo.get_user(user_id)
        elif user is not None and (
            user.last_seen_at is None or user.last_seen_at < datetime.now(UTC) - _TOUCH_INTERVAL
        ):
            await self._repo.touch(user.id)
            await self._session.commit()
        if user is None:  # unreachable: the upsert above always returns the row
            raise UserDisabledError
        if user.status != "active":
            raise UserDisabledError
        return CurrentUser(id=user.id, subject=user.subject, email=user.email, roles=claims.roles)

    async def me(self, user_id: uuid.UUID) -> MeResponse:
        user = await self._repo.get_user(user_id)
        profile = await self._repo.get_profile(user_id)
        return MeResponse(
            id=user.id,
            email=user.email,
            email_verified=user.email_verified,
            display_name=profile.display_name,
            base_currency=profile.base_currency,
            locale=profile.locale,
            timezone=profile.timezone,
            preferences=Preferences.model_validate(profile.preferences or {}),
            created_at=user.created_at,
        )

    async def update_preferences(self, user_id: uuid.UUID, change: PreferencesUpdate) -> MeResponse:
        sent = change.model_dump(exclude_unset=True, mode="json")
        for key in _REQUIRED_PROFILE_FIELDS:
            if key in sent and sent[key] is None:
                raise InvalidProfileChangeError(f"{key} cannot be cleared")
        profile = await self._repo.get_profile(user_id)
        prefs = dict(profile.preferences or {})
        for key in _UI_FIELDS:
            if key in sent:
                if sent[key] is None:
                    prefs.pop(key, None)
                else:
                    prefs[key] = sent[key]
        Preferences.model_validate(prefs)  # what is stored always matches the schema
        values = {k: sent[k] for k in _PROFILE_FIELDS if k in sent}
        values["preferences"] = prefs
        await self._repo.update_profile(user_id, values)
        await self._session.commit()
        return await self.me(user_id)

    # ----------------------------------------------------------------- risk profiles (owned)

    @staticmethod
    def _out(row: RiskProfile) -> RiskProfileOut:
        return RiskProfileOut.model_validate(row, from_attributes=True)

    async def add_risk_profile(self, user_id: uuid.UUID, body: RiskProfileCreate) -> RiskProfileOut:
        row = await self._repo.add_risk_profile(user_id, body.risk_tolerance, body.horizon_years)
        await self._audit.record(
            "identity.risk_profile.created",
            Actor.user(user_id),
            resource_type="risk_profile",
            resource_id=row.id,
            details={"risk_tolerance": row.risk_tolerance, "horizon_years": row.horizon_years},
        )
        await self._session.commit()
        return self._out(row)

    async def list_risk_profiles(self, user_id: uuid.UUID) -> list[RiskProfileOut]:
        return [self._out(r) for r in await self._repo.list_risk_profiles(user_id)]

    async def get_risk_profile(self, user_id: uuid.UUID, profile_id: uuid.UUID) -> RiskProfileOut:
        row = require_found(await self._repo.get_risk_profile(user_id, profile_id), "risk profile")
        return self._out(row)

    async def update_risk_profile(
        self, user_id: uuid.UUID, profile_id: uuid.UUID, change: RiskProfileUpdate
    ) -> RiskProfileOut:
        values = change.model_dump(exclude_unset=True)
        if "risk_tolerance" in values and values["risk_tolerance"] is None:
            raise InvalidProfileChangeError("risk_tolerance cannot be cleared")
        if values:
            if not await self._repo.update_risk_profile(user_id, profile_id, values):
                raise ResourceNotFoundError("risk profile")
            await self._audit.record(
                "identity.risk_profile.updated",
                Actor.user(user_id),
                resource_type="risk_profile",
                resource_id=profile_id,
                details={"changed": sorted(values), **values},
            )
            await self._session.commit()
        return await self.get_risk_profile(user_id, profile_id)
