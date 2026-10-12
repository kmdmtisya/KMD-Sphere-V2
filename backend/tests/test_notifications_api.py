"""Devices and alert push payloads (P09-T08, ADR-0016)."""

import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from app.modules.alerts.evaluation import evaluate_alerts
from app.modules.notifications.push import (
    ALERTS_ROUTE,
    NullPushSender,
    PushTarget,
    build_push_sender,
)
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, assert_hidden_from, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
NOW = datetime.now(UTC).replace(microsecond=0)
TOKEN = "fcm-token-abcdef0123456789"


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    application = create_app(migrated_settings, readiness_checks={}, token_verifier=ah.verifier())
    yield application
    await application.state.db.dispose()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture(scope="module")
async def db(migrated_settings: Settings) -> AsyncIterator[asyncpg.Connection]:  # noqa: F811
    conn = await asyncpg.connect(migrated_settings.database_dsn, timeout=5)
    yield conn
    await conn.close()


async def register(
    http: httpx.AsyncClient, h: dict[str, str], token: str = TOKEN, platform: str = "android"
) -> httpx.Response:
    return await http.post(
        "/api/v1/devices", headers=h, json={"platform": platform, "token": token}
    )


# ---------------------------------------------------------------------------------- devices
async def test_register_refresh_list_and_remove(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    first = await register(http, h)
    assert first.status_code == 201
    again = await register(http, h, platform="ios")
    assert again.status_code == 200
    assert again.json()["id"] == first.json()["id"]
    listed = (await http.get("/api/v1/devices", headers=h)).json()
    assert [d["platform"] for d in listed] == ["ios"]
    assert listed[0]["token_hint"] == TOKEN[-6:]
    assert TOKEN not in str(listed), "the full token is never returned"
    gone = await http.delete(f"/api/v1/devices/{first.json()['id']}", headers=h)
    assert gone.status_code == 204
    assert (await http.get("/api/v1/devices", headers=h)).json() == []


async def test_the_same_token_for_two_users_is_two_devices(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    assert (await register(http, two_users.alice.headers)).status_code == 201
    assert (await register(http, two_users.bob.headers)).status_code == 201
    bobs = (await http.get("/api/v1/devices", headers=two_users.bob.headers)).json()
    assert len(bobs) == 1


@pytest.mark.parametrize(
    "body",
    [
        {"platform": "windows", "token": TOKEN},
        {"platform": "android", "token": "short"},
        {"platform": "android", "token": "has spaces in it"},
        {"platform": "android", "token": TOKEN, "extra": 1},
    ],
)
async def test_a_bad_registration_is_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    body: dict[str, object],
) -> None:
    r = await http.post("/api/v1/devices", headers=two_users.alice.headers, json=body)
    assert r.status_code == 422


async def test_at_most_ten_devices(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    for i in range(10):
        assert (await register(http, h, token=f"{TOKEN}-{i}")).status_code == 201
    assert (await register(http, h, token=f"{TOKEN}-x")).status_code == 409


async def test_bob_cannot_remove_alices_device(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    device = (await register(http, two_users.alice.headers)).json()
    await assert_hidden_from(http, two_users.bob, "DELETE", f"/api/v1/devices/{device['id']}")
    assert len((await http.get("/api/v1/devices", headers=two_users.alice.headers)).json()) == 1


async def test_registrations_are_audited_without_the_token(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    device = (await register(http, two_users.alice.headers)).json()
    rows = await db.fetch(
        "SELECT action, details::text AS details FROM audit_events WHERE resource_id = $1",
        device["id"],
    )
    assert [r["action"] for r in rows] == ["notifications.device.registered"]
    assert TOKEN not in rows[0]["details"]


@pytest.mark.parametrize(
    ("method", "path"), [("GET", "/api/v1/devices"), ("POST", "/api/v1/devices")]
)
async def test_a_signed_in_user_is_required(
    http: httpx.AsyncClient, method: str, path: str
) -> None:
    assert (await http.request(method, path)).status_code == 401


# ------------------------------------------------------------------------------------ push
async def listed(db: asyncpg.Connection) -> str:
    cls = await db.fetchval("SELECT id FROM asset_classes WHERE code = 'stock'")
    return str(
        await db.fetchval(
            "INSERT INTO assets (asset_class_id, symbol, name, currency) "
            "VALUES ($1, $2, $2, 'USD') RETURNING id",
            cls,
            f"N{uuid.uuid4().hex[:6].upper()}",
        )
    )


async def put_price(db: asyncpg.Connection, asset: str, value: str, as_of: datetime) -> None:
    await db.execute(
        "INSERT INTO market_prices (asset_id, price, currency, price_type, provider, as_of, "
        "retrieved_at) VALUES ($1, $2, 'USD', 'quote', 'fake', $3, $3)",
        uuid.UUID(asset),
        Decimal(value),
        as_of,
    )


async def evaluate(app: FastAPI, sender: object) -> None:
    async with app.state.db.session_factory() as session:
        await evaluate_alerts(session, sender=sender)  # type: ignore[arg-type]


async def test_a_fired_alert_is_pushed_with_ids_and_a_route_only(
    http: httpx.AsyncClient,
    app: FastAPI,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    phone = (await register(http, h, token=f"{TOKEN}-phone")).json()
    tablet = (await register(http, h, token=f"{TOKEN}-tablet", platform="ios")).json()
    asset = await listed(db)
    alert = (
        await http.post(
            "/api/v1/alerts",
            headers=h,
            json={
                "alert_type": "price_above",
                "asset_id": asset,
                "threshold_price": {"amount": "100", "currency": "USD"},
            },
        )
    ).json()
    await put_price(db, asset, "987.65", NOW - timedelta(minutes=5))
    sender = NullPushSender()
    await evaluate(app, sender)
    mine = [(d, p) for d, p in sender.sent if p["alert_id"] == alert["id"]]
    assert {str(d) for d, _ in mine} == {phone["id"], tablet["id"]}
    payload = mine[0][1]
    assert set(payload) == {"type", "alert_id", "event_id", "route"}
    assert payload["type"] == "alert_triggered"
    assert payload["route"] == ALERTS_ROUTE
    assert "987" not in str(payload) and "100" not in str(payload), "no amounts in a payload"
    event = (await http.get("/api/v1/alerts/events", headers=h)).json()["items"][0]
    assert payload["event_id"] == event["id"]

    again = NullPushSender()
    await evaluate(app, again)
    assert not [p for _, p in again.sent if p["alert_id"] == alert["id"]], "fires once"


async def test_one_failing_device_does_not_stop_the_others(
    http: httpx.AsyncClient,
    app: FastAPI,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.bob.headers
    await register(http, h, token=f"{TOKEN}-bad")
    await register(http, h, token=f"{TOKEN}-good")
    asset = await listed(db)
    await http.post(
        "/api/v1/alerts",
        headers=h,
        json={
            "alert_type": "price_below",
            "asset_id": asset,
            "threshold_price": {"amount": "50", "currency": "USD"},
        },
    )
    await put_price(db, asset, "10", NOW - timedelta(minutes=5))

    class Flaky:
        def __init__(self) -> None:
            self.delivered: list[str] = []

        async def send(self, target: PushTarget, payload: Mapping[str, str]) -> None:
            if target.token.endswith("-bad"):
                raise ConnectionError("unreachable")
            self.delivered.append(target.token)

    sender = Flaky()
    await evaluate(app, sender)
    assert f"{TOKEN}-good" in sender.delivered


def test_the_worker_sends_nothing_until_fcm_is_configured() -> None:
    assert isinstance(build_push_sender(), NullPushSender)
