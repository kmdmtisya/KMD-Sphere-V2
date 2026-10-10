"""Audit events (P04-T04): append-only storage, redaction and correlation-ID linkage."""

import json
import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import asyncpg
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.audit import (
    MAX_DETAILS_BYTES,
    Actor,
    ActorType,
    AuditEvent,
    AuditImmutableError,
    AuditWriter,
    Outcome,
    hash_arguments,
    sanitise_details,
)
from app.core.config import Settings
from app.core.correlation import correlation_id_var
from app.core.redaction import REDACTED
from app.db.session import Database
from app.main import create_app
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = pytest.mark.security

# ------------------------------------------------------------------------- unit: redaction


def test_credentials_and_financial_values_are_redacted() -> None:
    cleaned = sanitise_details(
        {
            "password": "hunter2",
            "access_token": "abc.def.ghi",
            "amount": Decimal("1250.00"),
            "nested": {"market_value": "99.50", "api_key": "k", "note": "kept"},
            "items": [{"unit_price": 3}, {"name": "VWRA"}],
            "message": "retry with Bearer abcdefghijklmnop and fee=12.50",
            "risk_tolerance": "growth",
        }
    )
    assert cleaned["password"] == REDACTED
    assert cleaned["access_token"] == REDACTED
    assert cleaned["amount"] == REDACTED
    assert cleaned["nested"] == {"market_value": REDACTED, "api_key": REDACTED, "note": "kept"}
    assert cleaned["items"] == [{"unit_price": REDACTED}, {"name": "VWRA"}]
    assert "abcdefghijklmnop" not in cleaned["message"]
    assert "12.50" not in cleaned["message"]
    assert cleaned["risk_tolerance"] == "growth"


def test_details_are_json_safe_and_never_floats() -> None:
    uid = uuid.uuid4()
    cleaned = sanitise_details({"ratio": Decimal("0.125"), "id": uid, "score": 0.1, "n": 3})
    assert cleaned == {"ratio": "0.125", "id": str(uid), "score": REDACTED, "n": 3}
    json.dumps(cleaned)  # serialisable


def test_oversized_details_are_replaced_by_their_keys() -> None:
    cleaned = sanitise_details({"note": "x" * (MAX_DETAILS_BYTES + 1), "kind": "big"})
    assert cleaned == {"truncated": True, "keys": ["kind", "note"]}


def test_empty_details() -> None:
    assert sanitise_details(None) == {}
    assert sanitise_details({}) == {}


def test_argument_hash_is_stable_and_order_independent() -> None:
    a = hash_arguments({"portfolio_id": "p1", "period": "1Y", "amount": Decimal("10.0")})
    b = hash_arguments({"amount": Decimal("10.0"), "period": "1Y", "portfolio_id": "p1"})
    assert a == b
    assert len(a) == 64
    assert a != hash_arguments({"portfolio_id": "p2", "period": "1Y", "amount": Decimal("10.0")})


def test_the_writer_can_only_append() -> None:
    public = {name for name in dir(AuditWriter) if not name.startswith("_")}
    assert public == {"record"}


def test_actor_factories() -> None:
    uid = uuid.uuid4()
    assert Actor.user(uid) == Actor(ActorType.USER, uid)
    assert Actor.ai(uid) == Actor(ActorType.AI, uid)
    assert Actor.system() == Actor(ActorType.SYSTEM, None)


# ----------------------------------------------------------------------- database-backed

integration = pytest.mark.integration


@pytest.fixture(scope="module")
async def db(migrated_settings: Settings) -> AsyncIterator[Database]:  # noqa: F811
    database = Database(migrated_settings)
    yield database
    await database.dispose()


async def _record(db: Database, **kwargs: Any) -> uuid.UUID:
    async with db.session_factory() as session:
        row = await AuditWriter(session).record(**kwargs)
        await session.commit()
        return row.id


async def _fetch(settings: Settings, sql: str, *args: Any) -> list[asyncpg.Record]:
    conn = await asyncpg.connect(settings.database_dsn, timeout=5)
    try:
        return list(await conn.fetch(sql, *args))
    finally:
        await conn.close()


@integration
async def test_an_event_is_stored_with_its_correlation_id_and_redacted_details(
    db: Database,
    migrated_settings: Settings,  # noqa: F811
) -> None:
    uid = uuid.uuid4()
    token = correlation_id_var.set("corr-123")
    try:
        event_id = await _record(
            db,
            action="test.thing.changed",
            actor=Actor.user(uid),
            resource_type="thing",
            resource_id=uid,
            details={"password": "secret!", "amount": Decimal("5"), "field": "name"},
        )
    finally:
        correlation_id_var.reset(token)
    [row] = await _fetch(migrated_settings, "SELECT * FROM audit_events WHERE id = $1", event_id)
    assert row["correlation_id"] == "corr-123"
    assert row["actor_type"] == "user"
    assert row["actor_user_id"] == uid
    assert row["resource_id"] == str(uid)
    assert row["outcome"] == "success"
    assert row["occurred_at"] is not None
    stored = json.loads(row["details"])
    assert stored == {"password": REDACTED, "amount": REDACTED, "field": "name"}
    assert "secret!" not in row["details"]


