"""WS /api/v1/forex/stream (P13-T02.4, design section 4.3): live updates of the pairs a client
subscribes to, fanned out from the backend's single upstream subscription.

Protocol (JSON text frames):

- client, first, within `forex_stream_auth_timeout_seconds`: `{"type": "auth", "token": "..."}`
  (the same OIDC access token as for REST) or `{"type": "auth", "ticket": "..."}` (a single-use
  ticket from `POST /api/v1/forex/stream-ticket`, valid 30 seconds, for browsers that never hold
  the token: P14-T13). Neither is ever accepted in the URL, where it would end up in logs. The
  account must exist and be enabled.
- server: `{"type": "ready", "max_instruments": n, "notice": "..."}`.
- client: `{"type": "subscribe" | "unsubscribe", "instruments": ["EUR_USD", ...]}` or
  `{"type": "ping"}`.
- server: `subscribed` (with a snapshot of each pair from storage, `unavailable` when there is
  none), `quote`, `status` (the feed's status), `heartbeat`, `pong` and `error` frames.

Close codes: 4401 not authenticated or token expired; 4404 forex switched off; 4429 too many
connections for this user or too many messages; 1009 message too large; 1008 protocol error.
Limits are per user: `forex_stream_max_connections_per_user` sockets and
`forex_stream_max_instruments` pairs per socket."""

import asyncio
import contextlib
import json
import logging
import time
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.core.api_responses import UNAUTHORIZED, not_found
from app.core.auth import AuthenticationError, TokenClaims
from app.core.config import Settings
from app.modules.forex.api import require_forex
from app.modules.forex.instruments.registry import active_instruments
from app.modules.forex.marketdata.factory import quality_policy
from app.modules.forex.marketdata.gateway import LimitExceeded, QuoteHub, Subscriber
from app.modules.forex.marketdata.schemas import NOTICE
from app.modules.forex.marketdata.service import (
    feed_status_of,
    from_received,
    quote_board,
    quote_out,
)
from app.modules.forex.marketdata.types import check_instrument
from app.modules.forex.ws_ticket import TTL_SECONDS, TicketIssuer
from app.modules.identity.dependencies import bearer
from app.modules.identity.service import CurrentUser, IdentityService, UserDisabledError
from app.modules.market_data.providers.errors import ProviderDataError

logger = logging.getLogger(__name__)
router = APIRouter()
MAX_MESSAGE_BYTES = 4096
HEARTBEAT_SECONDS = 5.0


