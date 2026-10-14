"""Paper-trading API (P13-T09). PAPER TRADING: virtual accounts and simulated orders, behind the
forex flag; nothing is sent to a broker and nothing touches a real portfolio.

Every response carries `"mode": "PAPER TRADING"` and the header `X-Trading-Mode: PAPER TRADING`.
Every resource belongs to the caller: another user's account, order, position or journal entry
answers 404 (ADR-0011)."""

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.core.api_responses import UNAUTHORIZED, conflict, invalid, not_found
from app.core.money import CURRENCY_PATTERN, DecimalString, minor_units
from app.modules.forex.api import ForexUser, SessionDep
from app.modules.forex.marketdata.types import INSTRUMENT_PATTERN
from app.modules.forex.paper import analytics as an
from app.modules.forex.paper.models import (
    ForexPaperJournalEntry,
    ForexPaperOrder,
    ForexPaperPosition,
)
from app.modules.forex.paper.service import AccountState, OrderRequest, PaperService
from app.modules.forex.risk.engine import DISCLOSURES

Mode = Literal["PAPER TRADING"]
MODE: Mode = "PAPER TRADING"
TAG = r"^[a-z0-9][a-z0-9_-]{0,39}$"
NOTICE = (
    "PAPER TRADING: virtual money and simulated fills at the stored bid and ask, with modelled "
    "slippage and commission. Nothing is sent to a broker. Paper results are a separate series: "
    "they never enter net worth, holdings or the analytics of a real portfolio, and are never "
    "combined with backtested or live-observed results."
)
SERIES_NOTE = (
    "Paper results only: a separate, labelled series, never combined with backtested (P13-T08) "
    "or live-observed results and never part of a real portfolio's analytics."
)


def _mark(response: Response) -> None:
    response.headers["X-Trading-Mode"] = MODE


router = APIRouter(prefix="/api/v1/forex/paper", tags=["forex"], dependencies=[Depends(_mark)])
OWNED = {**UNAUTHORIZED, **not_found("paper resource, or the forex module is switched off")}


def money(value: Decimal | None, currency: str) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(Decimal(1).scaleb(-minor_units(currency)), rounding=ROUND_HALF_UP)


# ------------------------------------------------------------------------------------ schemas
class ForexPaperAccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    currency: str = Field(pattern=CURRENCY_PATTERN, examples=["USD"])
    starting_balance: DecimalString | None = Field(
        default=None, description="Virtual money; omitted: the default (10000), marked as such"
    )


class ForexExposureItem(BaseModel):
    currency: str
    amount: DecimalString = Field(description="Signed, in that currency: positive is long")


class ForexPaperAccountOut(BaseModel):
    mode: Mode = MODE
    id: uuid.UUID
    name: str
    currency: str
    status: Literal["active", "closed"]
    starting_balance: DecimalString
    starting_balance_is_default: bool
    balance: DecimalString = Field(description="Starting balance + realised P/L - open commissions")
    unrealised_pnl: DecimalString
    equity: DecimalString
    used_margin: DecimalString
    free_margin: DecimalString
    margin_level_percent: DecimalString | None
    open_positions: int
    pending_orders: int
    realised_today: DecimalString = Field(description="Since 00:00 UTC")
    realised_this_week: DecimalString = Field(description="Since Monday 00:00 UTC")
    exposure: list[ForexExposureItem]
    warnings: list[str]
    created_at: datetime
    notice: str = NOTICE


class ForexPaperAccountsOut(BaseModel):
    mode: Mode = MODE
    items: list[ForexPaperAccountOut]
    notice: str = NOTICE


class ForexPaperOrderCreate(BaseModel):
    instrument: str = Field(pattern=INSTRUMENT_PATTERN, examples=["EUR_USD"])
    side: Literal["long", "short"]
    order_type: Literal["market", "limit"] = "market"
    lots: DecimalString = Field(description="A multiple of the pair's lot step")
    stop: DecimalString = Field(description="Required: every paper position has a stop-loss")
    target: DecimalString | None = None
    limit_price: DecimalString | None = Field(default=None, description="For a limit order only")
    strategy_tag: str | None = Field(default=None, pattern=TAG)


class ForexPaperOrderOut(BaseModel):
    mode: Mode = MODE
    id: uuid.UUID
    account_id: uuid.UUID
    instrument: str
    side: Literal["long", "short"]
    order_type: Literal["market", "limit"]
    lots: DecimalString
    units: DecimalString
    limit_price: DecimalString | None
    stop: DecimalString
    target: DecimalString | None
    status: Literal["pending", "filled", "cancelled", "rejected"]
    strategy_tag: str | None
    contract_specification_version: int
    created_at: datetime
    filled_at: datetime | None
    cancelled_at: datetime | None


