"""/api/v1/goals: the signed-in user's goals and their progress (P06-T06).

Progress is computed by the forecast engine under each goal's stated assumptions; it is an
estimate, never a promise (docs/design/goals.md)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import UNAUTHORIZED, conflict, invalid, not_found
from app.db.session import get_session
from app.modules.goals.schemas import (
    GoalCreate,
    GoalOut,
    GoalProgressOut,
    GoalsSummaryOut,
    GoalUpdate,
)
from app.modules.goals.service import GoalService
from app.modules.identity.dependencies import CurrentUserDep

router = APIRouter(prefix="/api/v1/goals", tags=["goals"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
_NOT_FOUND = not_found("goal")


def _now() -> datetime:
    return datetime.now(UTC)


@router.post(
    "",
    response_model=GoalOut,
    status_code=201,
    responses={
        **UNAUTHORIZED,
        **invalid("goal (limits, dates, currencies or portfolio)"),
        **conflict("Name already used, or the goal limit is reached"),
    },
)
async def create_goal(body: GoalCreate, user: CurrentUserDep, session: SessionDep) -> GoalOut:
    """Creates a goal with its target, date, funding and assumptions."""
    return await GoalService(session).create(user.id, body, _now().date())


@router.get("", response_model=list[GoalOut], responses=UNAUTHORIZED)
async def list_goals(user: CurrentUserDep, session: SessionDep) -> list[GoalOut]:
    """The signed-in user's goals, by target date."""
    return await GoalService(session).list(user.id)


@router.get("/summary", response_model=GoalsSummaryOut, responses=UNAUTHORIZED)
async def goals_summary(user: CurrentUserDep, session: SessionDep) -> GoalsSummaryOut:
    """Progress and status of every goal, and how many are on track (estimates)."""
    return await GoalService(session).summary(user.id, _now())


@router.get("/{goal_id}", response_model=GoalOut, responses={**UNAUTHORIZED, **_NOT_FOUND})
async def get_goal(goal_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> GoalOut:
    """One of the signed-in user's goals."""
    return await GoalService(session).get(user.id, goal_id)


@router.patch(
    "/{goal_id}",
    response_model=GoalOut,
    responses={**UNAUTHORIZED, **_NOT_FOUND, **invalid("change"), **conflict("Name already used")},
)
async def update_goal(
    goal_id: uuid.UUID, change: GoalUpdate, user: CurrentUserDep, session: SessionDep
) -> GoalOut:
    """Changes any part of a goal; `assumptions` replaces all assumptions."""
    return await GoalService(session).update(user.id, goal_id, change, _now().date())


@router.delete(
    "/{goal_id}", status_code=204, response_class=Response, responses={**UNAUTHORIZED, **_NOT_FOUND}
)
async def delete_goal(goal_id: uuid.UUID, user: CurrentUserDep, session: SessionDep) -> Response:
    """Deletes a goal (goals are plans; nothing in the ledger changes)."""
    await GoalService(session).delete(user.id, goal_id)
    return Response(status_code=204)


@router.get(
    "/{goal_id}/progress",
    response_model=GoalProgressOut,
    responses={**UNAUTHORIZED, **_NOT_FOUND},
)
async def goal_progress(
    goal_id: uuid.UUID, user: CurrentUserDep, session: SessionDep
) -> GoalProgressOut:
    """Progress, gap, scenario projections, required contribution and estimated completion,
    under the goal's stated assumptions (an estimate, not guaranteed)."""
    return await GoalService(session).progress(user.id, goal_id, _now())
