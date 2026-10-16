"""Optimistic concurrency (P14-T18.1): ETag on single records, If-Match on updates, 409 for a stale
edit, no silent overwrite, and unchanged behaviour for clients that send no precondition."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.concurrency import etag_of, matches
from app.core.config import Settings
from app.main import create_app
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

TODAY = datetime.now(UTC).date()
T1 = datetime(2026, 10, 16, 9, 0, 0, 123456, tzinfo=UTC)
T2 = datetime(2026, 10, 16, 9, 0, 0, 123457, tzinfo=UTC)


def test_etag_changes_with_the_version_and_is_stable() -> None:
    assert etag_of(T1) == etag_of(T1) and etag_of(T1) != etag_of(T2)
    assert etag_of(T1).startswith('"') and etag_of(T1).endswith('"')


def test_if_match_rules() -> None:
    assert matches(None, T1) and matches("*", T1)
    assert matches(etag_of(T1), T1) and not matches(etag_of(T1), T2)
    assert matches(f'"other", {etag_of(T1)}', T1)  # a list names several acceptable versions
    assert matches("W/" + etag_of(T1), T1)  # a weak form of the same version
    assert not matches('"garbage"', T1)


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


def m(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


async def make_goal(http: httpx.AsyncClient, h: dict[str, str]) -> dict[str, Any]:
    r = await http.post(
        "/api/v1/goals",
        headers=h,
        json={
            "name": f"G {uuid.uuid4().hex[:6]}",
            "goal_type": "wealth",
            "target": m("1000.00"),
            "target_date": (TODAY + timedelta(days=700)).isoformat(),
            "target_in_todays_money": False,
            "assumptions": {"contribution": m("10.00"), "returns": {"base": "5"}},
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def make_liability(http: httpx.AsyncClient, h: dict[str, str]) -> dict[str, Any]:
    r = await http.post(
        "/api/v1/liabilities",
        headers=h,
        json={
            "name": f"L {uuid.uuid4().hex[:6]}",
            "liability_type": "personal_loan",
            "balance": m("500.00"),
            "balance_as_of": TODAY.isoformat(),
        },
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


async def make_portfolio(http: httpx.AsyncClient, h: dict[str, str]) -> dict[str, Any]:
    r = await http.post(
        "/api/v1/portfolios",
        headers=h,
        json={"name": f"P {uuid.uuid4().hex[:6]}", "base_currency": "USD"},
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


CASES = {
    "goals": (make_goal, {"name": "Renamed by A"}, {"name": "Renamed by B"}),
    "liabilities": (make_liability, {"name": "Loan A"}, {"name": "Loan B"}),
    "portfolios": (make_portfolio, {"name": "Folio A"}, {"name": "Folio B"}),
}


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.parametrize("resource", sorted(CASES))
async def test_a_stale_edit_gets_409_and_nothing_is_overwritten(
    resource: str,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    make, first, second = CASES[resource]
    h = two_users.alice.headers
    record = await make(http, h)
    url = f"/api/v1/{resource}/{record['id']}"
    loaded = await http.get(url, headers=h)
    version = loaded.headers["etag"]
    assert version.startswith('"')

    # Edit A, from that version, succeeds and moves the version on.
    a = await http.patch(url, headers=h | {"If-Match": version}, json=first)
    assert a.status_code == 200, a.text
    assert a.headers["etag"] != version
    # Edit B, still from the old version, is refused and does not overwrite A.
    b = await http.patch(url, headers=h | {"If-Match": version}, json=second)
    assert b.status_code == 409, b.text
    assert "Reload" in b.json()["detail"]
    assert (await http.get(url, headers=h)).json()["name"] == first["name"]
    # Reloading gives the new version, from which the edit is accepted.
    fresh = (await http.get(url, headers=h)).headers["etag"]
    assert (await http.patch(url, headers=h | {"If-Match": fresh}, json=second)).status_code == 200


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.parametrize("resource", sorted(CASES))
async def test_clients_that_send_no_precondition_keep_last_write_wins(
    resource: str,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    make, first, second = CASES[resource]
    h = two_users.alice.headers
    record = await make(http, h)
    url = f"/api/v1/{resource}/{record['id']}"
    assert (await http.patch(url, headers=h, json=first)).status_code == 200
    assert (await http.patch(url, headers=h, json=second)).status_code == 200
    assert (await http.patch(url, headers=h | {"If-Match": "*"}, json=first)).status_code == 200


@pytest.mark.integration
@pytest.mark.security
async def test_two_edits_from_the_same_version_cannot_both_win(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    h = two_users.alice.headers
    goal = await make_goal(http, h)
    url = f"/api/v1/goals/{goal['id']}"
    version = (await http.get(url, headers=h)).headers["etag"]
    results = await asyncio.gather(
        http.patch(url, headers=h | {"If-Match": version}, json={"name": "From the phone"}),
        http.patch(url, headers=h | {"If-Match": version}, json={"name": "From the browser"}),
    )
    assert sorted(r.status_code for r in results) == [200, 409]


@pytest.mark.integration
@pytest.mark.security
async def test_a_precondition_never_reveals_or_changes_someone_elses_record(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    alice, bob = two_users.alice.headers, two_users.bob.headers
    goal = await make_goal(http, alice)
    url = f"/api/v1/goals/{goal['id']}"
    for precondition in ({}, {"If-Match": "*"}, {"If-Match": '"x"'}):
        r = await http.patch(url, headers=bob | precondition, json={"name": "Taken by Bob"})
        assert r.status_code == 404
    assert "etag" not in (await http.get(url, headers=bob)).headers
    assert (await http.get(url, headers=alice)).json()["name"] == goal["name"]