class ForexPaperPositionOut(BaseModel):
    mode: Mode = MODE
    id: uuid.UUID
    account_id: uuid.UUID
    order_id: uuid.UUID
    instrument: str
    side: Literal["long", "short"]
    lots: DecimalString
    units: DecimalString
    status: Literal["open", "closed"]
    entry_price: DecimalString = Field(description="The fill: bid or ask with slippage")
    entry_at: datetime
    data_type: str = Field(description="Of the quote the entry used, for example simulated")
    stop: DecimalString
    target: DecimalString | None
    margin: DecimalString
    strategy_tag: str | None
    current_price: DecimalString | None = Field(description="Open: the closing side of the quote")
    unrealised_pnl: DecimalString | None
    exit_price: DecimalString | None
    exit_at: datetime | None
    exit_reason: Literal["stop", "target", "manual"] | None
    exit_rate: DecimalString | None = Field(description="Quote to account currency at the exit")
    exit_rate_path: str | None
    realised_pnl: DecimalString | None = Field(description="Net of spread, slippage, commission")
    costs: DecimalString | None


class ForexPaperOrderPlacedOut(BaseModel):
    mode: Mode = MODE
    order: ForexPaperOrderOut
    position: ForexPaperPositionOut | None = Field(description="Set when a market order filled")
    warnings: list[str]
    disclosures: list[str]
    notice: str = NOTICE


class ForexPaperOrdersOut(BaseModel):
    mode: Mode = MODE
    items: list[ForexPaperOrderOut]


class ForexPaperPositionsOut(BaseModel):
    mode: Mode = MODE
    account_id: uuid.UUID
    currency: str
    items: list[ForexPaperPositionOut]
    warnings: list[str]


class ForexPaperLevels(BaseModel):
    stop: DecimalString
    target: DecimalString | None = None


class ForexPaperJournalCreate(BaseModel):
    note: str = Field(min_length=1, max_length=4000)
    tags: list[Annotated[str, Field(pattern=TAG)]] = Field(default_factory=list, max_length=10)
    position_id: uuid.UUID | None = None


class ForexPaperJournalOut(BaseModel):
    mode: Mode = MODE
    id: uuid.UUID
    account_id: uuid.UUID
    position_id: uuid.UUID | None
    note: str
    tags: list[str]
    created_at: datetime


class ForexPaperJournalListOut(BaseModel):
    mode: Mode = MODE
    items: list[ForexPaperJournalOut]


class ForexPaperSummary(BaseModel):
    trades: int
    wins: int
    win_rate: DecimalString | None
    net_pnl: DecimalString
    gross_profit: DecimalString
    gross_loss: DecimalString
    profit_factor: DecimalString | None
    average_pnl: DecimalString | None
    best: DecimalString | None
    worst: DecimalString | None
    costs: DecimalString


class ForexPaperGroup(BaseModel):
    key: str
    summary: ForexPaperSummary


class ForexPaperAnalyticsOut(BaseModel):
    mode: Mode = MODE
    label: Literal["paper"] = "paper"
    series_note: str = SERIES_NOTE
    account_id: uuid.UUID
    currency: str
    starting_balance: DecimalString
    overall: ForexPaperSummary
    max_drawdown: DecimalString = Field(description="Of the closed balance, as a fraction")
    return_on_starting_balance: DecimalString = Field(description="A fraction")
    longest_losing_streak: int
    by_strategy_tag: list[ForexPaperGroup]
    by_instrument: list[ForexPaperGroup]
    open_positions: int


# ----------------------------------------------------------------------------------- mappers
def _account(state: AccountState) -> ForexPaperAccountOut:
    a, c = state.account, state.account.currency
    return ForexPaperAccountOut(
        id=a.id,
        name=a.name,
        currency=c,
        status="active" if a.status == "active" else "closed",
        starting_balance=money(a.starting_balance, c),
        starting_balance_is_default=a.starting_balance_is_default,
        balance=money(state.balance, c),
        unrealised_pnl=money(state.unrealised, c),
        equity=money(state.equity, c),
        used_margin=money(state.used_margin, c),
        free_margin=money(state.free_margin, c),
        margin_level_percent=state.margin_level,
        open_positions=state.open_positions,
        pending_orders=state.pending_orders,
        realised_today=money(state.realised_today, c),
        realised_this_week=money(state.realised_this_week, c),
        exposure=[
            ForexExposureItem(currency=k, amount=v)
            for k, v in sorted(state.exposure.items())
            if v != 0
        ],
        warnings=state.warnings,
        created_at=a.created_at,
    )


