"""Watchlist, alerts, preferences and alert evaluation (P08-T07)."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from app.modules.alerts.evaluation import evaluate_alerts
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, assert_hidden_from, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
NOW = datetime.now(UTC).replace(microsecond=0)


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


async def listed(db: asyncpg.Connection, currency: str = "USD") -> str:
    cls = await db.fetchval("SELECT id FROM asset_classes WHERE code = 'stock'")
    return str(
        await db.fetchval(
            "INSERT INTO assets (asset_class_id, symbol, name, currency) "
            "VALUES ($1, $2, $2, $3) RETURNING id",
            cls,
            f"W{uuid.uuid4().hex[:6].upper()}",
            currency,
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


def price_alert(asset: str, kind: str = "price_above", threshold: str = "100") -> dict[str, Any]:
    return {
        "alert_type": kind,
        "asset_id": asset,
        "threshold_price": {"amount": threshold, "currency": "USD"},
    }


async def make_alert(http: httpx.AsyncClient, h: dict[str, str], body: dict[str, Any]) -> Any:
    r = await http.post("/api/v1/alerts", headers=h, json=body)
    assert r.status_code == 201, r.text
    return r.json()


async def run_evaluation(app: FastAPI, now: datetime | None = None) -> Any:
    async with app.state.db.session_factory() as session:
        return await evaluate_alerts(session, now)


async def status_of(http: httpx.AsyncClient, h: dict[str, str], alert_id: str) -> str:
    return str((await http.get(f"/api/v1/alerts/{alert_id}", headers=h)).json()["status"])


# ------------------------------------------------------------------------------- watchlist
async def test_watchlist_add_list_remove(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    asset = await listed(db)
    await put_price(db, asset, "123.45", NOW - timedelta(hours=1))
    first = await http.post("/api/v1/watchlist", headers=h, json={"asset_id": asset})
    assert first.status_code == 201
    again = await http.post("/api/v1/watchlist", headers=h, json={"asset_id": asset})
    assert again.status_code == 200
    items = (await http.get("/api/v1/watchlist", headers=h)).json()
    assert [i["asset"]["id"] for i in items] == [asset]
    assert items[0]["latest_price"]["price"] == {"amount": "123.45", "currency": "USD"}
    assert items[0]["latest_price"]["stale"] is False
    assert (await http.delete(f"/api/v1/watchlist/{asset}", headers=h)).status_code == 204
    assert (await http.get("/api/v1/watchlist", headers=h)).json() == []
    assert (await http.delete(f"/api/v1/watchlist/{asset}", headers=h)).status_code == 404


async def test_a_watched_asset_without_a_price_shows_none(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    asset = await listed(db)
    await http.post("/api/v1/watchlist", headers=h, json={"asset_id": asset})
    assert (await http.get("/api/v1/watchlist", headers=h)).json()[0]["latest_price"] is None


async def test_an_unknown_asset_cannot_be_watched(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    r = await http.post(
        "/api/v1/watchlist", headers=two_users.alice.headers, json={"asset_id": str(uuid.uuid4())}
    )
    assert r.status_code == 422


async def test_bobs_private_asset_cannot_be_watched_by_alice(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    made = await http.post(
        "/api/v1/assets",
        headers=two_users.bob.headers,
        json={"asset_class": "real_estate", "name": "Bob's flat", "currency": "USD"},
    )
    r = await http.post(
        "/api/v1/watchlist", headers=two_users.alice.headers, json={"asset_id": made.json()["id"]}
    )
    assert r.status_code == 422


async def test_watchlists_are_separate(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    asset = await listed(db)
    await http.post("/api/v1/watchlist", headers=two_users.alice.headers, json={"asset_id": asset})
    assert (await http.get("/api/v1/watchlist", headers=two_users.bob.headers)).json() == []


async def test_bob_cannot_remove_alices_watchlist_item(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    asset = await listed(db)
    await http.post("/api/v1/watchlist", headers=two_users.alice.headers, json={"asset_id": asset})
    await assert_hidden_from(http, two_users.bob, "DELETE", f"/api/v1/watchlist/{asset}")
    assert len((await http.get("/api/v1/watchlist", headers=two_users.alice.headers)).json()) == 1


# --------------------------------------------------------------------------------- alerts
async def test_create_list_update_delete_an_alert(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    asset = await listed(db)
    alert = await make_alert(http, h, {**price_alert(asset), "note": "  sell above  "})
    assert alert["status"] == "active"
    assert alert["note"] == "sell above"
    assert alert["threshold_price"] == {"amount": "100.00", "currency": "USD"}
    assert [a["id"] for a in (await http.get("/api/v1/alerts", headers=h)).json()] == [alert["id"]]
    paused = await http.patch(f"/api/v1/alerts/{alert['id']}", headers=h, json={"status": "paused"})
    assert paused.json()["status"] == "paused"
    moved = await http.patch(
        f"/api/v1/alerts/{alert['id']}",
        headers=h,
        json={"threshold_price": {"amount": "150", "currency": "USD"}},
    )
    assert moved.json()["threshold_price"]["amount"] == "150.00"
    assert (await http.delete(f"/api/v1/alerts/{alert['id']}", headers=h)).status_code == 204
    assert (await http.get(f"/api/v1/alerts/{alert['id']}", headers=h)).status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"alert_type": "price_above"},
        {"alert_type": "price_above", "asset_id": str(uuid.uuid4())},
        {"alert_type": "allocation_above", "asset_class": "stock", "threshold_percent": "50"},
        {
            "alert_type": "allocation_above",
            "portfolio_id": str(uuid.uuid4()),
            "asset_class": "stock",
            "threshold_percent": "101",
        },
        {
            "alert_type": "price_above",
            "asset_id": str(uuid.uuid4()),
            "threshold_price": {"amount": "0", "currency": "USD"},
        },
    ],
)
async def test_a_malformed_alert_is_rejected(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    body: dict[str, Any],
) -> None:
    r = await http.post("/api/v1/alerts", headers=two_users.alice.headers, json=body)
    assert r.status_code == 422


async def test_the_threshold_must_be_in_the_assets_currency(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    asset = await listed(db, "USD")
    body = price_alert(asset)
    body["threshold_price"]["currency"] = "EUR"
    r = await http.post("/api/v1/alerts", headers=two_users.alice.headers, json=body)
    assert r.status_code == 422


async def test_an_allocation_alert_needs_the_users_own_portfolio(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    bobs = await http.post(
        "/api/v1/portfolios",
        headers=two_users.bob.headers,
        json={"name": "Bob P", "base_currency": "USD"},
    )
    r = await http.post(
        "/api/v1/alerts",
        headers=two_users.alice.headers,
        json={
            "alert_type": "allocation_above",
            "portfolio_id": bobs.json()["id"],
            "asset_class": "stock",
            "threshold_percent": "50",
        },
    )
    assert r.status_code == 422


async def test_the_alert_limit(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    asset = await listed(db)
    for _ in range(50):
        await make_alert(http, h, price_alert(asset))
    r = await http.post("/api/v1/alerts", headers=h, json=price_alert(asset))
    assert r.status_code == 409
    # The limit is per user.
    await make_alert(http, two_users.bob.headers, price_alert(asset))


async def test_bob_cannot_read_alices_alert(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    alert = await make_alert(http, two_users.alice.headers, price_alert(await listed(db)))
    await assert_hidden_from(http, two_users.bob, "GET", f"/api/v1/alerts/{alert['id']}")
    bobs = (await http.get("/api/v1/alerts", headers=two_users.bob.headers)).json()
    assert alert["id"] not in {a["id"] for a in bobs}


async def test_bob_cannot_change_alices_alert(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    alert = await make_alert(http, two_users.alice.headers, price_alert(await listed(db)))
    await assert_hidden_from(
        http, two_users.bob, "PATCH", f"/api/v1/alerts/{alert['id']}", json={"status": "paused"}
    )
    assert await status_of(http, two_users.alice.headers, alert["id"]) == "active"


async def test_bob_cannot_delete_alices_alert(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    alert = await make_alert(http, two_users.alice.headers, price_alert(await listed(db)))
    await assert_hidden_from(http, two_users.bob, "DELETE", f"/api/v1/alerts/{alert['id']}")
    assert await status_of(http, two_users.alice.headers, alert["id"]) == "active"


# -------------------------------------------------------------------------------- evaluation
async def test_a_price_alert_fires_once_and_evaluating_again_changes_nothing(
    http: httpx.AsyncClient,
    app: FastAPI,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    asset = await listed(db)
    above = await make_alert(http, h, price_alert(asset, "price_above", "100"))
    below = await make_alert(http, h, price_alert(asset, "price_below", "50"))
    await put_price(db, asset, "120", NOW - timedelta(minutes=5))
    first = await run_evaluation(app)
    assert first.triggered >= 1
    assert await status_of(http, h, above["id"]) == "triggered"
    assert await status_of(http, h, below["id"]) == "active"  # 120 is not at or below 50
    second = await run_evaluation(app)
    assert second.triggered == 0
    events = (await http.get("/api/v1/alerts/events", headers=h)).json()["items"]
    assert [e["alert_id"] for e in events] == [above["id"]]
    assert Decimal(events[0]["observed_value"]) == Decimal(120)
    assert events[0]["seen_at"] is None


async def test_a_price_alert_at_the_threshold_fires(
    http: httpx.AsyncClient,
    app: FastAPI,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    asset = await listed(db)
    alert = await make_alert(http, h, price_alert(asset, "price_below", "80"))
    await put_price(db, asset, "80", NOW - timedelta(minutes=1))
    await run_evaluation(app)
    assert await status_of(http, h, alert["id"]) == "triggered"


async def test_a_stale_or_missing_price_never_fires(
    http: httpx.AsyncClient,
    app: FastAPI,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    stale, none = await listed(db), await listed(db)
    a = await make_alert(http, h, price_alert(stale, "price_above", "10"))
    b = await make_alert(http, h, price_alert(none, "price_above", "10"))
    await put_price(db, stale, "500", NOW - timedelta(days=30))
    result = await run_evaluation(app)
    assert result.skipped_no_fresh_data >= 2
    assert await status_of(http, h, a["id"]) == "active"
    assert await status_of(http, h, b["id"]) == "active"


async def test_paused_alerts_are_not_evaluated_and_rearming_works(
    http: httpx.AsyncClient,
    app: FastAPI,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    asset = await listed(db)
    alert = await make_alert(http, h, price_alert(asset, "price_above", "100"))
    await http.patch(f"/api/v1/alerts/{alert['id']}", headers=h, json={"status": "paused"})
    await put_price(db, asset, "150", NOW - timedelta(minutes=2))
    await run_evaluation(app)
    assert await status_of(http, h, alert["id"]) == "paused"
    await http.patch(f"/api/v1/alerts/{alert['id']}", headers=h, json={"status": "active"})
    await run_evaluation(app)
    assert await status_of(http, h, alert["id"]) == "triggered"
    # Re-arm: the condition still holds, but the same observation does not fire it again.
    await http.patch(f"/api/v1/alerts/{alert['id']}", headers=h, json={"status": "active"})
    await run_evaluation(app)
    assert await status_of(http, h, alert["id"]) == "active"
    assert len((await http.get("/api/v1/alerts/events", headers=h)).json()["items"]) == 1
    # A new observation fires it again.
    await put_price(db, asset, "151", NOW - timedelta(minutes=1))
    await run_evaluation(app)
    assert await status_of(http, h, alert["id"]) == "triggered"
    assert len((await http.get("/api/v1/alerts/events", headers=h)).json()["items"]) == 2


async def test_preferences_default_to_everything_on(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    r = await http.get("/api/v1/alert-preferences", headers=two_users.alice.headers)
    assert r.json() == {
        "alerts_enabled": True,
        "price_alerts_enabled": True,
        "allocation_alerts_enabled": True,
    }


async def test_alerts_turned_off_are_not_evaluated(
    http: httpx.AsyncClient,
    app: FastAPI,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    alice, bob = two_users.alice.headers, two_users.bob.headers
    asset = await listed(db)
    a = await make_alert(http, alice, price_alert(asset))
    b = await make_alert(http, bob, price_alert(asset))
    off = {
        "alerts_enabled": False,
        "price_alerts_enabled": True,
        "allocation_alerts_enabled": True,
    }
    assert (await http.put("/api/v1/alert-preferences", headers=alice, json=off)).status_code == 200
    await put_price(db, asset, "999", NOW - timedelta(minutes=3))
    result = await run_evaluation(app)
    assert result.skipped_by_preferences >= 1
    assert await status_of(http, alice, a["id"]) == "active"  # untouched, not queued
    assert await status_of(http, bob, b["id"]) == "triggered"  # Bob's own settings apply


async def test_a_kind_turned_off_is_not_evaluated(
    http: httpx.AsyncClient,
    app: FastAPI,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    asset = await listed(db)
    alert = await make_alert(http, h, price_alert(asset))
    body = {
        "alerts_enabled": True,
        "price_alerts_enabled": False,
        "allocation_alerts_enabled": True,
    }
    await http.put("/api/v1/alert-preferences", headers=h, json=body)
    await put_price(db, asset, "999", NOW - timedelta(minutes=3))
    await run_evaluation(app)
    assert await status_of(http, h, alert["id"]) == "active"
    body["price_alerts_enabled"] = True
    await http.put("/api/v1/alert-preferences", headers=h, json=body)
    await run_evaluation(app)
    assert await status_of(http, h, alert["id"]) == "triggered"


async def test_an_allocation_alert_fires_on_the_published_allocation(
    http: httpx.AsyncClient,
    app: FastAPI,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    asset = await listed(db)
    await put_price(db, asset, "100", NOW - timedelta(minutes=1))
    pid = (
        await http.post(
            "/api/v1/portfolios", headers=h, json={"name": "Alloc", "base_currency": "USD"}
        )
    ).json()["id"]
    day = (NOW - timedelta(days=5)).date().isoformat()
    for body in (
        {
            "transaction_type": "DEPOSIT",
            "trade_date": day,
            "currency": "USD",
            "gross_amount": {"amount": "5000.00", "currency": "USD"},
        },
        {
            "transaction_type": "BUY",
            "trade_date": day,
            "currency": "USD",
            "asset_id": asset,
            "quantity": "10",
            "unit_price": {"amount": "100", "currency": "USD"},
        },
    ):
        r = await http.post(f"/api/v1/portfolios/{pid}/transactions", headers=h, json=body)
        assert r.status_code == 201, r.text

    def alloc(asset_class: str, pct: str) -> dict[str, Any]:
        return {
            "alert_type": "allocation_above",
            "portfolio_id": pid,
            "asset_class": asset_class,
            "threshold_percent": pct,
        }

    held = await make_alert(http, h, alloc("stock", "1"))
    absent = await make_alert(http, h, alloc("cryptocurrency", "1"))
    await run_evaluation(app)
    assert await status_of(http, h, held["id"]) == "triggered"
    assert await status_of(http, h, absent["id"]) == "active"
    events = (await http.get("/api/v1/alerts/events", headers=h)).json()["items"]
    assert [e["alert_type"] for e in events] == ["allocation_above"]
    assert Decimal(events[0]["observed_value"]) >= 1


# ----------------------------------------------------------------------------------- events
async def test_events_can_be_marked_seen_and_filtered(
    http: httpx.AsyncClient,
    app: FastAPI,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    asset = await listed(db)
    await make_alert(http, h, price_alert(asset))
    await put_price(db, asset, "500", NOW - timedelta(minutes=1))
    await run_evaluation(app)
    unseen = (await http.get("/api/v1/alerts/events?unseen=true", headers=h)).json()["items"]
    assert len(unseen) == 1
    seen = await http.post(f"/api/v1/alerts/events/{unseen[0]['id']}/seen", headers=h)
    assert seen.status_code == 200
    assert seen.json()["seen_at"] is not None
    assert (await http.get("/api/v1/alerts/events?unseen=true", headers=h)).json()["items"] == []
    assert len((await http.get("/api/v1/alerts/events", headers=h)).json()["items"]) == 1


async def test_bob_cannot_mark_alices_event_seen(
    http: httpx.AsyncClient,
    app: FastAPI,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    asset = await listed(db)
    await make_alert(http, h, price_alert(asset))
    await put_price(db, asset, "500", NOW - timedelta(minutes=1))
    await run_evaluation(app)
    event = (await http.get("/api/v1/alerts/events", headers=h)).json()["items"][0]
    await assert_hidden_from(
        http, two_users.bob, "POST", f"/api/v1/alerts/events/{event['id']}/seen"
    )
    assert (await http.get("/api/v1/alerts/events", headers=two_users.bob.headers)).json() == {
        "items": []
    }
    assert (await http.get("/api/v1/alerts/events?unseen=true", headers=h)).json()["items"]


async def test_changes_are_audited_without_payloads(
    http: httpx.AsyncClient,
    db: asyncpg.Connection,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    alert = await make_alert(http, two_users.alice.headers, price_alert(await listed(db)))
    rows = await db.fetch(
        "SELECT action, details::text AS details FROM audit_events WHERE resource_id = $1",
        alert["id"],
    )
    assert [r["action"] for r in rows] == ["alerts.alert.created"]
    assert "100" not in rows[0]["details"]


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/watchlist"),
        ("POST", "/api/v1/watchlist"),
        ("GET", "/api/v1/alerts"),
        ("POST", "/api/v1/alerts"),
        ("GET", "/api/v1/alerts/events"),
        ("GET", "/api/v1/alert-preferences"),
        ("PUT", "/api/v1/alert-preferences"),
    ],
)
async def test_a_signed_in_user_is_required(
    http: httpx.AsyncClient, method: str, path: str
) -> None:
    assert (await http.request(method, path)).status_code == 401