class Close(Exception):
    def __init__(self, code: int, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


class Connection:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self._lock = asyncio.Lock()

    async def send(self, message: dict[str, Any]) -> None:
        async with self._lock:
            await self.websocket.send_text(json.dumps(message, default=str))

    async def receive(self) -> dict[str, Any]:
        raw = await self.websocket.receive_text()
        if len(raw.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise Close(1009, "message too large")
        try:
            message = json.loads(raw)
        except json.JSONDecodeError:
            raise Close(1008, "not JSON") from None
        if not isinstance(message, dict) or not isinstance(message.get("type"), str):
            raise Close(1008, "a message is an object with a type")
        return message


async def authenticate(connection: Connection, settings: Settings) -> TokenClaims:
    app = connection.websocket.app
    try:
        message = await asyncio.wait_for(
            connection.receive(), settings.forex_stream_auth_timeout_seconds
        )
    except TimeoutError:
        raise Close(4401, "authentication timed out") from None
    token = message.get("token")
    ticket = message.get("ticket")
    if message["type"] != "auth":
        raise Close(4401, "authenticate first")
    if isinstance(ticket, str) and ticket:
        issuer: TicketIssuer = app.state.forex_ticket_issuer
        redeemed = await issuer.redeem(ticket)
        if redeemed is None:
            raise Close(4401, "not authenticated")
        try:
            async with app.state.db.session_factory() as session:
                await IdentityService(session).provision(redeemed)
        except UserDisabledError:
            raise Close(4401, "not authenticated") from None
        return redeemed
    if not isinstance(token, str) or not token:
        raise Close(4401, "authenticate first")
    verifier = app.state.token_verifier
    if verifier is None:
        raise Close(4401, "authentication is not configured")
    try:
        claims: TokenClaims = await run_in_threadpool(verifier.verify, token)
        async with app.state.db.session_factory() as session:
            await IdentityService(session).provision(claims)
    except (AuthenticationError, UserDisabledError):
        raise Close(4401, "not authenticated") from None
    return claims


def _instruments(message: dict[str, Any]) -> list[str]:
    raw = message.get("instruments")
    if (
        not isinstance(raw, list)
        or not 1 <= len(raw) <= 50
        or not all(isinstance(i, str) for i in raw)
    ):
        raise ValueError("instruments must be a list of 1 to 50 pairs")
    try:
        return [check_instrument(i) for i in raw]
    except ProviderDataError:
        raise ValueError("instrument must look like EUR_USD") from None


async def read_loop(
    connection: Connection,
    subscriber: Subscriber,
    hub: QuoteHub,
    settings: Settings,
    known: set[str],
) -> None:
    app = connection.websocket.app
    recent: deque[float] = deque()
    while True:
        try:
            message = await connection.receive()
        except WebSocketDisconnect:
            return
        now = time.monotonic()
        recent.append(now)
        while recent and now - recent[0] > 60:
            recent.popleft()
        if len(recent) > settings.forex_stream_messages_per_minute:
            raise Close(4429, "too many messages")
        kind = message["type"]
        if kind == "ping":
            await connection.send({"type": "pong"})
            continue
        if kind not in ("subscribe", "unsubscribe"):
            await connection.send({"type": "error", "code": "unknown_message"})
            continue
        try:
            pairs = _instruments(message)
        except ValueError:
            await connection.send({"type": "error", "code": "invalid_instruments"})
            continue
        if kind == "unsubscribe":
            hub.unsubscribe(subscriber, pairs)
            await connection.send(
                {"type": "unsubscribed", "instruments": sorted(subscriber.instruments)}
            )
            continue
        try:
            hub.subscribe(subscriber, pairs, known)
        except LimitExceeded:
            await connection.send({"type": "error", "code": "too_many_instruments"})
            continue
        except ValueError:
            await connection.send({"type": "error", "code": "unknown_instrument"})
            continue
        async with app.state.db.session_factory() as session:
            snapshot = await quote_board(
                session,
                settings.forex_provider,
                sorted(set(pairs)),
                datetime.now(UTC),
                quality_policy(settings),
                timedelta(days=settings.forex_quote_lookback_days),
                hub,
            )
        await connection.send(
            {
                "type": "subscribed",
                "instruments": sorted(subscriber.instruments),
                "snapshot": [q.model_dump(mode="json") for q in snapshot],
            }
        )


async def write_loop(
    connection: Connection,
    subscriber: Subscriber,
    hub: QuoteHub,
    settings: Settings,
    claims: TokenClaims,
) -> None:
    policy = quality_policy(settings)
    heartbeat = connection.websocket.app.state.forex_stream_heartbeat_seconds
    while True:
        if time.time() >= claims.expires_at:
            raise Close(4401, "token expired")
        quotes, statuses = await subscriber.drain(heartbeat)
        now = datetime.now(UTC)
        for provider, status in sorted(statuses.items()):
            await connection.send({"type": "status", "provider": provider, "feed_status": status})
        feed = feed_status_of(hub, settings.forex_provider)
        for q in quotes:
            out = quote_out(q.quote.instrument, from_received(q), now, policy, feed)
            await connection.send({"type": "quote", **out.model_dump(mode="json")})
        if not quotes and not statuses:
            await connection.send({"type": "heartbeat", "ts": now.isoformat()})


@router.websocket("/api/v1/forex/stream")
async def stream(websocket: WebSocket) -> None:
    app = websocket.app
    settings: Settings = app.state.settings
    hub: QuoteHub = app.state.forex_hub
    connection = Connection(websocket)
    await websocket.accept()
    subscriber: Subscriber | None = None
    try:
        claims = await authenticate(connection, settings)
        if not settings.forex_enabled:
            raise Close(4404, "forex is switched off")
        try:
            subscriber = hub.open(f"{claims.issuer}|{claims.subject}")
        except LimitExceeded:
            raise Close(4429, "too many connections") from None
        async with app.state.db.session_factory() as session:
            known = {r.code for r in await active_instruments(session)}
        await connection.send(
            {"type": "ready", "max_instruments": hub.max_instruments, "notice": NOTICE}
        )
        reader = asyncio.create_task(read_loop(connection, subscriber, hub, settings, known))
        writer = asyncio.create_task(write_loop(connection, subscriber, hub, settings, claims))
        done, pending = await asyncio.wait({reader, writer}, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            error = task.exception()
            if error is not None:
                raise error
    except Close as close:
        logger.info("forex stream closed", extra={"code": close.code})
        with contextlib.suppress(RuntimeError):  # the client may already have gone
            await websocket.close(close.code, close.reason)
    except WebSocketDisconnect:
        pass
    finally:
        if subscriber is not None:
            hub.close(subscriber)


class StreamTicketOut(BaseModel):
    ticket: str = Field(description='Send as {"type": "auth", "ticket": ...} on the socket')
    expires_in: int = Field(description="Seconds the ticket can still be used (one use only)")


@router.post(
    "/api/v1/forex/stream-ticket",
    response_model=StreamTicketOut,
    tags=["forex"],
    responses={**UNAUTHORIZED, **not_found("forex (switched off)")},
)
async def mint_stream_ticket(
    request: Request,
    _user: Annotated[CurrentUser, Depends(require_forex)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> StreamTicketOut:
    """A single-use ticket (30 seconds) that stands for the caller on the live-quotes WebSocket,
    for clients that must not hold the access token, such as the web portal's browser. The ticket
    carries the token's own expiry and is never accepted in a URL."""
    verifier = request.app.state.token_verifier
    if credentials is None or verifier is None:  # unreachable once require_forex has passed
        raise AuthenticationError("not authenticated")
    claims: TokenClaims = await run_in_threadpool(verifier.verify, credentials.credentials)
    ticket = await request.app.state.forex_ticket_issuer.mint(claims)
    return StreamTicketOut(ticket=ticket, expires_in=TTL_SECONDS)
