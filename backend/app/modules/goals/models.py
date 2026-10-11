"""Goal tables (P06-T06). A goal belongs to one user; its progress is computed from the user's
portfolios and the goal's stated assumptions (docs/design/goals.md). Goals are plans, not
financial records: they can be changed and deleted (with audit events)."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AMOUNT, Base, TimestampMixin, UUIDPrimaryKeyMixin

GOAL_TYPES = ("wealth", "retirement", "education", "house_deposit", "business_capital", "custom")
SCENARIO_KINDS = ("conservative", "base", "growth")
FREQUENCIES = ("monthly", "quarterly", "yearly")
PERCENT = Numeric(9, 4)  # percentages (8.25 means 8.25%)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Goal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "goals"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_goals_user_id_name"),
        CheckConstraint("length(btrim(name)) BETWEEN 1 AND 100", name="name"),
        CheckConstraint(_in("goal_type", GOAL_TYPES), name="goal_type"),
        CheckConstraint("target_currency ~ '^[A-Z]{3}$'", name="target_currency"),
        CheckConstraint("target_amount > 0", name="target_amount_positive"),
        CheckConstraint("contribution >= 0", name="contribution_non_negative"),
        CheckConstraint(_in("contribution_frequency", FREQUENCIES), name="contribution_frequency"),
        CheckConstraint(_in("compounding_frequency", FREQUENCIES), name="compounding_frequency"),
        CheckConstraint(
            "contribution_growth_percent >= 0 AND inflation_percent >= 0 "
            "AND annual_fee_percent >= 0",
            name="percents_non_negative",
        ),
        Index("ix_goals_portfolio_id", "portfolio_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    # The portfolio whose value funds the goal; None means all the user's active portfolios.
    portfolio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("portfolios.id", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(100))
    goal_type: Mapped[str] = mapped_column(String(24), server_default=text("'wealth'"))
    target_amount: Mapped[Decimal] = mapped_column(AMOUNT)
    target_currency: Mapped[str] = mapped_column(String(3))
    target_date: Mapped[date] = mapped_column()
    # True: the target is in today's money and grows with inflation to the target date.
    target_in_todays_money: Mapped[bool] = mapped_column(server_default=text("false"))
    # Assumptions shared by the goal's scenarios (each scenario sets its own return).
    contribution: Mapped[Decimal] = mapped_column(AMOUNT, server_default=text("0"))
    contribution_frequency: Mapped[str] = mapped_column(
        String(16), server_default=text("'monthly'")
    )
    contribution_growth_percent: Mapped[Decimal] = mapped_column(PERCENT, server_default=text("0"))
    inflation_percent: Mapped[Decimal] = mapped_column(PERCENT, server_default=text("0"))
    annual_fee_percent: Mapped[Decimal] = mapped_column(PERCENT, server_default=text("0"))
    compounding_frequency: Mapped[str] = mapped_column(String(16), server_default=text("'monthly'"))


class GoalScenario(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A return assumption for a goal. Every goal has a base scenario (its status is measured
    against it); conservative and growth are optional."""

    __tablename__ = "goal_scenarios"
    __table_args__ = (
        UniqueConstraint("goal_id", "kind", name="uq_goal_scenarios_goal_id_kind"),
        CheckConstraint(_in("kind", SCENARIO_KINDS), name="kind"),
    )

    goal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    annual_return_percent: Mapped[Decimal] = mapped_column(PERCENT)
