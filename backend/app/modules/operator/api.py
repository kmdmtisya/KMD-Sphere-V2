"""/api/v1/operator (P14-T17, DEC-34): read-only operational views for the `support` role.

Scope (docs/design/operator-views.md): the health of the platform and aggregate counts only. No
operator view returns a user's financial data, email, id or token; the audit view shows what
happened (action, outcome, kind of actor and resource, channel, time) without who or which record.
The role is checked on the server from the verified token; hiding the menu entry is never the
control. Every access, and every refused attempt, writes an audit event."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.api.health import ReadinessCheck
from app.core.api_responses import UNAUTHORIZED
from app.core.audit import Actor, AuditEvent, AuditWriter, Outcome
from app.core.auth import AuthenticationError
from app.core.authz import PermissionDeniedError
from app.core.config import Settings
from app.db.session import get_session
from app.modules.identity.dependencies import CurrentUserDep, bearer
from app.modules.identity.models import User
from app.worker.models import JobFailure, JobRun

SUPPORT_ROLE = "support"
WINDOW = timedelta(hours=24)

router = APIRouter(prefix="/api/v1/operator", tags=["operator"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
FORBIDDEN: dict[int | str, dict[str, Any]] = {403: {"description": "The support role is required"}}


async def require_support(
    request: Request,
    user: CurrentUserDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: SessionDep,
) -> None:
    """Allows only a token that carries the `support` realm role. A refused attempt is audited."""
    verifier = request.app.state.token_verifier
    if credentials is None or verifier is None:  # unreachable once CurrentUserDep has passed
        raise AuthenticationError("not authenticated")
    claims = await run_in_threadpool(verifier.verify, credentials.credentials)
    if SUPPORT_ROLE not in claims.roles:
        await AuditWriter(session).record(
            "operator.access.denied",
            Actor.user(user.id),
            resource_type="operator",
            outcome=Outcome.DENIED,
            details={"path": request.url.path},
        )
        await session.commit()
        raise PermissionDeniedError("the support role is required")


SupportDep = Depends(require_support)


class CountOut(BaseModel):
    name: str
    count: int


class OperatorStatusOut(BaseModel):
    generated_at: datetime
    environment: str
    checks: dict[str, Literal["ok", "failed"]] = Field(description="Readiness of each dependency")
    features: dict[str, str] = Field(description="Which optional modules are switched on")
    users: dict[str, int] = Field(description="Accounts by status (counts only)")
    window_hours: int
    audit_by_outcome: list[CountOut]
    audit_top_actions: list[CountOut]
    jobs_by_status: list[CountOut]
    job_failures_by_job: list[CountOut]
    notice: str


class OperatorAuditItem(BaseModel):
    occurred_at: datetime
    action: str
    outcome: str
    actor_type: str
    resource_type: str | None
    channel: str | None
    correlation_id: str | None


NOTICE = (
    "Operational view: counts and status only. It shows no account's financial data, email or "
    "identifier, and every view is recorded in the audit trail."
)


async def _checks(request: Request, settings: Settings) -> dict[str, Literal["ok", "failed"]]:
    checks: dict[str, ReadinessCheck] = request.app.state.readiness_checks

    async def run(check: ReadinessCheck) -> Literal["ok", "failed"]:
        try:
            await asyncio.wait_for(check(), timeout=settings.readiness_timeout_seconds + 1)
        except Exception:
            return "failed"
        return "ok"

    names = sorted(checks)
    results = await asyncio.gather(*(run(checks[n]) for n in names))
    return dict(zip(names, results, strict=True))


def _counts(rows: object) -> list[CountOut]:
    return [CountOut(name=str(name), count=int(count)) for name, count in rows]  # type: ignore[attr-defined]


@router.get(
    "/status",
    response_model=OperatorStatusOut,
    responses={**UNAUTHORIZED, **FORBIDDEN},
    dependencies=[SupportDep],
)
async def operator_status(
    request: Request, user: CurrentUserDep, session: SessionDep
) -> OperatorStatusOut:
    """Dependency health, optional modules, account counts, and the last day's audit, job and
    failure counts. No account is named."""
    settings: Settings = request.app.state.settings
    now = datetime.now(UTC)
    since = now - WINDOW
    user_rows = (
        await session.execute(select(User.status, func.count()).group_by(User.status))
    ).all()
    users = {str(status): int(n) for status, n in user_rows}
    outcomes = (
        await session.execute(
            select(AuditEvent.outcome, func.count())
            .where(AuditEvent.occurred_at >= since)
            .group_by(AuditEvent.outcome)
            .order_by(AuditEvent.outcome)
        )
    ).all()
    actions = (
        await session.execute(
            select(AuditEvent.action, func.count().label("n"))
            .where(AuditEvent.occurred_at >= since)
            .group_by(AuditEvent.action)
            .order_by(func.count().desc(), AuditEvent.action)
            .limit(10)
        )
    ).all()
    jobs = (
        await session.execute(
            select(JobRun.status, func.count())
            .where(JobRun.started_at >= since)
            .group_by(JobRun.status)
            .order_by(JobRun.status)
        )
    ).all()
    failures = (
        await session.execute(
            select(JobFailure.job_name, func.count().label("n"))
            .where(JobFailure.failed_at >= since)
            .group_by(JobFailure.job_name)
            .order_by(func.count().desc(), JobFailure.job_name)
            .limit(20)
        )
    ).all()
    out = OperatorStatusOut(
        generated_at=now,
        environment=settings.environment,
        checks=await _checks(request, settings),
        features={
            "forex": "on" if settings.forex_enabled else "off",
            "forex_feed": "on" if settings.forex_feed_enabled else "off",
            "assistant_provider": settings.ai_provider,
            "rate_limits": "on" if settings.rate_limit_enabled else "off",
        },
        users={"active": 0, "disabled": 0, **users},
        window_hours=int(WINDOW.total_seconds() // 3600),
        audit_by_outcome=_counts(outcomes),
        audit_top_actions=_counts(actions),
        jobs_by_status=_counts(jobs),
        job_failures_by_job=_counts(failures),
        notice=NOTICE,
    )
    await AuditWriter(session).record(
        "operator.status.viewed", Actor.user(user.id), resource_type="operator"
    )
    await session.commit()
    return out


@router.get(
    "/audit",
    response_model=list[OperatorAuditItem],
    responses={**UNAUTHORIZED, **FORBIDDEN},
    dependencies=[SupportDep],
)
async def operator_audit(
    user: CurrentUserDep,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    outcome: Annotated[Literal["success", "failure", "denied"] | None, Query()] = None,
    action_prefix: Annotated[
        str | None, Query(max_length=60, pattern=r"^[a-z][a-z0-9_.]*$", description="e.g. reports.")
    ] = None,
) -> list[OperatorAuditItem]:
    """The newest audit events, newest first, without who or which record: action, outcome, kind of
    actor and resource, channel, time and correlation id."""
    query = select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit)
    if outcome:
        query = query.where(AuditEvent.outcome == outcome)
    if action_prefix:
        query = query.where(AuditEvent.action.startswith(action_prefix, autoescape=True))
    rows = (await session.execute(query)).scalars().all()
    items = [
        OperatorAuditItem(
            occurred_at=r.occurred_at,
            action=r.action,
            outcome=r.outcome,
            actor_type=r.actor_type,
            resource_type=r.resource_type,
            channel=(r.details or {}).get("channel"),
            correlation_id=r.correlation_id,
        )
        for r in rows
    ]
    await AuditWriter(session).record(
        "operator.audit.viewed",
        Actor.user(user.id),
        resource_type="operator",
        details={"limit": limit, "outcome": outcome, "action_prefix": action_prefix},
    )
    await session.commit()
    return items
