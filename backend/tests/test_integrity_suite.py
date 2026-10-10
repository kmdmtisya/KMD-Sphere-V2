"""Authorisation and integrity suite (P05-T09).

1. IDOR sweep: every registered id route, called by Bob against Alice's real resources, answers
   a 404 indistinguishable from a missing id, and leaves every row of Alice's data unchanged.
2. Collection isolation: Bob's lists, searches and consolidated summary never include Alice's.
3. Ledger invariants under random sequences: seeded random runs of postings, sales (some
   backdated), income, reversals and idempotent replays through the real API; after every step
   the invariants below hold. A failure names its seed, so it can be replayed exactly.
"""

import hashlib
import json
import random
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.core.money import round_half_up
from app.main import create_app
from app.modules.transactions.holdings import Entry, compute, effective, never_negative
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, assert_hidden_from, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.idor_registry import IDOR_TESTS

pytestmark = [pytest.mark.integration, pytest.mark.security]
TODAY = date.today()


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    application = create_app(
        # Hundreds of requests from one test client: limits are tested in test_api_protection.
        migrated_settings.model_copy(
            update={"rate_limit_user_requests": 100_000, "rate_limit_ip_requests": 100_000}
        ),
        readiness_checks={},
        token_verifier=ah.verifier(),
    )
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


