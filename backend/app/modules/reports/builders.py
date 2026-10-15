"""Builds each report from the platform's own services (P14-T15). The figures are the ones the
screens show for the same request, taken from the same builders, so a file and a screen agree
(QG-30.1). Every builder is owner-scoped by the service it calls: another user's portfolio is
"not found". Nothing is calculated here."""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidValueError
from app.core.money import Money
from app.modules.goals.service import GoalService
from app.modules.networth.income_api import income_summary_out, portfolio_income_out
from app.modules.networth.service import NetWorthService
from app.modules.portfolio.analytics_views import allocation_out, performance_out
from app.modules.portfolio.service import PortfolioService
from app.modules.portfolio.summary_service import SummaryService
from app.modules.reports.model import Report, Table
from app.modules.transactions.holdings_service import HoldingsService

CATALOGUE = [
    ("portfolio", "Portfolio statement", True, "Totals and holdings of one portfolio."),
    (
        "performance",
        "Performance and allocation",
        True,
        "Return, profit and loss, and allocation of one portfolio.",
    ),
    ("net-worth", "Net worth", False, "Assets, liabilities and what is left."),
    (
        "income",
        "Passive income",
        False,
        "Dividends, interest, rent and coupons; one portfolio or all.",
    ),
    ("goals", "Goals", False, "Each goal's progress, estimate and projected outcomes."),
]


def _m(money: Money | None) -> str:
    """The amount exactly as the API writes it (a decimal string in the currency's minor units)."""
    return "" if money is None else str(money.model_dump(mode="json")["amount"])


def _s(value: object) -> str:
    if value is None:
        return ""
    return format(value, "f") if isinstance(value, Decimal) else str(value)


def _at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


async def build(
    kind: str,
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    portfolio_id: uuid.UUID | None,
    currency: str | None,
    now: datetime,
) -> Report:
    """Raises InvalidValueError (422) for a report that needs a portfolio, and
    ResourceNotFoundError (404) for a portfolio that is not the user's."""
    if kind in ("portfolio", "performance"):
        if portfolio_id is None:
            raise InvalidValueError("portfolio_id is required for this report")
        if kind == "portfolio":
            return await _portfolio(session, user_id, portfolio_id, currency, now)
        return await _performance(session, user_id, portfolio_id, now)
    if kind == "net-worth":
        return await _net_worth(session, user_id, currency, now)
    if kind == "income":
        return await _income(session, user_id, portfolio_id, currency, now)
    if kind == "goals":
        return await _goals(session, user_id, now)
    raise InvalidValueError(f"unknown report {kind}")


async def _portfolio(
    session: AsyncSession,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID,
    currency: str | None,
    now: datetime,
) -> Report:
    portfolio = await PortfolioService(session).get(user_id, portfolio_id)
    summaries = SummaryService(session)
    s = await (
        summaries.portfolio_in(user_id, portfolio_id, currency)
        if currency
        else summaries.portfolio(user_id, portfolio_id)
    )
    holdings = await HoldingsService(session).list(user_id, portfolio_id, False)
    totals = Table(
        "Totals",
        ("Measure", "Amount"),
        [
            ("Total value", _m(s.total_value)),
            ("Holdings value", _m(s.holdings_value)),
            ("Cash", _m(s.cash)),
            ("Cost basis", _m(s.cost_basis)),
            ("Unrealised profit or loss", _m(s.unrealized_pl)),
            ("Realised profit or loss", _m(s.realized_pl)),
            ("Income", _m(s.income)),
            ("Expenses", _m(s.expenses)),
            ("Net contributions", _m(s.net_contributions)),
        ],
        frozenset({1}),
    )
    rows: list[tuple[str, ...]] = [
        (
            h.asset.name,
            _s(h.asset.symbol),
            h.asset.asset_class,
            h.asset.currency,
            _s(h.quantity),
            _m(h.average_cost),
            _m(h.cost_basis),
            _m(h.value),
            _s(h.value_as_of)[:10],
            "stale" if h.value_stale else "",
        )
        for h in holdings
    ]
    table = Table(
        "Holdings",
        (
            "Asset",
            "Symbol",
            "Class",
            "Asset currency",
            "Quantity",
            "Average cost",
            "Cost basis",
            "Value",
            "Valued on",
            "Note",
        ),
        rows,
        frozenset({4, 5, 6, 7}),
    )
    notes = []
    if s.unpriced_assets:
        notes.append(
            f"{len(s.unpriced_assets)} position(s) have no price or valuation and are not in "
            "the value."
        )
    if s.freshness.unconverted_currencies:
        notes.append(
            "Amounts in "
            + ", ".join(s.freshness.unconverted_currencies)
            + " have no exchange rate and are left out."
        )
    return Report(
        "portfolio",
        f"Portfolio statement: {portfolio.name}",
        now,
        s.currency,
        s.freshness.data_as_of,
        [totals, table],
        notes,
    )


