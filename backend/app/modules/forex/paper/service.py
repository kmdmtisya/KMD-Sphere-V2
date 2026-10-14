"""Paper trading (P13-T09.2 to T09.4). PAPER TRADING: virtual money only, never a broker.

**Ownership.** Every read and write starts from the caller's own rows (`owned_by`, ADR-0011):
another user's account, order, position or journal entry answers 404, exactly like one that does
not exist.

**Evaluation.** Pending limit orders and open positions are checked against the stored quotes
since they were last checked, in time order, whenever the account is read and by the minute job
(`forex_paper_evaluate`). A trigger fills at the quote that caused it (`book`), and its P/L is
converted at the rates of that quote's time.

**Limits** (settings) give warnings on an order, never a silent change:
- risk per trade;
- leverage across the open positions;
- margin use;
- the realised paper loss today and this week;
- the exposure to each currency across the open positions.
An order is refused only when it cannot be filled: no fresh quote, a bad size or levels, or not
enough free margin. Margin is checked when an order is placed; a limit order that fills later
is not checked again. Positions are never closed automatically for margin: the account shows the
margin level and warns below 100%."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from typing import Literal

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import Actor, AuditWriter
from app.core.authz import owned_by, require_found
from app.core.config import Settings
from app.core.errors import ConflictError, InvalidValueError
from app.db.base import Base
from app.modules.forex.instruments.models import ForexInstrument
from app.modules.forex.instruments.registry import active_instruments
from app.modules.forex.paper import book
from app.modules.forex.paper.models import (
    ForexPaperAccount,
    ForexPaperJournalEntry,
    ForexPaperOrder,
    ForexPaperPosition,
)
from app.modules.forex.paper.quotes import latest_tick, rates_at, ticks_after
from app.modules.forex.risk.conversion import NoConversionRate, Rate, resolve
from app.modules.forex.risk.engine import Conversion
from app.modules.forex.risk.specs import ForexContractSpec, SpecValues, active_spec, values_of

D = Decimal
ZERO = D(0)
PLACES = D("0.0001")  # account-currency amounts are kept to 4 places
OrderStatus = Literal["pending", "filled", "cancelled", "rejected"]


def _q(x: Decimal) -> Decimal:
    return x.quantize(PLACES)


@dataclass(frozen=True)
class OrderRequest:
    instrument: str
    side: book.Side
    order_type: Literal["market", "limit"]
    lots: Decimal
    stop: Decimal
    target: Decimal | None
    limit_price: Decimal | None
    strategy_tag: str | None


@dataclass
class Mark:
    price: Decimal | None  # the current closing-side price; None with no quote
    unrealised: Decimal  # account currency


@dataclass
class AccountState:
    account: ForexPaperAccount
    balance: Decimal  # starting balance + realised P/L - commission paid on open positions
    unrealised: Decimal
    equity: Decimal
    used_margin: Decimal
    free_margin: Decimal
    margin_level: Decimal | None  # equity / used margin, percent
    open_notional: Decimal  # account currency, at the entry rates
    open_positions: int
    pending_orders: int
    realised_today: Decimal
    realised_this_week: Decimal
    exposure: dict[str, Decimal]  # currency -> signed amount in that currency
    marks: dict[uuid.UUID, Mark] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Placed:
    order: ForexPaperOrder
    position: ForexPaperPosition | None
    warnings: list[str]


class PaperService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.audit = AuditWriter(session)
        self.stale = timedelta(seconds=settings.forex_quote_stale_seconds)
        self.lookback = timedelta(days=settings.forex_quote_lookback_days)

    # ------------------------------------------------------------------------------ helpers
    async def _pairs(self) -> dict[str, ForexInstrument]:
        return {p.code: p for p in await active_instruments(self.session)}

    async def currencies(self) -> set[str]:
        return {c for p in (await self._pairs()).values() for c in (p.base, p.quote)}

    async def _rates(self, pairs: dict[str, ForexInstrument], at: datetime) -> dict[str, Rate]:
        return await rates_at(
            self.session,
            self.settings.forex_provider,
            list(pairs),
            {c for c, p in pairs.items() if p.liquidity_tier == "exotic"},
            at,
            self.lookback,
        )

    def _convert(self, rates: dict[str, Rate], frm: str, to: str, at: datetime) -> Conversion:
        try:
            return resolve(frm, to, rates, at, self.stale)
        except NoConversionRate as exc:
            raise InvalidValueError(str(exc)) from exc

    async def _spec(self, code: str) -> ForexContractSpec:
        spec = await active_spec(self.session, code)
        if spec is None:
            raise InvalidValueError("no contract specification for this instrument")
        return spec

    async def _count(self, model: type[Base], *where: ColumnElement[bool]) -> int:
        return int(
            await self.session.scalar(select(func.count()).select_from(model).where(*where)) or 0
        )

    # ------------------------------------------------------------------------------ accounts
    async def create_account(
        self,
        user_id: uuid.UUID,
        name: str,
        currency: str,
        starting_balance: Decimal,
        is_default: bool,
    ) -> ForexPaperAccount:
        if not name.strip():
            raise InvalidValueError("the account name must not be blank")
        if currency not in await self.currencies():
            raise InvalidValueError("the account currency must be one of the forex currencies")
        low, high = self.settings.forex_paper_min_balance, self.settings.forex_paper_max_balance
        if not low <= starting_balance <= high:
            raise InvalidValueError(f"the starting balance must be from {low} to {high}")
        active = await self._count(
            ForexPaperAccount,
            ForexPaperAccount.user_id == user_id,
            ForexPaperAccount.status == "active",
        )
        if active >= self.settings.forex_paper_max_accounts:
            raise ConflictError(
                f"at most {self.settings.forex_paper_max_accounts} active paper accounts"
            )
        row = ForexPaperAccount(
            user_id=user_id,
            name=name.strip(),
            currency=currency,
            starting_balance=_q(starting_balance),
            starting_balance_is_default=is_default,
            status="active",
        )
        self.session.add(row)
        await self.session.flush()
        await self.audit.record(
            "forex.paper.account_created",
            Actor.user(user_id),
            resource_type="forex_paper_account",
            resource_id=row.id,
        )
        await self.session.commit()
        return row

    async def accounts(self, user_id: uuid.UUID) -> list[ForexPaperAccount]:
        rows = await self.session.execute(
            owned_by(ForexPaperAccount, user_id).order_by(ForexPaperAccount.created_at)
        )
        return list(rows.scalars())

    async def account(self, user_id: uuid.UUID, account_id: uuid.UUID) -> ForexPaperAccount:
        return require_found(
            await self.session.scalar(
                owned_by(ForexPaperAccount, user_id).where(ForexPaperAccount.id == account_id)
            ),
            "paper account",
        )

    async def close_account(
        self, user_id: uuid.UUID, account_id: uuid.UUID, now: datetime
    ) -> ForexPaperAccount:
        account = await self.account(user_id, account_id)
        await self.evaluate(account, now)
        busy = await self._count(
            ForexPaperPosition,
            ForexPaperPosition.account_id == account.id,
            ForexPaperPosition.status == "open",
        )
        pending = await self._count(
            ForexPaperOrder,
            ForexPaperOrder.account_id == account.id,
            ForexPaperOrder.status == "pending",
        )
        if busy or pending:
            raise ConflictError("close the open positions and cancel the pending orders first")
        account.status = "closed"
        await self.audit.record(
            "forex.paper.account_closed",
            Actor.user(user_id),
            resource_type="forex_paper_account",
            resource_id=account.id,
        )
        await self.session.commit()
        return account

    async def _realised_since(self, account: ForexPaperAccount, since: datetime | None) -> Decimal:
        query = select(func.coalesce(func.sum(ForexPaperPosition.realised_pnl), 0)).where(
            ForexPaperPosition.account_id == account.id, ForexPaperPosition.status == "closed"
        )
        if since is not None:
            query = query.where(ForexPaperPosition.exit_at >= since)
        return D(await self.session.scalar(query) or 0)

    async def open_positions(self, account: ForexPaperAccount) -> list[ForexPaperPosition]:
        return await self._positions(account, "open")

    async def _positions(
        self, account: ForexPaperAccount, status: str | None
    ) -> list[ForexPaperPosition]:
        query = owned_by(ForexPaperPosition, account.user_id).where(
            ForexPaperPosition.account_id == account.id
        )
        if status is not None:
            query = query.where(ForexPaperPosition.status == status)
        return list(
            (await self.session.execute(query.order_by(ForexPaperPosition.created_at))).scalars()
        )

    async def state(self, account: ForexPaperAccount, now: datetime) -> AccountState:
        """Balance, equity, margin and exposure after evaluating the account."""
        await self.evaluate(account, now)
        pairs = await self._pairs()
        rates = await self._rates(pairs, now)
        open_rows = await self._positions(account, "open")
        day = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        week = day - timedelta(days=day.weekday())  # Monday 00:00 UTC
        realised = await self._realised_since(account, None)
        pending = await self._count(
            ForexPaperOrder,
            ForexPaperOrder.account_id == account.id,
            ForexPaperOrder.status == "pending",
        )
        marks: dict[uuid.UUID, Mark] = {}
        exposure: dict[str, Decimal] = {}
        warnings: list[str] = []
        with localcontext() as ctx:
            ctx.prec = 50
            unrealised = open_notional = ZERO
            for p in open_rows:
                base, quote = p.instrument[:3], p.instrument[4:]
                s = book.sign(p.side)  # type: ignore[arg-type]
                exposure[base] = exposure.get(base, ZERO) + s * p.units
                exposure[quote] = exposure.get(quote, ZERO) - s * p.units * p.entry_price
                open_notional += p.margin / (await self._margin_rate(p.instrument))
                tick = await latest_tick(
                    self.session, self.settings.forex_provider, p.instrument, now, self.lookback
                )
                if tick is None:
                    marks[p.id] = Mark(None, ZERO)
                    warnings.append(f"{p.instrument}: no quote to value the open position")
                    continue
                price = book.closing_price(p.side, tick)  # type: ignore[arg-type]
                rate = self._convert(rates, quote, account.currency, now).rate
                value = book.pnl_quote(p.side, p.units, p.entry_price, price) * rate  # type: ignore[arg-type]
                marks[p.id] = Mark(price, _q(value))
                unrealised += value
            balance = (
                account.starting_balance
                + realised
                - sum((p.entry_commission for p in open_rows), ZERO)
            )
            used = sum((p.margin for p in open_rows), ZERO)
            equity = balance + unrealised
            level = equity / used * 100 if used > 0 else None
        if level is not None and level < 100:
            warnings.append(
                f"Margin level {level:.0f}%: a broker would ask for more margin below 100% and "
                "close positions below about 50%. Paper positions are not closed automatically."
            )
        return AccountState(
            account=account,
            balance=_q(balance),
            unrealised=_q(unrealised),
            equity=_q(equity),
            used_margin=_q(used),
            free_margin=_q(equity - used),
            margin_level=None if level is None else level.quantize(D("0.01")),
            open_notional=_q(open_notional),
            open_positions=len(open_rows),
            pending_orders=pending,
            realised_today=_q(await self._realised_since(account, day)),
            realised_this_week=_q(await self._realised_since(account, week)),
            exposure=exposure,
            marks=marks,
            warnings=warnings,
        )

    async def _margin_rate(self, code: str) -> Decimal:
        return (await self._spec(code)).margin_rate

    # -------------------------------------------------------------------------------- orders
    async def place(
        self, user_id: uuid.UUID, account_id: uuid.UUID, req: OrderRequest, now: datetime
    ) -> Placed:
        account = await self.account(user_id, account_id)
        if account.status != "active":
            raise ConflictError("the paper account is closed")
        pairs = await self._pairs()
        pair = pairs.get(req.instrument)
        if pair is None:
            raise InvalidValueError("unknown or inactive instrument")
        spec_row = await self._spec(pair.code)
        spec = values_of(spec_row)
        try:
            units = book.units_for(req.lots, spec)
        except ValueError as exc:
            raise InvalidValueError(str(exc)) from exc
        tick = await latest_tick(
            self.session, self.settings.forex_provider, pair.code, now, self.stale
        )
        if tick is None:
            raise InvalidValueError(
                "no fresh quote for this pair: a paper order fills only at a live bid or ask"
            )
        slip = book.slippage(spec, pair.pip_location)
        if req.order_type == "market":
            if req.limit_price is not None:
                raise InvalidValueError("a market order takes no limit price")
            reference = book.market_entry(req.side, tick, slip)
        else:
            if req.limit_price is None:
                raise InvalidValueError("a limit order needs a limit price")
            if (req.side == "long" and req.limit_price >= tick.ask) or (
                req.side == "short" and req.limit_price <= tick.bid
            ):
                raise InvalidValueError("the limit price is already reached: use a market order")
            reference = req.limit_price
        try:
            book.check_levels(req.side, reference, req.stop, req.target)
        except ValueError as exc:
            raise InvalidValueError(str(exc)) from exc
        state = await self.state(account, now)
        rates = await self._rates(pairs, now)
        with localcontext() as ctx:
            ctx.prec = 50
            rate = self._convert(rates, pair.quote, account.currency, now).rate
            notional = units * reference * rate
            margin = notional * spec.margin_rate
            risk = (abs(reference - req.stop) * units + 2 * book.commission(units, spec)) * rate
            delta = {
                pair.base: book.sign(req.side) * units,
                pair.quote: -book.sign(req.side) * units * reference,
            }
            shares = {}
            for currency, change in delta.items():
                if currency == account.currency or state.equity <= 0:
                    continue
                after = state.exposure.get(currency, ZERO) + change
                value = abs(after) * self._convert(rates, currency, account.currency, now).rate
                shares[currency] = value / state.equity * 100
        if margin > state.free_margin:
            raise InvalidValueError(
                "not enough free paper margin for this order "
                f"(needs {_q(margin)} {account.currency}, free {state.free_margin})"
            )
        warnings = self._warnings(
            state, pair, spec_row, tick.data_type, notional, margin, risk, shares
        )
        order = ForexPaperOrder(
            account_id=account.id,
            user_id=user_id,
            instrument=pair.code,
            side=req.side,
            order_type=req.order_type,
            lots=req.lots,
            units=units,
            limit_price=req.limit_price,
            stop=req.stop,
            target=req.target,
            status="pending",
            strategy_tag=req.strategy_tag,
            spec_version=spec_row.version,
            checked_until=tick.at,
        )
        self.session.add(order)
        await self.session.flush()
        position = None
        if req.order_type == "market":
            position = await self._fill(account, order, pair, spec, tick, reference, rates)
        await self.audit.record(
            "forex.paper.order_placed",
            Actor.user(user_id),
            resource_type="forex_paper_order",
            resource_id=order.id,
            details={"instrument": pair.code, "order_type": req.order_type},
        )
        await self.session.commit()
        return Placed(order, position, warnings)

    def _warnings(
        self,
        state: AccountState,
        pair: ForexInstrument,
        spec_row: ForexContractSpec,
        data_type: str,
        notional: Decimal,
        margin: Decimal,
        risk: Decimal,
        shares: dict[str, Decimal],
    ) -> list[str]:
        s = self.settings
        if state.equity <= 0:
            return ["The paper account has no equity left."]
        out: list[str] = []
        with localcontext() as ctx:
            ctx.prec = 50
            risk_pct = risk / state.equity * 100
            leverage = (state.open_notional + notional) / state.equity
            margin_use = (state.used_margin + margin) / state.equity * 100
        if risk_pct > s.forex_risk_max_percent:
            out.append(
                f"Risk at the stop is {risk_pct:.2f}% of equity, above the "
                f"{s.forex_risk_max_percent}% limit."
            )
        if leverage > s.forex_risk_max_leverage:
            out.append(
                f"Leverage would be {leverage:.2f}x, above the {s.forex_risk_max_leverage}x limit."
            )
        if margin_use > s.forex_risk_max_margin_use_percent:
            out.append(
                f"Margin would use {margin_use:.2f}% of equity, above the "
                f"{s.forex_risk_max_margin_use_percent}% limit."
            )
        start = state.account.starting_balance
        if -state.realised_today >= start * s.forex_paper_max_daily_loss_percent / 100:
            out.append(
                "Today's realised paper loss has reached the "
                f"{s.forex_paper_max_daily_loss_percent}% daily limit."
            )
        if -state.realised_this_week >= start * s.forex_paper_max_weekly_loss_percent / 100:
            out.append(
                "This week's realised paper loss has reached the "
                f"{s.forex_paper_max_weekly_loss_percent}% weekly limit."
            )
        for currency, share in sorted(shares.items()):
            if share > s.forex_paper_max_currency_exposure_percent:
                out.append(
                    f"{currency} exposure would be {share:.0f}% of equity, above the "
                    f"{s.forex_paper_max_currency_exposure_percent}% limit."
                )
        if data_type != "tradable_quote":
            out.append(f"The price is a {data_type} quote, not a tradable one.")
        if spec_row.review_status != "reviewed":
            out.append("The contract specification is an unreviewed default, not a broker's terms.")
        if pair.liquidity_tier == "exotic":
            out.append("A less liquid pair: spreads, slippage and gaps can be much larger.")
        return out

    async def _fill(
        self,
        account: ForexPaperAccount,
        order: ForexPaperOrder,
        pair: ForexInstrument,
        spec: SpecValues,
        tick: book.Tick,
        price: Decimal,
        rates: dict[str, Rate],
    ) -> ForexPaperPosition:
        with localcontext() as ctx:
            ctx.prec = 50
            rate = self._convert(rates, pair.quote, account.currency, tick.at).rate
            margin = order.units * price * rate * spec.margin_rate
            commission = book.commission(order.units, spec) * rate
        order.status, order.filled_at, order.checked_until = "filled", tick.at, tick.at
        position = ForexPaperPosition(
            account_id=account.id,
            user_id=account.user_id,
            order_id=order.id,
            instrument=order.instrument,
            side=order.side,
            lots=order.lots,
            units=order.units,
            entry_price=price,
            entry_mid=tick.mid,
            entry_quote_at=tick.at,
            data_type=tick.data_type,
            stop=order.stop,
            target=order.target,
            margin=_q(margin),
            entry_commission=_q(commission),
            strategy_tag=order.strategy_tag,
            status="open",
            checked_until=tick.at,
        )
        self.session.add(position)
        await self.session.flush()
        return position

    async def orders(
        self, user_id: uuid.UUID, account_id: uuid.UUID, status: OrderStatus | None, now: datetime
    ) -> list[ForexPaperOrder]:
        account = await self.account(user_id, account_id)
        await self.evaluate(account, now)
        query = owned_by(ForexPaperOrder, user_id).where(ForexPaperOrder.account_id == account.id)
        if status is not None:
            query = query.where(ForexPaperOrder.status == status)
        return list(
            (await self.session.execute(query.order_by(ForexPaperOrder.created_at))).scalars()
        )

    async def cancel(
        self, user_id: uuid.UUID, account_id: uuid.UUID, order_id: uuid.UUID, now: datetime
    ) -> ForexPaperOrder:
        account = await self.account(user_id, account_id)
        await self.evaluate(account, now)
        order = require_found(
            await self.session.scalar(
                owned_by(ForexPaperOrder, user_id).where(
                    ForexPaperOrder.id == order_id, ForexPaperOrder.account_id == account.id
                )
            ),
            "paper order",
        )
        if order.status != "pending":
            raise ConflictError(f"the order is {order.status}, not pending")
        order.status, order.cancelled_at = "cancelled", now
        await self.audit.record(
            "forex.paper.order_cancelled",
            Actor.user(user_id),
            resource_type="forex_paper_order",
            resource_id=order.id,
        )
        await self.session.commit()
        return order

    # ----------------------------------------------------------------------------- positions
    async def position(
        self, account: ForexPaperAccount, position_id: uuid.UUID
    ) -> ForexPaperPosition:
        return require_found(
            await self.session.scalar(
                owned_by(ForexPaperPosition, account.user_id).where(
                    ForexPaperPosition.id == position_id,
                    ForexPaperPosition.account_id == account.id,
                )
            ),
            "paper position",
        )

    async def positions(
        self, user_id: uuid.UUID, account_id: uuid.UUID, status: str | None, now: datetime
    ) -> tuple[AccountState, list[ForexPaperPosition]]:
        account = await self.account(user_id, account_id)
        state = await self.state(account, now)
        return state, await self._positions(account, status)

    async def close(
        self, user_id: uuid.UUID, account_id: uuid.UUID, position_id: uuid.UUID, now: datetime
    ) -> ForexPaperPosition:
        account = await self.account(user_id, account_id)
        await self.evaluate(account, now)
        p = await self.position(account, position_id)
        if p.status != "open":
            raise ConflictError("the position is already closed")
        pairs = await self._pairs()
        pair = pairs.get(p.instrument)
        tick = await latest_tick(
            self.session, self.settings.forex_provider, p.instrument, now, self.stale
        )
        if tick is None or pair is None:
            raise InvalidValueError(
                "no fresh quote for this pair: a paper position closes only at a live bid or ask"
            )
        spec = values_of(await self._spec(p.instrument))
        price = book.market_exit(p.side, tick, book.slippage(spec, pair.pip_location))  # type: ignore[arg-type]
        await self._close(
            account, p, pair, spec, book.Exit(tick, price, "manual"), Actor.user(user_id)
        )
        await self.session.commit()
        return p

    async def set_levels(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        position_id: uuid.UUID,
        stop: Decimal,
        target: Decimal | None,
        now: datetime,
    ) -> ForexPaperPosition:
        account = await self.account(user_id, account_id)
        await self.evaluate(account, now)
        p = await self.position(account, position_id)
        if p.status != "open":
            raise ConflictError("the position is already closed")
        tick = await latest_tick(
            self.session, self.settings.forex_provider, p.instrument, now, self.stale
        )
        if tick is None:
            raise InvalidValueError("no fresh quote for this pair")
        reference = book.closing_price(p.side, tick)  # type: ignore[arg-type]
        try:
            book.check_levels(p.side, reference, stop, target)  # type: ignore[arg-type]
        except ValueError as exc:
            raise InvalidValueError(f"{exc} (the current closing price is {reference})") from exc
        p.stop, p.target = stop, target
        await self.audit.record(
            "forex.paper.levels_changed",
            Actor.user(user_id),
            resource_type="forex_paper_position",
            resource_id=p.id,
        )
        await self.session.commit()
        return p

    async def _close(
        self,
        account: ForexPaperAccount,
        p: ForexPaperPosition,
        pair: ForexInstrument,
        spec: SpecValues,
        exit_: book.Exit,
        actor: Actor,
    ) -> None:
        rates = await self._rates(await self._pairs(), exit_.tick.at)
        conv = self._convert(rates, pair.quote, account.currency, exit_.tick.at)
        side: book.Side = "long" if p.side == "long" else "short"
        with localcontext() as ctx:
            ctx.prec = 50
            rate = conv.rate
            gross = book.pnl_quote(side, p.units, p.entry_price, exit_.price) * rate
            exit_commission = book.commission(p.units, spec) * rate
            paid = (
                book.spread_and_slippage(p.units, p.entry_price, p.entry_mid)
                + book.spread_and_slippage(p.units, exit_.price, exit_.tick.mid)
            ) * rate
        p.status = "closed"
        p.exit_price = exit_.price
        p.exit_at = exit_.tick.at
        p.exit_reason = exit_.reason
        p.exit_rate = rate.quantize(D("1E-15"))
        p.exit_rate_path = conv.path[:80]
        p.realised_pnl = _q(gross - p.entry_commission - exit_commission)
        p.costs = _q(paid + p.entry_commission + exit_commission)
        p.checked_until = exit_.tick.at
        await self.audit.record(
            "forex.paper.position_closed",
            actor,
            resource_type="forex_paper_position",
            resource_id=p.id,
            details={"reason": exit_.reason},
        )

    # ---------------------------------------------------------------------------- evaluation
    async def evaluate(self, account: ForexPaperAccount, now: datetime) -> int:
        """Fills pending limit orders and triggers stops and targets from the quotes since each
        was last checked. Returns the number of fills and exits. Commits."""
        pairs = await self._pairs()
        provider = self.settings.forex_provider
        changed = 0
        pending = (
            await self.session.execute(
                owned_by(ForexPaperOrder, account.user_id)
                .where(
                    ForexPaperOrder.account_id == account.id, ForexPaperOrder.status == "pending"
                )
                .order_by(ForexPaperOrder.created_at)
            )
        ).scalars()
        for order in list(pending):
            pair = pairs.get(order.instrument)
            if pair is None or order.limit_price is None:
                continue
            ticks = await ticks_after(
                self.session, provider, order.instrument, order.checked_until, now
            )
            side: book.Side = "long" if order.side == "long" else "short"
            hit = book.limit_fill(side, order.limit_price, ticks)
            if hit is None:
                if ticks:
                    order.checked_until = ticks[-1].at
                continue
            spec = values_of(await self._spec(order.instrument))
            rates = await self._rates(pairs, hit.at)
            await self._fill(account, order, pair, spec, hit, order.limit_price, rates)
            changed += 1
        for p in await self._positions(account, "open"):
            pair = pairs.get(p.instrument)
            if pair is None:
                continue
            ticks = await ticks_after(self.session, provider, p.instrument, p.checked_until, now)
            if not ticks:
                continue
            spec = values_of(await self._spec(p.instrument))
            side = "long" if p.side == "long" else "short"
            hit_exit = book.exit_for(
                side, p.stop, p.target, ticks, book.slippage(spec, pair.pip_location)
            )
            if hit_exit is None:
                p.checked_until = ticks[-1].at
                continue
            await self._close(account, p, pair, spec, hit_exit, Actor.system())
            changed += 1
        await self.session.commit()
        return changed

    # ------------------------------------------------------------------------------- journal
    async def add_note(
        self,
        user_id: uuid.UUID,
        account_id: uuid.UUID,
        note: str,
        tags: Sequence[str],
        position_id: uuid.UUID | None,
    ) -> ForexPaperJournalEntry:
        account = await self.account(user_id, account_id)
        if position_id is not None:
            await self.position(account, position_id)  # 404 unless it is this account's
        row = ForexPaperJournalEntry(
            account_id=account.id,
            user_id=user_id,
            position_id=position_id,
            note=note.strip(),
            tags=sorted({t.strip().lower() for t in tags if t.strip()}),
        )
        self.session.add(row)
        await self.session.commit()
        return row

    async def journal(
        self, user_id: uuid.UUID, account_id: uuid.UUID, tag: str | None
    ) -> list[ForexPaperJournalEntry]:
        account = await self.account(user_id, account_id)
        query = owned_by(ForexPaperJournalEntry, user_id).where(
            ForexPaperJournalEntry.account_id == account.id
        )
        if tag is not None:
            query = query.where(ForexPaperJournalEntry.tags.contains([tag.strip().lower()]))
        rows = await self.session.execute(query.order_by(ForexPaperJournalEntry.created_at.desc()))
        return list(rows.scalars())

    async def delete_note(
        self, user_id: uuid.UUID, account_id: uuid.UUID, entry_id: uuid.UUID
    ) -> None:
        account = await self.account(user_id, account_id)
        row = require_found(
            await self.session.scalar(
                owned_by(ForexPaperJournalEntry, user_id).where(
                    ForexPaperJournalEntry.id == entry_id,
                    ForexPaperJournalEntry.account_id == account.id,
                )
            ),
            "journal entry",
        )
        await self.session.delete(row)
        await self.session.commit()

    async def closed(
        self, user_id: uuid.UUID, account_id: uuid.UUID, now: datetime
    ) -> tuple[ForexPaperAccount, list[ForexPaperPosition]]:
        account = await self.account(user_id, account_id)
        await self.evaluate(account, now)
        rows = await self.session.execute(
            owned_by(ForexPaperPosition, user_id)
            .where(
                ForexPaperPosition.account_id == account.id, ForexPaperPosition.status == "closed"
            )
            .order_by(ForexPaperPosition.exit_at, ForexPaperPosition.id)
        )
        return account, list(rows.scalars())


async def accounts_to_evaluate(session: AsyncSession) -> list[ForexPaperAccount]:
    """Every active account with an open position or a pending order (for the minute job)."""
    busy = select(ForexPaperPosition.account_id).where(ForexPaperPosition.status == "open")
    waiting = select(ForexPaperOrder.account_id).where(ForexPaperOrder.status == "pending")
    rows = await session.execute(
        select(ForexPaperAccount).where(
            ForexPaperAccount.status == "active",
            ForexPaperAccount.id.in_(busy.union(waiting)),
        )
    )
    return list(rows.scalars())
