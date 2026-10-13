"""The opportunity pipeline (P12-T06): investment universe -> eligibility -> features and
explainable scores -> portfolio compatibility -> retrieved research -> model explanation from that
evidence only -> validation -> persisted run (SOLUTION_INTENT section 17).

Every number in a result comes from the deterministic steps. The model only explains them, and an
explanation that adds a fact, a figure or a forecast is refused (explain.py). Runs are kept as they
were and audited. Nothing is bought or prepared for trading: an opportunity is a research candidate
with its risks, never an instruction."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.base import LlmProvider
from app.core.audit import Actor, AuditWriter
from app.core.authz import ResourceNotFoundError
from app.core.money import round_half_up
from app.core.ratelimit import RateLimitedError
from app.modules.assets.liquidity import Liquidity
from app.modules.compatibility.schemas import compatibility_out
from app.modules.compatibility.service import Compatibility, CompatibilityService
from app.modules.doctor.service import DoctorService
from app.modules.opportunities.explain import explain
from app.modules.opportunities.models import Opportunity, OpportunityRun
from app.modules.research.embedding import Embedder
from app.modules.research.service import Evidence, ResearchService
from app.modules.scoring.schemas import scored_out
from app.modules.scoring.scoring import Factor
from app.modules.scoring.service import ScoredItem, ScoringService
from app.modules.universe.eligibility import MIN_HORIZON_YEARS
from app.modules.universe.service import UniverseService

DAY = timedelta(days=1)
EVIDENCE_PER_CANDIDATE = 3
# A stated research horizon (an assumption, not advice): the longer of the time the instrument's
# liquidity ties money up (the eligibility rule) and a typical recovery time for its risk level.
RISK_HORIZON_YEARS = {1: 0, 2: 1, 3: 3, 4: 5, 5: 7}


def horizon(risk_level: int, liquidity: Liquidity) -> dict[str, Any]:
    years = max(RISK_HORIZON_YEARS[risk_level], MIN_HORIZON_YEARS[liquidity])
    return {
        "minimum_years": years,
        "basis": f"Assumed: at least {years} years for a risk level {risk_level} instrument with "
        f"{liquidity.value} liquidity, so there is time to recover from falls.",
    }


# Without an amount, compatibility is checked for this share of the portfolio's value.
DEFAULT_AMOUNT_SHARE = Decimal("0.05")


@dataclass(frozen=True)
class RunRequest:
    portfolio_id: uuid.UUID | None = None
    amount: Decimal | None = None
    amount_currency: str | None = None
    asset_class: str | None = None
    limit: int = 3


def _facts(
    scored: ScoredItem, compat: Compatibility | None, evidence: list[Evidence]
) -> dict[str, Any]:
    """What the model may use about one candidate: deterministic results only, and no money
    amounts of the user's (compatibility is given as shares and checks)."""
    item = scored.item
    out = scored_out(scored).model_dump(mode="json")
    facts: dict[str, Any] = {
        "asset_id": str(item.asset_id),
        "symbol": item.symbol,
        "name": item.name,
        "asset_class": item.asset_class,
        "currency": item.currency,
        "risk_level": item.risk_level,
        "liquidity": item.liquidity.value,
        "is_demo": item.is_demo,
        "score": out["score"],
        "prices_as_of": out["last_close"],
        "universe_as_of": item.data_as_of.isoformat(),
        "research_horizon": horizon(item.risk_level, item.liquidity),
        "evidence": [
            {
                "id": str(e.id),
                "title": e.title,
                "summary": e.summary,
                "source": e.source,
                "licence_status": e.licence_status,
                "published_at": e.published_at.isoformat(),
            }
            for e in evidence
        ],
        "compatibility": None,
    }
    if compat is not None:
        c = compatibility_out(compat).model_dump(mode="json")
        drop = ("total_value",)
        facts["compatibility"] = {
            "verdict": c["verdict"],
            "reasons": c["reasons"],
            "before": {k: v for k, v in c["before"].items() if k not in drop},
            "after": {k: v for k, v in c["after"].items() if k not in drop},
            "doctor_changes": c["doctor_changes"],
        }
    return facts