def m(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


async def listed_stock(db: asyncpg.Connection) -> str:
    cls = await db.fetchval("SELECT id FROM asset_classes WHERE code = 'stock'")
    return str(
        await db.fetchval(
            "INSERT INTO assets (asset_class_id, symbol, name, currency) "
            "VALUES ($1, $2, 'Sweep Co', 'USD') RETURNING id",
            cls,
            uuid.uuid4().hex[:8].upper(),
        )
    )


# ----------------------------------------------------------------------------- IDOR sweep


async def alice_world(
    http: httpx.AsyncClient, h: dict[str, str], db: asyncpg.Connection
) -> dict[str, str]:
    """One of each of Alice's resources, keyed by the path parameter that names it."""

    async def ok(r: httpx.Response) -> dict[str, Any]:
        assert r.status_code in (200, 201), r.text
        return r.json()  # type: ignore[no-any-return]

    portfolio = await ok(
        await http.post(
            "/api/v1/portfolios", headers=h, json={"name": "Alice main", "base_currency": "USD"}
        )
    )
    pid = portfolio["id"]
    asset = await ok(
        await http.post(
            "/api/v1/assets",
            headers=h,
            json={"asset_class": "real_estate", "name": "Alice flat", "currency": "USD"},
        )
    )
    stock = await listed_stock(db)
    base = f"/api/v1/portfolios/{pid}/transactions"
    tx = await ok(
        await http.post(
            base,
            headers=h,
            json={
                "transaction_type": "DEPOSIT",
                "trade_date": TODAY.isoformat(),
                "currency": "USD",
                "gross_amount": m("1000.00"),
            },
        )
    )
    await ok(
        await http.post(
            base,
            headers=h,
            json={
                "transaction_type": "BUY",
                "trade_date": TODAY.isoformat(),
                "currency": "USD",
                "asset_id": stock,
                "quantity": "2",
                "unit_price": m("50"),
            },
        )
    )
    valuation = await ok(
        await http.post(
            f"/api/v1/portfolios/{pid}/valuations",
            headers=h,
            json={
                "asset_id": asset["id"],
                "value": m("90000.00"),
                "as_of": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
                "source": "owner estimate",
            },
        )
    )
    risk = await ok(
        await http.post("/api/v1/risk-profiles", headers=h, json={"risk_tolerance": "balanced"})
    )
    return {
        "portfolio_id": pid,
        "transaction_id": tx["id"],
        "valuation_id": valuation["id"],
        "asset_id": asset["id"],
        "risk_profile_id": risk["id"],
    }


# A valid body for each write route, so a 404 can only come from the ownership check.
BODIES: dict[tuple[str, str], dict[str, Any] | None] = {
    ("PATCH", "/api/v1/portfolios/{portfolio_id}"): {"name": "Taken by Bob"},
    ("POST", "/api/v1/portfolios/{portfolio_id}/archive"): None,
    ("POST", "/api/v1/portfolios/{portfolio_id}/transactions"): {
        "transaction_type": "WITHDRAWAL",
        "trade_date": TODAY.isoformat(),
        "currency": "USD",
        "gross_amount": m("999.00"),
    },
    ("POST", "/api/v1/portfolios/{portfolio_id}/transactions/{transaction_id}/reversal"): {},
    ("POST", "/api/v1/portfolios/{portfolio_id}/valuations"): {
        "asset_id": "{asset_id}",
        "value": m("1.00"),
        "as_of": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        "source": "bob",
    },
    ("PATCH", "/api/v1/portfolios/{portfolio_id}/valuations/{valuation_id}"): {"source": "bob"},
    ("PATCH", "/api/v1/risk-profiles/{risk_profile_id}"): {"risk_tolerance": "aggressive"},
}

# Every table that holds a user's data, for the before/after snapshot.
SNAPSHOT_TABLES = (
    "portfolios",
    "transactions",
    "holdings",
    "valuations",
    "assets",
    "asset_metadata",
    "risk_profiles",
    "user_profiles",
)


async def snapshot(db: asyncpg.Connection, user_id: str) -> dict[str, str]:
    uid = uuid.UUID(user_id)
    queries = {
        "portfolios": "SELECT * FROM portfolios WHERE user_id = $1 ORDER BY id",
        "transactions": "SELECT t.* FROM transactions t JOIN portfolios p ON p.id = t.portfolio_id "
        "WHERE p.user_id = $1 ORDER BY t.id",
        "holdings": "SELECT h.* FROM holdings h JOIN portfolios p ON p.id = h.portfolio_id "
        "WHERE p.user_id = $1 ORDER BY h.id",
        "valuations": "SELECT v.* FROM valuations v JOIN portfolios p ON p.id = v.portfolio_id "
        "WHERE p.user_id = $1 ORDER BY v.id",
        "assets": "SELECT * FROM assets WHERE owner_user_id = $1 ORDER BY id",
        "asset_metadata": "SELECT m.* FROM asset_metadata m JOIN assets a ON a.id = m.asset_id "
        "WHERE a.owner_user_id = $1 ORDER BY m.id",
        "risk_profiles": "SELECT * FROM risk_profiles WHERE user_id = $1 ORDER BY id",
        "user_profiles": "SELECT * FROM user_profiles WHERE user_id = $1",
    }
    assert set(queries) == set(SNAPSHOT_TABLES)
    out = {}
    for table, sql in queries.items():
        rows = [dict(r) for r in await db.fetch(sql, uid)]
        out[table] = hashlib.sha256(
            json.dumps(rows, default=str, sort_keys=True).encode()
        ).hexdigest()
    return out


def fill(template: str, world: dict[str, str]) -> str:
    out = template
    for name, value in world.items():
        out = out.replace("{" + name + "}", value)
    assert "{" not in out, f"the sweep does not know a parameter in {template}: add it"
    return out


def fill_body(body: dict[str, Any] | None, world: dict[str, str]) -> dict[str, Any] | None:
    """Replaces "{name}" string values with the matching resource id."""
    if body is None:
        return None
    return {
        k: world[v[1:-1]] if isinstance(v, str) and v.startswith("{") and v.endswith("}") else v
        for k, v in body.items()
    }


async def test_the_idor_sweep_covers_every_registered_route(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    world = await alice_world(http, two_users.alice.headers, db)
    before = await snapshot(db, two_users.alice.id)
    for method, template in sorted(IDOR_TESTS):
        path = fill(template, world)
        body = fill_body(BODIES.get((method, template)), world)
        await assert_hidden_from(http, two_users.bob, method, path, json=body)
    after = await snapshot(db, two_users.alice.id)
    assert after == before, "Bob's requests changed Alice's data"
    # Alice still sees everything (the sweep did not break her access).
    pid = world["portfolio_id"]
    assert (
        await http.get(f"/api/v1/portfolios/{pid}", headers=two_users.alice.headers)
    ).status_code == 200


async def test_every_write_route_has_a_valid_sweep_body() -> None:
    writes = {(m_, p) for m_, p in IDOR_TESTS if m_ in ("POST", "PATCH", "PUT")}
    assert writes <= set(BODIES), f"add a body for {sorted(writes - set(BODIES))}"


async def test_collections_never_show_another_users_data(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    world = await alice_world(http, two_users.alice.headers, db)
    bob = two_users.bob.headers
    assert world["portfolio_id"] not in {
        p["id"]
        for p in (
            await http.get("/api/v1/portfolios", headers=bob, params={"include_archived": 1})
        ).json()
    }
    assert world["risk_profile_id"] not in {
        r["id"] for r in (await http.get("/api/v1/risk-profiles", headers=bob)).json()
    }
    found = await http.get("/api/v1/assets/search", headers=bob, params={"q": "Alice flat"})
    assert world["asset_id"] not in {a["id"] for a in found.json()["items"]}
    summary = await http.get("/api/v1/portfolios/consolidated/summary", headers=bob)
    assert world["portfolio_id"] not in summary.json()["portfolio_ids"]


# ------------------------------------------------------------ ledger invariants (random)

SEEDS = range(12)
STEPS = 30


async def ledger(db: asyncpg.Connection, pid: str) -> list[asyncpg.Record]:
    return list(
        await db.fetch("SELECT * FROM transactions WHERE portfolio_id = $1", uuid.UUID(pid))
    )


def entries_of(rows: list[asyncpg.Record]) -> list[Entry]:
    return [
        Entry(
            id=r["id"],
            transaction_type=r["transaction_type"],
            trade_date=r["trade_date"],
            created_at=r["created_at"],
            asset_id=r["asset_id"],
            quantity=r["quantity"],
            gross_amount=r["gross_amount"],
            fees=r["fees"],
            taxes=r["taxes"],
            fx=r["fx_rate_to_portfolio_currency"],
            reverses=r["reverses_transaction_id"],
            currency=r["currency"],
        )
        for r in rows
    ]


def expected_cash(e: Entry) -> Decimal:
    """The test's own cash rules (docs/design/portfolio-summary.md, section 3), written out
    independently of the product code so a bug there cannot hide here."""
    gross, costs = e.gross_amount, e.fees + e.taxes
    inflow = {"DEPOSIT", "SELL", "DIVIDEND", "INTEREST", "COUPON", "RENT", "DISTRIBUTION"}
    outflow = {"WITHDRAWAL", "BUY", "FEE", "TAX"}
    if e.transaction_type in inflow:
        return gross - costs
    if e.transaction_type in outflow:
        return -(gross + costs)
    if e.transaction_type in {"TRANSFER_IN", "TRANSFER_OUT"}:
        return -costs
    return Decimal(0)


async def check_invariants(
    http: httpx.AsyncClient,
    h: dict[str, str],
    db: asyncpg.Connection,
    pid: str,
    seen: dict[uuid.UUID, str],
    context: str,
) -> None:
    rows = await ledger(db, pid)
    entries = entries_of(rows)

    # Posted rows never change.
    for r in rows:
        digest = hashlib.sha256(
            json.dumps(dict(r), default=str, sort_keys=True).encode()
        ).hexdigest()
        assert seen.setdefault(r["id"], digest) == digest, f"{context}: row {r['id']} changed"

    # Reversals: one per entry, never of a reversal, always in the same portfolio.
    by_id = {e.id: e for e in entries}
    reversed_ids = [e.reverses for e in entries if e.reverses is not None]
    assert len(reversed_ids) == len(set(reversed_ids)), f"{context}: an entry reversed twice"
    for rid in reversed_ids:
        assert rid in by_id, f"{context}: reversal of an entry outside the portfolio"
        assert by_id[rid].reverses is None, f"{context}: a reversal was reversed"

    # No quantity goes below zero on any date, and the holdings cache equals the ledger.
    assert never_negative(entries), f"{context}: negative position in the history"
    expected = compute(entries)
    stored = {
        r["asset_id"]: r
        for r in await db.fetch("SELECT * FROM holdings WHERE portfolio_id = $1", uuid.UUID(pid))
    }
    assert set(stored) == set(expected), f"{context}: holdings rows differ from the ledger"
    for asset_id, position in expected.items():
        row = stored[asset_id]
        assert row["quantity"] == round_half_up(position.quantity, 12), context
        assert row["quantity"] >= 0, context
        for field in ("cost_basis", "realized_pl", "income", "expenses"):
            assert row[field] == round_half_up(getattr(position, field), 8), f"{context}: {field}"

    # One audit event per ledger entry.
    events = await db.fetchval(
        "SELECT count(*) FROM audit_events WHERE resource_type = 'transaction' "
        "AND resource_id = ANY($1::text[])",
        [str(r["id"]) for r in rows],
    )
    assert events == len(rows), f"{context}: {events} audit events for {len(rows)} entries"

    # The summary agrees with the holdings and with the ledger's cash.
    s = (await http.get(f"/api/v1/portfolios/{pid}/summary", headers=h)).json()
    realised = sum((p.realized_pl for p in expected.values()), Decimal(0))
    assert Decimal(s["realized_pl"]["amount"]) == round_half_up(realised, 2), context
    cash = sum((expected_cash(e) for e in effective(entries)), Decimal(0))
    assert Decimal(s["cash"]["amount"]) == round_half_up(cash, 2), context


@pytest.mark.parametrize("seed", SEEDS)
async def test_ledger_invariants_hold_under_random_sequences(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
    seed: int,
) -> None:
    rnd = random.Random(seed)  # noqa: S311 (reproducible test data, not cryptography)
    h = two_users.alice.headers
    r = await http.post(
        "/api/v1/portfolios", headers=h, json={"name": f"Random {seed}", "base_currency": "USD"}
    )
    pid = r.json()["id"]
    url = f"/api/v1/portfolios/{pid}/transactions"
    assets = [await listed_stock(db) for _ in range(2)]
    posted: list[str] = []
    keys: list[tuple[str, dict[str, Any], str]] = []
    seen: dict[uuid.UUID, str] = {}

    for step in range(STEPS):
        day = (TODAY - timedelta(days=rnd.randint(0, 60))).isoformat()
        asset = rnd.choice(assets)
        op = rnd.choices(
            ["deposit", "buy", "sell", "dividend", "reverse", "replay"], [2, 4, 4, 1, 2, 1]
        )[0]
        body: dict[str, Any] | None = None
        if op == "deposit":
            body = {"transaction_type": "DEPOSIT", "gross_amount": m(f"{rnd.randint(1, 5000)}.00")}
        elif op in ("buy", "sell"):
            body = {
                "transaction_type": op.upper(),
                "asset_id": asset,
                "quantity": str(Decimal(rnd.randint(1, 4000)) / 100),
                "unit_price": m(str(Decimal(rnd.randint(100, 50000)) / 100)),
                "fees": m(f"{rnd.randint(0, 9)}.{rnd.randint(0, 99):02d}"),
            }
        elif op == "dividend":
            body = {"transaction_type": "DIVIDEND", "asset_id": asset, "gross_amount": m("12.34")}
        context = f"seed {seed}, step {step}, {op}"
        if body is not None:
            key = f"k-{seed}-{step}"
            body |= {"trade_date": day, "currency": "USD"}
            resp = await http.post(url, headers={**h, "Idempotency-Key": key}, json=body)
            assert resp.status_code in (201, 409), f"{context}: {resp.text}"
            if resp.status_code == 201:
                posted.append(resp.json()["id"])
                keys.append((key, body, resp.json()["id"]))
        elif op == "reverse" and posted:
            target = rnd.choice(posted)
            resp = await http.post(f"{url}/{target}/reversal", headers=h, json={})
            assert resp.status_code in (201, 409), f"{context}: {resp.text}"
            if resp.status_code == 201:
                posted.append(resp.json()["id"])
        elif op == "replay" and keys:
            key, body, first_id = rnd.choice(keys)
            before = len(await ledger(db, pid))
            resp = await http.post(url, headers={**h, "Idempotency-Key": key}, json=body)
            assert resp.status_code == 200, f"{context}: {resp.text}"
            assert resp.json()["id"] == first_id, context
            assert len(await ledger(db, pid)) == before, f"{context}: a replay added an entry"
        await check_invariants(http, h, db, pid, seen, context)
