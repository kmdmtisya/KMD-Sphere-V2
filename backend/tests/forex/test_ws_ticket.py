"""Single-use WebSocket tickets (P14-T13.2): the store and issuer rules, and the ticket through
the API and the real forex socket."""

import time
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.core.auth import TokenClaims
from app.core.config import Settings
from app.main import create_app
from app.modules.forex.ws_ticket import MemoryTicketStore, TicketIssuer
from tests import auth_helpers as ah
from tests.authz_harness import TestUser, make_user
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.forex.ws import AsgiWebSocket


def claims(expires_in: int = 600) -> TokenClaims:
    return TokenClaims(
        issuer="https://idp.test",
        subject="user-1",
        email="a@example.test",
        email_verified=True,
        authorized_party="wealthsphere-web",
        roles=frozenset({"user"}),
        expires_at=int(time.time()) + expires_in,
    )


# ------------------------------------------------------------------------------ unit
async def test_a_ticket_stands_for_the_caller_once() -> None:
    issuer = TicketIssuer(MemoryTicketStore())
    ticket = await issuer.mint(claims())
    first = await issuer.redeem(ticket)
    assert first is not None and first.subject == "user-1" and first.roles == frozenset({"user"})
    assert first.authorized_party == "wealthsphere-web"
    assert await issuer.redeem(ticket) is None  # one use only


async def test_unknown_and_expired_tickets_are_refused() -> None:
    clock = [0.0]
    store = MemoryTicketStore(clock=lambda: clock[0])
    issuer = TicketIssuer(store)
    assert await issuer.redeem("never-issued") is None
    ticket = await issuer.mint(claims())
    clock[0] += 31  # past the 30 seconds
    assert await issuer.redeem(ticket) is None


async def test_a_ticket_never_outlives_the_token_it_came_from() -> None:
    issuer = TicketIssuer(MemoryTicketStore(), clock=lambda: time.time() + 120)
    ticket = await issuer.mint(claims(expires_in=60))
    assert await issuer.redeem(ticket) is None


async def test_tickets_are_unique_and_only_a_hash_is_stored() -> None:
    store = MemoryTicketStore()
    issuer = TicketIssuer(store)
    a, b = await issuer.mint(claims()), await issuer.mint(claims())
    assert a != b and len(a) >= 43
    assert all(a not in key and b not in key for key in store._items)


# ----------------------------------------------------------------------- API and socket


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    settings = migrated_settings.model_copy(update={"forex_enabled": True})
    application = create_app(settings, readiness_checks={}, token_verifier=ah.verifier())
    application.state.forex_stream_heartbeat_seconds = 0.05
    yield application
    await application.state.db.dispose()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.integration
@pytest.mark.security
async def test_a_ticket_opens_the_socket_once_and_never_via_the_url(
    app: FastAPI, http: httpx.AsyncClient
) -> None:
    user: TestUser = await make_user(http, "ticketed")
    assert (await http.post("/api/v1/forex/stream-ticket")).status_code == 401
    response = await http.post("/api/v1/forex/stream-ticket", headers=user.headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["expires_in"] == 30 and len(body["ticket"]) >= 43

    async with AsgiWebSocket(app) as ws:
        await ws.send({"type": "auth", "ticket": body["ticket"]})
        ready = await ws.receive_type("ready")
        assert ready["max_instruments"] > 0
    # The same ticket a second time is refused.
    async with AsgiWebSocket(app) as ws:
        await ws.send({"type": "auth", "ticket": body["ticket"]})
        assert await ws.closed_with() == 4401
    # A made-up ticket is refused.
    async with AsgiWebSocket(app) as ws:
        await ws.send({"type": "auth", "ticket": "x" * 43})
        assert await ws.closed_with() == 4401


@pytest.mark.integration
@pytest.mark.security
async def test_the_ticket_route_is_off_when_forex_is_off(migrated_settings: Settings) -> None:  # noqa: F811
    off = create_app(
        migrated_settings.model_copy(update={"forex_enabled": False}),
        readiness_checks={},
        token_verifier=ah.verifier(),
    )
    try:
        transport = httpx.ASGITransport(app=off, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            someone = await make_user(client, "no-forex")
            r = await client.post("/api/v1/forex/stream-ticket", headers=someone.headers)
            assert r.status_code == 404
    finally:
        await off.state.db.dispose()
