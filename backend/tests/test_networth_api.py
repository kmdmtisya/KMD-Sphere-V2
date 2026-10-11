"""/api/v1/liabilities and /api/v1/net-worth (P06-T07) through the API."""

import secrets
import string
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.core.money import minor_units
from app.main import create_app
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, assert_hidden_from, make_user, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
NOW = datetime.now(UTC).replace(microsecond=0)
TODAY = NOW.date()


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


def fresh_currency() -> str:
    """A code no other test uses (FX rates are shared), with 2 minor units."""
    while True:
        code = "W" + "".join(secrets.choice(string.ascii_uppercase) for _ in range(2))
        if minor_units(code) == 2:
            return code


def m(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


def liability(**changes: Any) -> dict[str, Any]:
    body = {
        "name": f"Loan {uuid.uuid4().hex[:6]}",
        "liability_type": "personal_loan",
        "balance": m("1000.00"),
        "balance_as_of": TODAY.isoformat(),
    }
    return body | changes


async def create(http: httpx.AsyncClient, h: dict[str, str], **changes: Any) -> dict[str, Any]:
    r = await http.post("/api/v1/liabilities", headers=h, json=liability(**changes))
    assert r.status_code == 201, r.text
    return dict(r.json())


async def rate(db: asyncpg.Connection, base: str, quote: str, value: str) -> None:
    await db.execute(
        "INSERT INTO fx_rates (base_currency, quote_currency, rate, provider, rate_timestamp, "
        "retrieved_at) VALUES ($1, $2, $3::numeric, 'test-provider', $4, $4)",
        base,
        quote,
        value,
        NOW - timedelta(minutes=10),
    )


# ---------------------------------------------------------------------------------- liabilities


async def test_liability_crud(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    house = (
        await http.post(
            "/api/v1/assets",
            headers=h,
            json={"asset_class": "real_estate", "name": "Flat", "currency": "USD"},
        )
    ).json()
    item = await create(http, h, liability_type="mortgage", balance=m("150000.00"),
                        interest_rate_percent="4.25", asset_id=house["id"])  # fmt: skip
    assert item["balance"] == m("150000.00") and item["interest_rate_percent"] == "4.25"
    assert item["asset_id"] == house["id"] and item["liability_type"] == "mortgage"
    assert (await http.get(f"/api/v1/liabilities/{item['id']}", headers=h)).json() == item
    assert item["id"] in {
        x["id"] for x in (await http.get("/api/v1/liabilities", headers=h)).json()
    }

    r = await http.patch(f"/api/v1/liabilities/{item['id']}", headers=h, json={
        "balance": m("149000.00"), "interest_rate_percent": None, "asset_id": None})  # fmt: skip
    assert r.status_code == 200, r.text
    changed = r.json()
    assert changed["balance"] == m("149000.00")
    assert changed["interest_rate_percent"] is None and changed["asset_id"] is None
    moved = await http.patch(f"/api/v1/liabilities/{item['id']}", headers=h,
                             json={"balance": m("120000.00", "EUR")})  # fmt: skip
    assert moved.json()["balance"] == m("120000.00", "EUR")

    assert (await http.delete(f"/api/v1/liabilities/{item['id']}", headers=h)).status_code == 204
    assert (await http.get(f"/api/v1/liabilities/{item['id']}", headers=h)).status_code == 404
    actions = [
        r["action"]
        for r in await db.fetch(
            "SELECT action FROM audit_events WHERE resource_type = 'liability' "
            "AND resource_id = $1 ORDER BY occurred_at",
            item["id"],
        )
    ]
    assert actions == [
        "networth.liability.created",
        "networth.liability.updated",
        "networth.liability.updated",
        "networth.liability.deleted",
    ]


INVALID = [
    ("future balance date", {"balance_as_of": (TODAY + timedelta(days=1)).isoformat()}),
    ("negative balance", {"balance": m("-1.00")}),
    ("too many decimals", {"balance": m("1.001")}),
    ("too large", {"balance": m("10000000000.01")}),
    ("a JSON number", {"balance": {"amount": 1, "currency": "USD"}}),
    ("unknown type", {"liability_type": "iou"}),
    ("blank name", {"name": " "}),
    ("rate over 100", {"interest_rate_percent": "100.01"}),
    ("rate 3 decimals", {"interest_rate_percent": "4.125"}),
    ("unknown asset", {"asset_id": str(uuid.uuid4())}),
    ("unknown field", {"lender": "Bank"}),
]


@pytest.mark.parametrize(("name", "change"), INVALID, ids=[n for n, _ in INVALID])
async def test_invalid_liabilities_are_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    name: str,
    change: dict[str, Any],
) -> None:
    r = await http.post("/api/v1/liabilities", headers=two_users.alice.headers,
                        json=liability(**change))  # fmt: skip
    assert r.status_code == 422, (name, r.text)


async def test_invalid_changes_and_names(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    item = await create(http, h)
    for change in ({"name": None}, {"balance": None}, {"balance_as_of": None},
                   {"liability_type": None},
                   {"balance_as_of": (TODAY + timedelta(days=2)).isoformat()},
                   {"asset_id": str(uuid.uuid4())}):  # fmt: skip
        r = await http.patch(f"/api/v1/liabilities/{item['id']}", headers=h, json=change)
        assert r.status_code == 422, (change, r.text)
    again = await http.post("/api/v1/liabilities", headers=h, json=liability(name=item["name"]))
    assert again.status_code == 409
    other = await create(http, h)
    clash = await http.patch(f"/api/v1/liabilities/{other['id']}", headers=h,
                             json={"name": item["name"]})  # fmt: skip
    assert clash.status_code == 409


async def test_another_users_asset_cannot_secure_a_liability(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    bobs = (
        await http.post(
            "/api/v1/assets",
            headers=two_users.bob.headers,
            json={"asset_class": "real_estate", "name": "Bob house", "currency": "USD"},
        )
    ).json()
    r = await http.post("/api/v1/liabilities", headers=two_users.alice.headers,
                        json=liability(asset_id=bobs["id"]))  # fmt: skip
    assert r.status_code == 422 and "no such asset" in r.text


async def test_the_liability_limit(
    http: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.networth import service

    monkeypatch.setattr(service, "MAX_LIABILITIES_PER_USER", 1)
    h = (await make_user(http, "limit")).headers
    await create(http, h)
    assert (await http.post("/api/v1/liabilities", headers=h, json=liability())).status_code == 409


# ------------------------------------------------------------------------------------ net worth


async def test_net_worth_with_fx_provenance(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.alice.headers
    fx, missing = fresh_currency(), fresh_currency()
    await rate(db, fx, "USD", "0.5")
    pid = (
        await http.post(
            "/api/v1/portfolios", headers=h, json={"name": "Main", "base_currency": "USD"}
        )
    ).json()["id"]
    house = (
        await http.post(
            "/api/v1/assets",
            headers=h,
            json={"asset_class": "real_estate", "name": "Home", "currency": "USD"},
        )
    ).json()["id"]
    for body in (
        {"transaction_type": "DEPOSIT", "gross_amount": m("10000.00")},
        {"transaction_type": "BUY", "asset_id": house, "quantity": "1", "unit_price": m("6000")},
    ):
        r = await http.post(f"/api/v1/portfolios/{pid}/transactions", headers=h, json=body | {
            "trade_date": (TODAY - timedelta(days=5)).isoformat(), "currency": "USD"})  # fmt: skip
        assert r.status_code == 201, r.text
    await http.post(f"/api/v1/portfolios/{pid}/valuations", headers=h, json={
        "asset_id": house, "value": m("8000.00"), "as_of": (NOW - timedelta(days=1)).isoformat(),
        "source": "estimate"})  # fmt: skip
    await create(http, h, liability_type="mortgage", balance=m("5000.00"))
    await create(http, h, liability_type="car_loan", balance=m("1000.00", fx))  # 500 USD
    await create(http, h, liability_type="other", balance=m("10.00", missing),
                 balance_as_of=(TODAY - timedelta(days=30)).isoformat())  # no rate  # fmt: skip

    r = await http.get("/api/v1/net-worth", headers=h)
    assert r.status_code == 200, r.text
    nw = r.json()
    # Assets: house 8000 + cash 10000 - 6000 = 12000. Liabilities: 5000 + 500.
    assert nw["currency"] == "USD"
    assert (nw["assets"], nw["liabilities"], nw["net_worth"]) == (
        m("12000.00"),
        m("5500.00"),
        m("6500.00"),
    )
    assert nw["assets_by_class"] == [
        {"asset_class": "real_estate", "value": m("8000.00"), "share_percent": "66.67"},
        {"asset_class": "cash", "value": m("4000.00"), "share_percent": "33.33"},
    ]
    assert [(t["liability_type"], t["value"], t["count"]) for t in nw["liabilities_by_type"]] == [
        ("mortgage", m("5000.00"), 1),
        ("car_loan", m("500.00"), 1),
    ]
    lines = {line["liability_type"]: line for line in nw["liability_lines"]}
    assert lines["car_loan"]["balance"] == m("1000.00", fx)
    assert lines["car_loan"]["value"] == m("500.00")
    assert lines["other"]["value"] is None
    used = {f["currency"]: f for f in nw["fx_rates"]}
    assert fx in used and missing not in used
    assert (used[fx]["rate"], used[fx]["provider"], used[fx]["stale"], used[fx]["inverted"]) == (
        "0.5",
        "test-provider",
        False,
        False,
    )
    f = nw["freshness"]
    assert f["complete"] is False and f["unconverted_currencies"] == [missing]
    assert f["oldest_liability_balance"] == (TODAY - timedelta(days=30)).isoformat()
    # The mobile NetWorthSummary fields.
    assert {"assets", "liabilities", "net_worth", "as_of"} <= set(nw)


async def test_net_worth_in_another_currency(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    h = two_users.bob.headers
    reporting = fresh_currency()
    await rate(db, "USD", reporting, "2")
    pid = (
        await http.post("/api/v1/portfolios", headers=h, json={"name": "B", "base_currency": "USD"})
    ).json()["id"]
    await http.post(f"/api/v1/portfolios/{pid}/transactions", headers=h, json={
        "transaction_type": "DEPOSIT", "gross_amount": m("100.00"), "currency": "USD",
        "trade_date": TODAY.isoformat()})  # fmt: skip
    await create(http, h, balance=m("20.00", reporting))  # needs no rate: only the portfolio does
    nw = (await http.get(f"/api/v1/net-worth?currency={reporting}", headers=h)).json()
    assert (nw["assets"], nw["liabilities"], nw["net_worth"]) == (
        m("200.00", reporting),
        m("20.00", reporting),
        m("180.00", reporting),
    )
    assert [f["currency"] for f in nw["fx_rates"]] == ["USD"]
    assert nw["freshness"]["complete"] is True
    bad = await http.get("/api/v1/net-worth?currency=usd", headers=h)
    assert bad.status_code == 422


async def test_nothing_recorded(http: httpx.AsyncClient) -> None:
    h = (await make_user(http, "empty")).headers
    nw = (await http.get("/api/v1/net-worth", headers=h)).json()
    assert (nw["assets"]["amount"], nw["liabilities"]["amount"], nw["net_worth"]["amount"]) == (
        "0.00",
        "0.00",
        "0.00",
    )
    assert nw["assets_by_class"] == [] and nw["liability_lines"] == []
    assert nw["freshness"]["oldest_liability_balance"] is None


async def test_net_worth_is_the_users_own(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    await create(http, two_users.bob.headers, balance=m("777.00"))
    nw = (await http.get("/api/v1/net-worth", headers=two_users.alice.headers)).json()
    assert nw["liabilities"] == m("0.00") and nw["liability_lines"] == []


# ------------------------------------------------------------------------------ ownership (IDOR)


async def test_bob_cannot_read_alices_liability(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    item = await create(http, two_users.alice.headers)
    await assert_hidden_from(http, two_users.bob, "GET", f"/api/v1/liabilities/{item['id']}")
    bobs = (await http.get("/api/v1/liabilities", headers=two_users.bob.headers)).json()
    assert item["id"] not in {x["id"] for x in bobs}


async def test_bob_cannot_change_alices_liability(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    item = await create(http, two_users.alice.headers)
    await assert_hidden_from(http, two_users.bob, "PATCH", f"/api/v1/liabilities/{item['id']}",
                             json={"balance": m("0.00")})  # fmt: skip
    after = await http.get(f"/api/v1/liabilities/{item['id']}", headers=two_users.alice.headers)
    assert after.json() == item


async def test_bob_cannot_delete_alices_liability(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    item = await create(http, two_users.alice.headers)
    await assert_hidden_from(http, two_users.bob, "DELETE", f"/api/v1/liabilities/{item['id']}")
    after = await http.get(f"/api/v1/liabilities/{item['id']}", headers=two_users.alice.headers)
    assert after.status_code == 200


async def test_repository_writes_are_scoped_to_the_owner(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    from app.modules.networth.repository import LiabilityRepository

    item = await create(http, two_users.alice.headers)
    async with app.state.db.session_factory() as session:
        repo = LiabilityRepository(session)
        await repo.update(uuid.UUID(two_users.bob.id), uuid.UUID(item["id"]), {"name": "Taken"})
        await repo.delete(uuid.UUID(two_users.bob.id), uuid.UUID(item["id"]))
        await session.commit()
    after = await http.get(f"/api/v1/liabilities/{item['id']}", headers=two_users.alice.headers)
    assert after.json() == item


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/api/v1/liabilities"), ("POST", "/api/v1/liabilities"), ("GET", "/api/v1/net-worth")],
)
async def test_a_signed_in_user_is_required(
    http: httpx.AsyncClient, method: str, path: str
) -> None:
    assert (await http.request(method, path, json=liability())).status_code == 401