def _order(o: ForexPaperOrder) -> ForexPaperOrderOut:
    return ForexPaperOrderOut(
        id=o.id,
        account_id=o.account_id,
        instrument=o.instrument,
        side="long" if o.side == "long" else "short",
        order_type="market" if o.order_type == "market" else "limit",
        lots=o.lots,
        units=o.units,
        limit_price=o.limit_price,
        stop=o.stop,
        target=o.target,
        status=o.status,
        strategy_tag=o.strategy_tag,
        contract_specification_version=o.spec_version,
        created_at=o.created_at,
        filled_at=o.filled_at,
        cancelled_at=o.cancelled_at,
    )


def _position(
    p: ForexPaperPosition, currency: str, state: AccountState | None = None
) -> ForexPaperPositionOut:
    mark = state.marks.get(p.id) if state is not None else None
    return ForexPaperPositionOut(
        id=p.id,
        account_id=p.account_id,
        order_id=p.order_id,
        instrument=p.instrument,
        side="long" if p.side == "long" else "short",
        lots=p.lots,
        units=p.units,
        status="open" if p.status == "open" else "closed",
        entry_price=p.entry_price,
        entry_at=p.entry_quote_at,
        data_type=p.data_type,
        stop=p.stop,
        target=p.target,
        margin=money(p.margin, currency),
        strategy_tag=p.strategy_tag,
        current_price=mark.price if mark is not None else None,
        unrealised_pnl=money(mark.unrealised, currency) if mark is not None else None,
        exit_price=p.exit_price,
        exit_at=p.exit_at,
        exit_reason=p.exit_reason,
        exit_rate=p.exit_rate,
        exit_rate_path=p.exit_rate_path,
        realised_pnl=money(p.realised_pnl, currency),
        costs=money(p.costs, currency),
    )


def _note(e: ForexPaperJournalEntry) -> ForexPaperJournalOut:
    return ForexPaperJournalOut(
        id=e.id,
        account_id=e.account_id,
        position_id=e.position_id,
        note=e.note,
        tags=list(e.tags),
        created_at=e.created_at,
    )


def _summary(s: an.Summary, currency: str) -> ForexPaperSummary:
    return ForexPaperSummary(
        trades=s.trades,
        wins=s.wins,
        win_rate=None if s.win_rate is None else s.win_rate.quantize(Decimal("0.0001")),
        net_pnl=money(s.net, currency),
        gross_profit=money(s.gross_profit, currency),
        gross_loss=money(s.gross_loss, currency),
        profit_factor=None
        if s.profit_factor is None
        else s.profit_factor.quantize(Decimal("0.01")),
        average_pnl=money(s.average, currency),
        best=money(s.best, currency),
        worst=money(s.worst, currency),
        costs=money(s.costs, currency),
    )


def _service(request: Request, session: SessionDep) -> PaperService:
    return PaperService(session, request.app.state.settings)


Service = Annotated[PaperService, Depends(_service)]


def _now() -> datetime:
    return datetime.now(UTC)


# ------------------------------------------------------------------------------------ routes
@router.post(
    "/accounts",
    status_code=status.HTTP_201_CREATED,
    response_model=ForexPaperAccountOut,
    summary="Open a paper-trading account (virtual money)",
    description="Virtual money only. The currency must be a forex currency; an omitted starting "
    "balance uses the default and is marked as such. At most the configured number of"
    " active accounts.",
    responses={**UNAUTHORIZED, **invalid("account"), **conflict("too many active paper accounts")},
)
async def create_account(
    body: ForexPaperAccountCreate, user: ForexUser, service: Service, request: Request
) -> ForexPaperAccountOut:
    settings = request.app.state.settings
    is_default = body.starting_balance is None
    balance: Decimal = (
        settings.forex_paper_default_balance
        if body.starting_balance is None
        else body.starting_balance
    )
    account = await service.create_account(user.id, body.name, body.currency, balance, is_default)
    return _account(await service.state(account, _now()))


@router.get(
    "/accounts",
    response_model=ForexPaperAccountsOut,
    summary="The caller's paper accounts",
    description="Each with its balance, equity, margin and exposure after the latest quotes are "
    "evaluated.",
    responses=OWNED,
)
async def list_accounts(user: ForexUser, service: Service) -> ForexPaperAccountsOut:
    now = _now()
    return ForexPaperAccountsOut(
        items=[_account(await service.state(a, now)) for a in await service.accounts(user.id)]
    )


