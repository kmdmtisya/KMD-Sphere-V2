"""Assets (P05-T02): seeded classes, extensibility, search, detail, user-defined assets and
cross-user isolation."""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from app.modules.assets.catalogue import INITIAL_CLASSES, MetadataError, validate_metadata
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, assert_hidden_from, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = pytest.mark.security

# ------------------------------------------------------------------------------- metadata

SCHEMA: dict[str, Any] = {
    "fields": {
        "rate": {"type": "decimal", "required": True},
        "maturity": {"type": "date", "required": False},
        "issuer": {"type": "string", "required": False},
        "year": {"type": "integer", "required": False},
        "callable": {"type": "boolean", "required": False},
    }
}


def test_metadata_is_normalised() -> None:
    out = validate_metadata(
        SCHEMA,
        {
            "rate": "5.2500",
            "maturity": "2030-06-30",
            "issuer": "  Treasury ",
            "year": 2024,
            "callable": False,
        },
    )
    assert out == {
        "rate": "5.2500",
        "maturity": "2030-06-30",
        "issuer": "Treasury",
        "year": 2024,
        "callable": False,
    }
    assert validate_metadata(SCHEMA, {"rate": "1E+2"})["rate"] == "100"
    assert validate_metadata(SCHEMA, {"rate": "1", "issuer": None}) == {"rate": "1"}


@pytest.mark.parametrize(
    "values",
    [
        {},  # required missing
        {"rate": None},
        {"rate": 5.25},  # a JSON number may already be a float: refused
        {"rate": "abc"},
        {"rate": "NaN"},
        {"rate": "Infinity"},
        {"rate": "1", "maturity": "30/06/2030"},
        {"rate": "1", "maturity": 20300630},
        {"rate": "1", "issuer": ""},
        {"rate": "1", "issuer": "x" * 201},
        {"rate": "1", "year": "2024"},
        {"rate": "1", "year": True},
        {"rate": "1", "callable": "yes"},
        {"rate": "1", "colour": "blue"},  # unknown key
    ],
)
def test_bad_metadata_is_refused(values: dict[str, Any]) -> None:
    with pytest.raises(MetadataError):
        validate_metadata(SCHEMA, values)


def test_the_initial_classes() -> None:
    codes = [c.code for c in INITIAL_CLASSES]
    assert len(codes) == len(set(codes)) == 16
    assert {c.valuation_mode for c in INITIAL_CLASSES} == {"market", "manual"}
    for c in INITIAL_CLASSES:
        for kind, _ in c.fields.values():
            assert kind in {"string", "decimal", "date", "integer", "boolean"}


# ----------------------------------------------------------------------------------- API


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


async def global_asset(
    db: asyncpg.Connection, cls: str, symbol: str | None, name: str, **extra: Any
) -> str:
    class_id = await db.fetchval("SELECT id FROM asset_classes WHERE code = $1", cls)
    cols: dict[str, Any] = {
        "asset_class_id": class_id,
        "symbol": symbol,
        "name": name,
        "currency": "USD",
        **extra,
    }
    marks = ", ".join(f"${i + 1}" for i in range(len(cols)))
    sql = f"INSERT INTO assets ({', '.join(cols)}) VALUES ({marks}) RETURNING id"  # noqa: S608
    return str(await db.fetchval(sql, *cols.values()))


@pytest.mark.integration
async def test_the_seed_matches_the_catalogue(db: asyncpg.Connection) -> None:
    rows = await db.fetch("SELECT code, name, valuation_mode, metadata_schema FROM asset_classes")
    stored = {r["code"]: r for r in rows}
    for c in INITIAL_CLASSES:
        row = stored[c.code]
        assert (row["name"], row["valuation_mode"]) == (c.name, c.valuation_mode)
        assert json.loads(row["metadata_schema"]) == c.metadata_schema