async def _performance(
    session: AsyncSession, user_id: uuid.UUID, portfolio_id: uuid.UUID, now: datetime
) -> Report:
    portfolio = await PortfolioService(session).get(user_id, portfolio_id)
    p = await performance_out(session, user_id, portfolio_id)
    a = await allocation_out(session, user_id, portfolio_id)
    perf = Table(
        "Performance",
        ("Measure", "Value"),
        [
            ("Total value", _m(p.total_value)),
            ("Net invested", _m(p.net_invested)),
            ("Profit or loss", _m(p.profit_loss)),
            ("Return on money invested (%)", _s(p.return_percent)),
            ("Money-weighted return, a year (%)", _s(p.money_weighted.annual_return_percent)),
            ("Contributions", _m(p.contributions)),
            ("Withdrawals", _m(p.withdrawals)),
            ("Income", _m(p.income)),
            ("Expenses", _m(p.expenses)),
            ("Realised profit or loss", _m(p.realized_pl)),
            ("Unrealised profit or loss", _m(p.unrealized_pl)),
        ],
        frozenset({1}),
    )
    tables = [perf]
    for title, dimension in (
        ("Allocation by asset class", a.asset_class),
        ("Allocation by currency", a.currency_exposure),
        ("Allocation by country", a.country),
        ("Allocation by sector", a.sector),
    ):
        tables.append(
            Table(
                title,
                ("Group", "Value", "Share (%)", "Positions"),
                [
                    (s.key or "Unclassified", _m(s.value), _s(s.weight_percent), str(s.parts))
                    for s in dimension.slices
                ],
                frozenset({1, 2, 3}),
            )
        )
    notes = [p.notice]
    if not p.complete:
        notes.append("Some assets have no price yet, so these figures are incomplete.")
    if p.assumed_deposit_count:
        notes.append(
            f"{p.assumed_deposit_count} holding(s) have no recorded purchase; a deposit on the "
            "first date is assumed."
        )
    return Report(
        "performance",
        f"Performance and allocation: {portfolio.name}",
        now,
        p.currency,
        _at(p.as_of),
        tables,
        notes,
    )


async def _net_worth(
    session: AsyncSession, user_id: uuid.UUID, currency: str | None, now: datetime
) -> Report:
    n = await NetWorthService(session).user(user_id, currency, now)
    summary = Table(
        "Net worth",
        ("Measure", "Amount"),
        [
            ("Assets", _m(n.assets)),
            ("Liabilities", _m(n.liabilities)),
            ("Net worth", _m(n.net_worth)),
        ],
        frozenset({1}),
    )
    by_class = Table(
        "Assets by class",
        ("Class", "Value", "Share (%)"),
        [
            (c.asset_class.replace("_", " "), _m(c.value), _s(c.share_percent))
            for c in n.assets_by_class
        ],
        frozenset({1, 2}),
    )
    liabilities = Table(
        "Liabilities",
        ("Name", "Type", "Balance", "Balance currency", "In report currency", "Balance as of"),
        [
            (
                line.name,
                line.liability_type.replace("_", " "),
                _m(line.balance),
                line.balance.currency,
                _m(line.value),
                line.balance_as_of.isoformat(),
            )
            for line in n.liability_lines
        ],
        frozenset({2, 4}),
    )
    rates = Table(
        "Exchange rates used",
        ("From", "Rate", "Provider", "As of", "Stale"),
        [
            (f.currency, _s(f.rate), f.provider, _s(f.as_of)[:16], "yes" if f.stale else "")
            for f in n.fx_rates
        ],
        frozenset({1}),
    )
    notes = []
    if not n.freshness.complete:
        notes.append(
            "Some figures are incomplete: unpriced assets or currencies without a rate are "
            "left out."
        )
    return Report(
        "net-worth",
        "Net worth",
        now,
        n.currency,
        n.freshness.data_as_of,
        [summary, by_class, liabilities, rates],
        notes,
    )


