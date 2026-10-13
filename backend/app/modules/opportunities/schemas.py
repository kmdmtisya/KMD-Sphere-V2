"""Opportunity API schemas (P12-T06)."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.money import Money, minor_units, round_half_up
from app.modules.opportunities.models import Opportunity, OpportunityRun

Action = Literal["research", "compare", "simulate"]
ACTIONS: tuple[Action, ...] = ("research", "compare", "simulate")
NOTICE = (
    "Research candidates selected by deterministic rules from your eligibility, measured "
    "characteristics, portfolio fit and retrieved evidence. Not advice and not a recommendation "
    "to buy or sell; no return is expected or promised. DEMO instruments are fictional. Actions: "
    "Research, Compare, Simulate."
)


class OpportunitiesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portfolio_id: uuid.UUID | None = Field(
        default=None, description="Check each candidate's fit against this portfolio"
    )
    amount: Money | None = Field(
        default=None,
        description="Hypothetical amount for the fit check, in the portfolio's base currency; "
        "default 5% of the portfolio's value. Needs portfolio_id",
    )
    asset_class: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,39}$")
    limit: int = Field(default=3, ge=1, le=5)


class ExplanationOut(BaseModel):
    thesis: str
    why_surfaced: str
    key_risks: list[str]
    assumptions: list[str]
    evidence_ids: list[uuid.UUID] = Field(description="Ids of evidence items in `facts`")


class OpportunityOut(BaseModel):
    rank: int
    asset_id: uuid.UUID
    symbol: str | None
    name: str
    asset_class: str
    is_demo: bool
    risk_level: int
    facts: dict[str, Any] = Field(
        description="The deterministic facts: score with factors, compatibility, evidence (with "
        "source, licence status and dates), prices_as_of and universe_as_of"
    )
    explanation: ExplanationOut
    explanation_source: Literal["model", "template"] = Field(
        description="model: written by the model from the facts and validated; template: fixed "
        "wording from the facts (no model, or no reply passed validation)"
    )
    actions: list[Action] = Field(default_factory=lambda: list(ACTIONS))
    is_trade: Literal[False] = False


class RunSummaryOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    portfolio_id: uuid.UUID | None
    asset_class: str | None
    explanation_source: Literal["model", "template"]


class RunOut(RunSummaryOut):
    amount: Money | None
    provider: str | None
    model: str | None
    weights: dict[str, str]
    investor: dict[str, Any] = Field(description="The facts eligibility used")
    excluded: list[dict[str, Any]] = Field(
        description="Eligible candidates left out because they did not suit the portfolio, why"
    )
    opportunities: list[OpportunityOut]
    notice: str = NOTICE


def summary_out(run: OpportunityRun) -> RunSummaryOut:
    return RunSummaryOut(
        id=run.id,
        created_at=run.created_at,
        portfolio_id=run.portfolio_id,
        asset_class=run.asset_class,
        explanation_source=run.explanation_source,
    )


def run_out(run: OpportunityRun, items: list[Opportunity]) -> RunOut:
    return RunOut(
        id=run.id,
        created_at=run.created_at,
        portfolio_id=run.portfolio_id,
        asset_class=run.asset_class,
        explanation_source=run.explanation_source,
        amount=None
        if run.amount is None or run.amount_currency is None
        else Money(
            amount=round_half_up(run.amount, minor_units(run.amount_currency)),
            currency=run.amount_currency,
        ),
        provider=run.provider,
        model=run.model,
        weights=run.weights,
        investor=run.investor,
        excluded=run.excluded,
        opportunities=[
            OpportunityOut(
                rank=o.rank,
                asset_id=o.asset_id,
                symbol=o.facts["symbol"],
                name=o.facts["name"],
                asset_class=o.facts["asset_class"],
                is_demo=o.is_demo,
                risk_level=o.facts["risk_level"],
                facts=o.facts,
                explanation=ExplanationOut.model_validate(o.explanation),
                explanation_source=o.explanation_source,
            )
            for o in items
        ],
    )
