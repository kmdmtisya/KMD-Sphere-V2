"""GET /api/v1/search (P14-T07): the signed-in user's own records only (ADR-0011)."""

import uuid
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
URL = "/api/v1/search"


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


async def make_portfolio(http: httpx.AsyncClient, h: dict[str, str], name: str) -> str:
    r = await http.post(
        "/api/v1/portfolios", headers=h, json={"name": name, "base_currency": "USD"}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def make_goal(http: httpx.AsyncClient, h: dict[str, str], name: str) -> str:
    body: dict[str, Any] = {
        "name": name,
        "goal_type": "house_deposit",
        "target": {"amount": "12000.00", "currency": "USD"},
        "target_date": date(date.today().year + 2, 1, 1).isoformat(),
        "assumptions": {
            "contribution": {"amount": "500.00", "currency": "USD"},
            "returns": {"base": "0"},
        },
    }
    r = await http.post("/api/v1/goals", headers=h, json=body)
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def find(http: httpx.AsyncClient, h: dict[str, str], q: str) -> list[dict[str, Any]]:
    r = await http.get(URL, headers=h, params={"q": q})
    assert r.status_code == 200, r.text
    return list(r.json()["results"])


async def test_search_needs_a_signed_in_user(http: httpx.AsyncClient) -> None:
    assert (await http.get(URL, params={"q": "x"})).status_code == 401


async def test_finds_your_own_portfolios_and_goals_case_insensitively(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    tag = uuid.uuid4().hex[:8]
    pid = await make_portfolio(http, two_users.alice.headers, f"Retirement {tag}")
    gid = await make_goal(http, two_users.alice.headers, f"Retire early {tag}")
    hits = await find(http, two_users.alice.headers, "RETIRE")
    found = {(h["kind"], h["id"]) for h in hits}
    assert ("portfolio", pid) in found and ("goal", gid) in found


async def test_bob_never_finds_alices_records(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    tag = uuid.uuid4().hex[:8]
    pid = await make_portfolio(http, two_users.alice.headers, f"Private {tag}")
    gid = await make_goal(http, two_users.alice.headers, f"Secret goal {tag}")
    for query in (tag, f"Private {tag}", "Secret"):
        ids = {h["id"] for h in await find(http, two_users.bob.headers, query)}
        assert pid not in ids and gid not in ids, query
    # ... while Alice still does.
    assert pid in {h["id"] for h in await find(http, two_users.alice.headers, tag)}


async def test_like_wildcards_in_the_query_are_literal(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    tag = uuid.uuid4().hex[:8]
    await make_portfolio(http, two_users.alice.headers, f"Growth {tag}")
    assert await find(http, two_users.alice.headers, "%") == []
    assert await find(http, two_users.alice.headers, "_") == []
    assert await find(http, two_users.alice.headers, f"Gr_wth {tag}") == []


async def test_rejects_an_empty_or_oversized_query(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    for q in ("", "x" * 81):
        r = await http.get(URL, headers=two_users.alice.headers, params={"q": q})
        assert r.status_code == 422