@pytest.mark.integration
async def test_classes_are_listed_with_their_metadata_fields(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    r = await http.get("/api/v1/asset-classes", headers=two_users.alice.headers)
    assert r.status_code == 200
    by_code = {c["code"]: c for c in r.json()}
    assert {c.code for c in INITIAL_CLASSES} <= set(by_code)
    assert by_code["fixed_deposit"]["metadata_fields"]["maturity_date"] == {
        "type": "date",
        "required": True,
    }
    assert by_code["real_estate"]["valuation_mode"] == "manual"


@pytest.mark.integration
async def test_a_new_asset_class_needs_no_schema_change(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    code = f"art_{uuid.uuid4().hex[:8]}"
    schema = {"fields": {"artist": {"type": "string", "required": True}}}
    await db.execute(
        "INSERT INTO asset_classes (code, name, valuation_mode, metadata_schema) "
        "VALUES ($1, 'Art', 'manual', $2::jsonb)",
        code,
        json.dumps(schema),
    )
    headers = two_users.alice.headers
    listed = await http.get("/api/v1/asset-classes", headers=headers)
    assert code in {c["code"] for c in listed.json()}
    created = await http.post(
        "/api/v1/assets",
        headers=headers,
        json={
            "asset_class": code,
            "name": "Sunset",
            "currency": "KES",
            "metadata": {"artist": "N"},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["metadata"] == {"artist": "N"}


@pytest.mark.integration
async def test_search_sees_the_catalogue_and_own_assets_only(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    tag = uuid.uuid4().hex[:6].upper()
    listed = await global_asset(db, "stock", f"{tag}A", f"{tag} Alpha Holdings")
    alice = two_users.alice.headers
    bob = two_users.bob.headers
    own = await http.post(
        "/api/v1/assets",
        headers=alice,
        json={"asset_class": "real_estate", "name": f"{tag} Alpha Villa", "currency": "KES"},
    )
    assert own.status_code == 201
    alice_hits = await http.get("/api/v1/assets/search", params={"q": tag}, headers=alice)
    bob_hits = await http.get("/api/v1/assets/search", params={"q": tag}, headers=bob)
    alice_ids = {a["id"] for a in alice_hits.json()["items"]}
    bob_ids = {a["id"] for a in bob_hits.json()["items"]}
    assert alice_ids == {listed, own.json()["id"]}
    assert bob_ids == {listed}  # never another user's asset
    flags = {a["id"]: a["is_custom"] for a in alice_hits.json()["items"]}
    assert flags == {listed: False, own.json()["id"]: True}


@pytest.mark.integration
async def test_search_ranks_exact_symbol_then_prefix_then_name(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    tag = uuid.uuid4().hex[:5].upper()
    contains = await global_asset(db, "etf", f"X{tag}", "Able fund")
    prefix = await global_asset(db, "etf", f"{tag}X", "Yankee fund")
    exact = await global_asset(db, "etf", tag, "Zulu fund")
    by_name = await global_asset(db, "etf", None, f"{tag} by name only")
    r = await http.get(
        "/api/v1/assets/search", params={"q": tag.lower()}, headers=two_users.alice.headers
    )
    # Names alone would sort Able, <tag>..., Yankee, Zulu: the ranking must override that.
    assert [a["id"] for a in r.json()["items"]] == [exact, prefix, by_name, contains]


@pytest.mark.integration
async def test_search_filters_limits_and_treats_wildcards_literally(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    tag = uuid.uuid4().hex[:6]
    for i in range(3):
        await global_asset(db, "bond", None, f"{tag} bond {i}")
    await global_asset(db, "stock", None, f"{tag} stock")
    headers = two_users.alice.headers
    bonds = await http.get(
        "/api/v1/assets/search", params={"q": tag, "asset_class": "bond"}, headers=headers
    )
    assert {a["asset_class"] for a in bonds.json()["items"]} == {"bond"}
    assert len(bonds.json()["items"]) == 3
    two = await http.get("/api/v1/assets/search", params={"q": tag, "limit": 2}, headers=headers)
    assert len(two.json()["items"]) == 2
    wildcard = await http.get("/api/v1/assets/search", params={"q": "%"}, headers=headers)
    assert all("%" in (a["name"] + (a["symbol"] or "")) for a in wildcard.json()["items"])
    for params in ({"limit": 0}, {"limit": 51}, {"q": "x" * 101}, {"asset_class": "Bad Code"}):
        r = await http.get("/api/v1/assets/search", params=params, headers=headers)
        assert r.status_code == 422, params


@pytest.mark.integration
async def test_inactive_assets_are_not_found(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    tag = uuid.uuid4().hex[:8]
    gone = await global_asset(db, "stock", None, f"{tag} delisted", is_active=False)
    headers = two_users.alice.headers
    assert (await http.get(f"/api/v1/assets/{gone}", headers=headers)).status_code == 404
    hits = await http.get("/api/v1/assets/search", params={"q": tag}, headers=headers)
    assert hits.json()["items"] == []


@pytest.mark.integration
async def test_create_and_read_a_user_defined_asset(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    migrated_settings: Settings,  # noqa: F811
    db: asyncpg.Connection,
) -> None:
    body = {
        "asset_class": "fixed_deposit",
        "name": " 12-month deposit ",
        "currency": "KES",
        "country": "KE",
        "metadata": {
            "institution": "Example Bank",
            "interest_rate": "11.50",
            "maturity_date": "2027-10-10",
        },
    }
    created = await http.post("/api/v1/assets", headers=two_users.alice.headers, json=body)
    assert created.status_code == 201, created.text
    out = created.json()
    assert out["name"] == "12-month deposit"
    assert out["is_custom"] is True
    assert out["valuation_mode"] == "manual"
    assert out["metadata"] == {
        "institution": "Example Bank",
        "interest_rate": "11.50",
        "maturity_date": "2027-10-10",
    }
    got = await http.get(f"/api/v1/assets/{out['id']}", headers=two_users.alice.headers)
    assert got.json() == out
    event = await db.fetchrow(
        "SELECT action, actor_user_id, details FROM audit_events WHERE resource_id = $1", out["id"]
    )
    assert event is not None and event["action"] == "assets.asset.created"
    assert str(event["actor_user_id"]) == two_users.alice.id


@pytest.mark.integration
async def test_bob_cannot_read_alices_asset(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    created = await http.post(
        "/api/v1/assets",
        headers=two_users.alice.headers,
        json={"asset_class": "private_business", "name": "Alice Ltd", "currency": "USD"},
    )
    await assert_hidden_from(http, two_users.bob, "GET", f"/api/v1/assets/{created.json()['id']}")


@pytest.mark.integration
@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"asset_class": "nope", "name": "x", "currency": "USD"}, 422),
        ({"asset_class": "real_estate", "name": "x", "currency": "usd"}, 422),
        ({"asset_class": "real_estate", "name": "", "currency": "USD"}, 422),
        ({"asset_class": "real_estate", "name": "x", "currency": "USD", "country": "KEN"}, 422),
        (
            {"asset_class": "real_estate", "name": "x", "currency": "USD", "owner_user_id": "u"},
            422,
        ),
        (
            {"asset_class": "fixed_deposit", "name": "x", "currency": "USD", "metadata": {}},
            422,
        ),
        (
            {
                "asset_class": "real_estate",
                "name": "x",
                "currency": "USD",
                "metadata": {"ownership_percent": 50.5},
            },
            422,
        ),
        (
            {
                "asset_class": "real_estate",
                "name": "x",
                "currency": "USD",
                "metadata": {"rooms": "3"},
            },
            422,
        ),
    ],
)
async def test_invalid_assets_are_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    body: dict[str, Any],
    status: int,
) -> None:
    r = await http.post("/api/v1/assets", headers=two_users.alice.headers, json=body)
    assert r.status_code == status, (body, r.text)