@router.get(
    "/accounts/{account_id}",
    response_model=ForexPaperAccountOut,
    summary="One paper account: balance, equity, margin and exposure",
    description="Pending limit orders, stops and targets are evaluated against the stored quotes "
    "first. Another user's account answers 404.",
    responses=OWNED,
)
async def get_account(
    account_id: uuid.UUID, user: ForexUser, service: Service
) -> ForexPaperAccountOut:
    return _account(await service.state(await service.account(user.id, account_id), _now()))


@router.post(
    "/accounts/{account_id}/close",
    response_model=ForexPaperAccountOut,
    summary="Close a paper account (no open positions or pending orders)",
    description="A closed account takes no new orders. Refused while positions are open or orders"
    " pending.",
    responses={**OWNED, **conflict("open positions or pending orders")},
)
async def close_account(
    account_id: uuid.UUID, user: ForexUser, service: Service
) -> ForexPaperAccountOut:
    now = _now()
    account = await service.close_account(user.id, account_id, now)
    return _account(await service.state(account, now))


@router.post(
    "/accounts/{account_id}/orders",
    status_code=status.HTTP_201_CREATED,
    response_model=ForexPaperOrderPlacedOut,
    summary="Place a simulated paper order (market or limit) with a stop-loss",
    description="A market order fills at once at the stored ask (buy) or bid (sell) with the "
    "specification's slippage; a limit order waits for the quote to reach its price. Refused "
    "with no fresh quote, a bad size or levels, or not enough free paper margin; limits beyond "
    "the settings give warnings. Nothing is sent to a broker.",
    responses={**OWNED, **invalid("order"), **conflict("the paper account is closed")},
)
async def place_order(
    account_id: uuid.UUID, body: ForexPaperOrderCreate, user: ForexUser, service: Service
) -> ForexPaperOrderPlacedOut:
    placed = await service.place(
        user.id,
        account_id,
        OrderRequest(
            instrument=body.instrument,
            side=body.side,
            order_type=body.order_type,
            lots=body.lots,
            stop=body.stop,
            target=body.target,
            limit_price=body.limit_price,
            strategy_tag=body.strategy_tag,
        ),
        _now(),
    )
    account = await service.account(user.id, account_id)
    return ForexPaperOrderPlacedOut(
        order=_order(placed.order),
        position=None if placed.position is None else _position(placed.position, account.currency),
        warnings=placed.warnings,
        disclosures=list(DISCLOSURES),
    )


@router.get(
    "/accounts/{account_id}/orders",
    response_model=ForexPaperOrdersOut,
    summary="Paper orders",
    description="The account's paper orders, optionally by status, after evaluating pending limit"
    " orders.",
    responses=OWNED,
)
async def list_orders(
    account_id: uuid.UUID,
    user: ForexUser,
    service: Service,
    status_: Annotated[
        Literal["pending", "filled", "cancelled", "rejected"] | None, Query(alias="status")
    ] = None,
) -> ForexPaperOrdersOut:
    return ForexPaperOrdersOut(
        items=[_order(o) for o in await service.orders(user.id, account_id, status_, _now())]
    )


@router.post(
    "/accounts/{account_id}/orders/{order_id}/cancel",
    response_model=ForexPaperOrderOut,
    summary="Cancel a pending paper order",
    description="Only a pending limit order can be cancelled.",
    responses={**OWNED, **conflict("the order is not pending")},
)
async def cancel_order(
    account_id: uuid.UUID, order_id: uuid.UUID, user: ForexUser, service: Service
) -> ForexPaperOrderOut:
    return _order(await service.cancel(user.id, account_id, order_id, _now()))


@router.get(
    "/accounts/{account_id}/positions",
    response_model=ForexPaperPositionsOut,
    summary="Paper positions, open ones valued at the current quote",
    description="Open positions are valued at the closing side of the latest quote, converted "
    "into the account currency; closed ones show the exit, the rate used and the "
    "realised P/L net of costs.",
    responses=OWNED,
)
async def list_positions(
    account_id: uuid.UUID,
    user: ForexUser,
    service: Service,
    status_: Annotated[Literal["open", "closed"] | None, Query(alias="status")] = None,
) -> ForexPaperPositionsOut:
    state, rows = await service.positions(user.id, account_id, status_, _now())
    c = state.account.currency
    return ForexPaperPositionsOut(
        account_id=state.account.id,
        currency=c,
        items=[_position(p, c, state) for p in rows],
        warnings=state.warnings,
    )