class OpportunityService:
    def __init__(
        self,
        session: AsyncSession,
        weights: dict[Factor, Decimal],
        embedder: Embedder,
        llm: LlmProvider | None,
        runs_per_day: int,
    ) -> None:
        self._session = session
        self._weights = weights
        self._scoring = ScoringService(session, weights)
        self._compat = CompatibilityService(session)
        self._doctor = DoctorService(session)
        self._universe = UniverseService(session)
        self._research = ResearchService(session, embedder)
        self._llm = llm
        self._runs_per_day = runs_per_day
        self._audit = AuditWriter(session)

    async def _check_daily_limit(self, user_id: uuid.UUID, now: datetime) -> None:
        count, oldest = (
            await self._session.execute(
                select(func.count(), func.min(OpportunityRun.created_at)).where(
                    OpportunityRun.user_id == user_id, OpportunityRun.created_at > now - DAY
                )
            )
        ).one()
        if count >= self._runs_per_day and oldest is not None:
            raise RateLimitedError(max(int((oldest + DAY - now).total_seconds()), 1))

    async def run(self, user_id: uuid.UUID, request: RunRequest, now: datetime) -> OpportunityRun:
        await self._check_daily_limit(user_id, now)
        amount = request.amount
        currency: str | None = request.amount_currency
        if request.portfolio_id is not None and amount is None:
            inputs = await self._doctor.inputs(user_id, request.portfolio_id, now)
            amount = round_half_up(inputs.total * DEFAULT_AMOUNT_SHARE, 2)
            currency = inputs.currency
        scored = await self._scoring.universe(user_id, request.asset_class, now)
        candidates: list[tuple[ScoredItem, Compatibility | None, list[Evidence]]] = []
        excluded: list[dict[str, Any]] = []
        for s in scored:
            if len(candidates) >= request.limit:
                break
            if not s.item.eligibility.eligible or s.score.score is None:
                continue
            compat = None
            if request.portfolio_id is not None and amount is not None and amount > 0:
                compat = await self._compat.check(
                    user_id, request.portfolio_id, s.item.asset_id, amount, str(currency), now
                )
                if compat.assessment.verdict.value == "not_suitable":
                    excluded.append(
                        {
                            "asset_id": str(s.item.asset_id),
                            "symbol": s.item.symbol,
                            "reasons": [r.message for r in compat.assessment.reasons],
                        }
                    )
                    continue
            evidence = await self._research.for_asset(s.item.asset_id, EVIDENCE_PER_CANDIDATE)
            candidates.append((s, compat, evidence))
        facts = [_facts(s, c, e) for s, c, e in candidates]
        outcome = await explain(self._llm, facts)
        universe = await self._universe.investor(user_id)  # the facts eligibility used
        run = OpportunityRun(
            id=uuid.uuid4(),
            user_id=user_id,
            portfolio_id=request.portfolio_id,
            amount=amount if request.portfolio_id is not None else None,
            amount_currency=str(currency) if request.portfolio_id is not None else None,
            asset_class=request.asset_class,
            created_at=now,
            explanation_source=outcome.source,
            provider=outcome.provider,
            model=outcome.model,
            problems=list(outcome.problems),
            weights={f.value: str(w) for f, w in self._weights.items()},
            investor={
                "residence_country": universe.residence_country,
                "risk_tolerance": universe.risk_tolerance,
                "horizon_years": universe.horizon_years,
            },
            excluded=excluded,
        )
        self._session.add(run)
        await self._session.flush()
        for rank, f in enumerate(facts, start=1):
            exp = outcome.explanations[uuid.UUID(f["asset_id"])]
            self._session.add(
                Opportunity(
                    run_id=run.id,
                    rank=rank,
                    asset_id=uuid.UUID(f["asset_id"]),
                    is_demo=f["is_demo"],
                    facts=f,
                    explanation=exp.model_dump(mode="json", exclude={"asset_id"}),
                    explanation_source=outcome.source,
                )
            )
        await self._audit.record(
            "ai.opportunities.run",
            Actor.user(user_id),
            resource_type="opportunity_run",
            resource_id=run.id,
            details={
                "opportunities": len(facts),
                "excluded": len(excluded),
                "explanation_source": outcome.source,
                "provider": outcome.provider,
                "model": outcome.model,
                "problems": list(outcome.problems),
            },
        )
        await self._session.commit()
        return run

    async def runs(self, user_id: uuid.UUID, limit: int = 20) -> list[OpportunityRun]:
        return list(
            (
                await self._session.execute(
                    select(OpportunityRun)
                    .where(OpportunityRun.user_id == user_id)
                    .order_by(OpportunityRun.created_at.desc(), OpportunityRun.id)
                    .limit(limit)
                )
            ).scalars()
        )

    async def get(
        self, user_id: uuid.UUID, run_id: uuid.UUID
    ) -> tuple[OpportunityRun, list[Opportunity]]:
        run = await self._session.scalar(
            select(OpportunityRun).where(
                OpportunityRun.id == run_id, OpportunityRun.user_id == user_id
            )
        )
        if run is None:
            raise ResourceNotFoundError("opportunity run")
        items = list(
            (
                await self._session.execute(
                    select(Opportunity)
                    .where(Opportunity.run_id == run_id)
                    .order_by(Opportunity.rank)
                )
            ).scalars()
        )
        return run, items