async def _income(
    session: AsyncSession,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    currency: str | None,
    now: datetime,
) -> Report:
    if portfolio_id is None:
        s = await income_summary_out(session, user_id, currency)
        names = {p.id: p.name for p in await PortfolioService(session).list(user_id, False)}
        totals = Table(
            "Passive income",
            ("Measure", "Amount"),
            [
                ("Per month (net)", _m(s.monthly)),
                ("Per year (net)", _m(s.yearly)),
                ("Per year (gross)", _m(s.yearly_gross)),
            ],
            frozenset({1}),
        )
        by_portfolio = Table(
            "By portfolio",
            ("Portfolio", "Net a year (portfolio currency)", "Currency", "In report currency"),
            [
                (
                    names.get(p.portfolio_id, "Portfolio"),
                    _m(p.yearly),
                    p.yearly.currency,
                    _m(p.value),
                )
                for p in s.portfolios
            ],
            frozenset({1, 3}),
        )
        notes = (
            []
            if s.complete
            else [
                "Income in "
                + ", ".join(s.unconverted_currencies)
                + " could not be converted and is left out."
            ]
        )
        return Report(
            "income", "Passive income", now, s.currency, _at(s.as_of), [totals, by_portfolio], notes
        )
    portfolio = await PortfolioService(session).get(user_id, portfolio_id)
    i = await portfolio_income_out(session, user_id, portfolio_id)
    t = i.trailing_12m
    last12 = Table(
        "The last 12 months",
        ("Measure", "Amount"),
        [
            ("Gross", _m(t.gross)),
            ("Fees", _m(t.fees)),
            ("Taxes", _m(t.taxes)),
            ("Net", _m(t.net)),
            ("Payments", str(t.payments)),
            ("Yield on portfolio value (%)", _s(i.portfolio_yield_percent)),
        ],
        frozenset({1}),
    )
    months = Table(
        "By month",
        ("Month", "Gross", "Fees", "Taxes", "Net", "Payments"),
        [
            (
                m.period,
                _m(m.totals.gross),
                _m(m.totals.fees),
                _m(m.totals.taxes),
                _m(m.totals.net),
                str(m.totals.payments),
            )
            for m in i.months
        ],
        frozenset({1, 2, 3, 4, 5}),
    )
    by_type = Table(
        "By type",
        ("Type", "Net, last 12 months", "Net, all time"),
        [(x.income_type, _m(x.trailing_12m.net), _m(x.all_time.net)) for x in i.by_type],
        frozenset({1, 2}),
    )
    notes = (
        [] if i.complete else ["Some income could not be converted, so the figures are incomplete."]
    )
    return Report(
        "income",
        f"Passive income: {portfolio.name}",
        now,
        i.currency,
        _at(i.as_of),
        [last12, months, by_type],
        notes,
    )


async def _goals(session: AsyncSession, user_id: uuid.UUID, now: datetime) -> Report:
    service = GoalService(session)
    goals = await service.list(user_id)
    rows: list[tuple[str, ...]] = []
    scenarios: list[tuple[str, ...]] = []
    currency = ""
    notes: list[str] = []
    for goal in goals:
        p = await service.progress(user_id, goal.id, now)
        currency = currency or p.target.currency
        rows.append(
            (
                p.name,
                "reached"
                if p.reached
                else "past its date"
                if p.overdue
                else p.status.replace("_", " "),
                _m(p.target),
                p.target_date.isoformat(),
                _m(p.current_value),
                _m(p.gap),
                _s(p.progress_percent),
                str(p.months_left),
                _s(p.estimated_completion),
                _m(p.required_contribution),
            )
        )
        for sc in p.scenarios:
            scenarios.append(
                (
                    p.name,
                    sc.kind,
                    _s(sc.annual_return_percent),
                    _m(sc.projected_value),
                    "yes" if sc.reaches_target else "no",
                )
            )
        notes = [p.notice]
    progress = Table(
        "Goals",
        (
            "Goal",
            "Status",
            "Target",
            "Target date",
            "Saved so far",
            "Still to go",
            "Progress (%)",
            "Months left",
            "Estimated completion",
            "Contribution needed",
        ),
        rows,
        frozenset({2, 4, 5, 6, 7, 9}),
    )
    outcomes = Table(
        "Projected outcomes",
        ("Goal", "Scenario", "Assumed return (%)", "Projected value", "Reaches target"),
        scenarios,
        frozenset({2, 3}),
    )
    return Report("goals", "Goals", now, currency or "n/a", now, [progress, outcomes], notes)