@integration
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE audit_events SET outcome = 'failure' WHERE id = $1",
        "UPDATE audit_events SET details = '{}'::jsonb WHERE id = $1",
        "DELETE FROM audit_events WHERE id = $1",
    ],
)
async def test_the_database_rejects_changes_and_deletes(
    db: Database,
    migrated_settings: Settings,  # noqa: F811
    sql: str,
) -> None:
    event_id = await _record(db, action="test.thing.created", actor=Actor.system())
    with pytest.raises(asyncpg.InsufficientPrivilegeError, match="append-only"):
        await _fetch(migrated_settings, sql, event_id)
    [row] = await _fetch(
        migrated_settings, "SELECT outcome FROM audit_events WHERE id = $1", event_id
    )
    assert row["outcome"] == "success"


@integration
async def test_the_database_rejects_truncate(
    db: Database,
    migrated_settings: Settings,  # noqa: F811
) -> None:
    await _record(db, action="test.thing.created", actor=Actor.system())
    with pytest.raises(asyncpg.InsufficientPrivilegeError, match="TRUNCATE"):
        await _fetch(migrated_settings, "TRUNCATE audit_events")
    [row] = await _fetch(migrated_settings, "SELECT count(*) AS n FROM audit_events")
    assert row["n"] > 0


@integration
async def test_the_orm_refuses_to_change_or_delete_a_loaded_event(db: Database) -> None:
    event_id = await _record(db, action="test.thing.created", actor=Actor.system())
    async with db.session_factory() as session:
        loaded = (
            await session.execute(select(AuditEvent).where(AuditEvent.id == event_id))
        ).scalar_one()
        loaded.outcome = Outcome.FAILURE.value
        with pytest.raises(AuditImmutableError):
            await session.flush()
        await session.rollback()
    async with db.session_factory() as session:
        loaded = (
            await session.execute(select(AuditEvent).where(AuditEvent.id == event_id))
        ).scalar_one()
        await session.delete(loaded)
        with pytest.raises(AuditImmutableError):
            await session.flush()
        await session.rollback()


@integration
@pytest.mark.parametrize(
    ("action", "actor"),
    [
        ("Not.Valid", Actor.system()),
        ("noseparator", Actor.system()),
        ("test.user.missing", Actor(ActorType.USER, None)),
        ("test.ai.missing", Actor(ActorType.AI, None)),
    ],
)
async def test_malformed_events_are_rejected(db: Database, action: str, actor: Actor) -> None:
    with pytest.raises(IntegrityError):
        await _record(db, action=action, actor=actor)


# ------------------------------------------------------------------ wired into the API


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


async def _events_for(settings: Settings, resource_id: str) -> list[asyncpg.Record]:
    return await _fetch(
        settings,
        "SELECT * FROM audit_events WHERE resource_id = $1 ORDER BY occurred_at, action",
        resource_id,
    )


@integration
async def test_risk_profile_changes_are_audited_and_linked_to_the_request(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    migrated_settings: Settings,  # noqa: F811
) -> None:
    alice = two_users.alice
    created = await http.post(
        "/api/v1/risk-profiles",
        headers={**alice.headers, "X-Correlation-ID": "create-req-1"},
        json={"risk_tolerance": "balanced", "horizon_years": 10},
    )
    assert created.status_code == 201
    pid = created.json()["id"]
    changed = await http.patch(
        f"/api/v1/risk-profiles/{pid}",
        headers={**alice.headers, "X-Correlation-ID": "update-req-2"},
        json={"risk_tolerance": "growth"},
    )
    assert changed.status_code == 200

    events = await _events_for(migrated_settings, pid)
    assert [(e["action"], e["correlation_id"]) for e in events] == [
        ("identity.risk_profile.created", "create-req-1"),
        ("identity.risk_profile.updated", "update-req-2"),
    ]
    assert {str(e["actor_user_id"]) for e in events} == {alice.id}
    assert json.loads(events[1]["details"]) == {
        "changed": ["risk_tolerance"],
        "risk_tolerance": "growth",
    }


@integration
async def test_a_hidden_resource_produces_no_success_event(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    migrated_settings: Settings,  # noqa: F811
) -> None:
    created = await http.post(
        "/api/v1/risk-profiles",
        headers=two_users.alice.headers,
        json={"risk_tolerance": "balanced"},
    )
    pid = created.json()["id"]
    r = await http.patch(
        f"/api/v1/risk-profiles/{pid}",
        headers=two_users.bob.headers,
        json={"risk_tolerance": "aggressive"},
    )
    assert r.status_code == 404
    actions = [e["action"] for e in await _events_for(migrated_settings, pid)]
    assert actions == ["identity.risk_profile.created"]


@integration
async def test_a_change_is_not_kept_when_its_audit_event_cannot_be_written(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    migrated_settings: Settings,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def broken(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(AuditWriter, "record", broken)
    before = await _fetch(
        migrated_settings,
        "SELECT count(*) AS n FROM risk_profiles WHERE user_id = $1",
        uuid.UUID(two_users.alice.id),
    )
    r = await http.post(
        "/api/v1/risk-profiles",
        headers=two_users.alice.headers,
        json={"risk_tolerance": "growth"},
    )
    assert r.status_code == 500
    after = await _fetch(
        migrated_settings,
        "SELECT count(*) AS n FROM risk_profiles WHERE user_id = $1",
        uuid.UUID(two_users.alice.id),
    )
    assert after[0]["n"] == before[0]["n"]