@router.post(
    "/accounts/{account_id}/positions/{position_id}/close",
    response_model=ForexPaperPositionOut,
    summary="Close a paper position at the current bid or ask",
    description="A simulated market close at the latest fresh quote with slippage. Nothing is "
    "sent to a broker.",
    responses={**OWNED, **invalid("no fresh quote"), **conflict("the position is already closed")},
)
async def close_position(
    account_id: uuid.UUID, position_id: uuid.UUID, user: ForexUser, service: Service
) -> ForexPaperPositionOut:
    p = await service.close(user.id, account_id, position_id, _now())
    account = await service.account(user.id, account_id)
    return _position(p, account.currency)


@router.put(
    "/accounts/{account_id}/positions/{position_id}/levels",
    response_model=ForexPaperPositionOut,
    summary="Move a paper position's stop-loss and take-profit",
    description="The stop must stay on the losing side and the target on the winning side of the "
    "current closing price.",
    responses={**OWNED, **invalid("levels"), **conflict("the position is already closed")},
)
async def set_levels(
    account_id: uuid.UUID,
    position_id: uuid.UUID,
    body: ForexPaperLevels,
    user: ForexUser,
    service: Service,
) -> ForexPaperPositionOut:
    p = await service.set_levels(user.id, account_id, position_id, body.stop, body.target, _now())
    account = await service.account(user.id, account_id)
    return _position(p, account.currency)


@router.get(
    "/accounts/{account_id}/journal",
    response_model=ForexPaperJournalListOut,
    summary="The paper trading journal",
    description="Notes, newest first, optionally filtered by tag.",
    responses=OWNED,
)
async def list_journal(
    account_id: uuid.UUID,
    user: ForexUser,
    service: Service,
    tag: Annotated[str | None, Query(pattern=TAG)] = None,
) -> ForexPaperJournalListOut:
    return ForexPaperJournalListOut(
        items=[_note(e) for e in await service.journal(user.id, account_id, tag)]
    )


@router.post(
    "/accounts/{account_id}/journal",
    status_code=status.HTTP_201_CREATED,
    response_model=ForexPaperJournalOut,
    summary="Add a journal entry, optionally about one position",
    description="Tags are lower-cased and de-duplicated; a linked position must belong to this "
    "account.",
    responses={**OWNED, **invalid("journal entry")},
)
async def add_journal(
    account_id: uuid.UUID, body: ForexPaperJournalCreate, user: ForexUser, service: Service
) -> ForexPaperJournalOut:
    return _note(
        await service.add_note(user.id, account_id, body.note, body.tags, body.position_id)
    )


@router.delete(
    "/accounts/{account_id}/journal/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a journal entry",
    description="Removes one of the caller's journal entries.",
    responses=OWNED,
)
async def delete_journal(
    account_id: uuid.UUID, entry_id: uuid.UUID, user: ForexUser, service: Service
) -> Response:
    await service.delete_note(user.id, account_id, entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"X-Trading-Mode": MODE})


@router.get(
    "/accounts/{account_id}/analytics",
    response_model=ForexPaperAnalyticsOut,
    summary="Paper-trading performance: a separate, labelled series",
    description="Closed paper positions only: net P/L, win rate, profit factor, drawdown and "
    "breakdowns by strategy tag and pair. Never combined with backtested, live-"
    "observed or real-portfolio results.",
    responses=OWNED,
)
async def analytics(
    account_id: uuid.UUID, user: ForexUser, service: Service
) -> ForexPaperAnalyticsOut:
    account, closed = await service.closed(user.id, account_id, _now())
    perf = an.performance(account.starting_balance, closed)
    c = account.currency
    open_count = len(await service.open_positions(account))
    return ForexPaperAnalyticsOut(
        account_id=account.id,
        currency=c,
        starting_balance=money(account.starting_balance, c),
        overall=_summary(perf.overall, c),
        max_drawdown=perf.max_drawdown.quantize(Decimal("0.000001")),
        return_on_starting_balance=perf.return_on_start.quantize(Decimal("0.000001")),
        longest_losing_streak=perf.longest_losing_streak,
        by_strategy_tag=[
            ForexPaperGroup(key=k, summary=_summary(v, c)) for k, v in perf.by_tag.items()
        ],
        by_instrument=[
            ForexPaperGroup(key=k, summary=_summary(v, c)) for k, v in perf.by_instrument.items()
        ],
        open_positions=open_count,
    )
