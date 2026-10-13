"""Cross-user access through every P12 entry point (P12-T08, QG-07.1): Bob, with Alice's ids,
gets exactly what a non-existent id gets, the tools refuse, the public endpoints show nothing of
Alice's, and smuggled user ids are refused. Real app and database."""

import json
import uuid
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.tools.base import ToolContext
from app.ai.tools.factory import build_tool_registry
from app.modules.universe.ingestion import DemoUniverseSource, ingest
from tests.ai_eval.harness import judge, load
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.test_analytics_api import Book, m

pytestmark = [pytest.mark.integration, pytest.mark.security]
ASSUMPTIONS = {
    "initial_investment": m("1000.00"),
    "contribution": m("100.00"),
    "annual_return_percent": "6.00",
    "conservative_return_percent": "3.00",
    "growth_return_percent": "9.00",
    "years": 10,
}


async def world(app: FastAPI, http: httpx.AsyncClient, users: TwoUsers) -> dict[str, Any]:
    sessions: async_sessionmaker[AsyncSession] = app.state.db.session_factory
    async with sessions() as s:
        await ingest(s, DemoUniverseSource())
    universe = (await http.get("/api/v1/universe", headers=users.alice.headers)).json()
    ids = {i["symbol"]: i["asset_id"] for i in universe["items"]}
    alice = Book(http, users.alice.headers)
    portfolio = await alice.portfolio()
    await alice.post(portfolio, "DEPOSIT", gross_amount=m("5000.00"))
    archived = await alice.portfolio()
    r = await http.post(f"/api/v1/portfolios/{archived}/archive", headers=users.alice.headers)
    assert r.status_code in (200, 204), r.text
    private = await alice.asset()
    run = await http.post("/api/v1/ai/opportunities", headers=users.alice.headers, json={})
    assert run.status_code == 201, run.text
    bob_portfolio = await Book(http, users.bob.headers).portfolio()
    return {
        "portfolio": portfolio,
        "archived": archived,
        "private_asset": private,
        "run": run.json()["id"],
        "RUN": run.json()["id"].upper(),
        "alice": users.alice.id,
        "instrument": ids["DEMO-GEQ"],
        "instrument2": ids["DEMO-GBD"],
        "bob_portfolio": bob_portfolio,
        "assumptions": ASSUMPTIONS,
    }


def fill(value: Any, w: dict[str, Any]) -> Any:
    if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
        return w[value[1:-1]]
    if isinstance(value, str):
        for k, v in w.items():
            if isinstance(v, str):
                value = value.replace("{" + k + "}", v)
        return value
    if isinstance(value, dict):
        return {k: fill(v, w) for k, v in value.items()}
    if isinstance(value, list):
        return [fill(v, w) for v in value]
    return value


def unknown(w: dict[str, Any]) -> dict[str, Any]:
    """The same world with every one of Alice's ids replaced by an id that does not exist."""
    alices = ("portfolio", "archived", "private_asset", "run", "RUN")
    return w | {k: str(uuid.uuid4()) for k in alices}


def leaks(text: str, w: dict[str, Any]) -> bool:
    return any(
        str(w[k]).lower() in text.lower()
        for k in ("portfolio", "archived", "private_asset", "run", "alice")
    )


async def verdict(
    app: FastAPI, http: httpx.AsyncClient, users: TwoUsers, row: dict[str, Any], w: dict[str, Any]
) -> bool:
    bob = users.bob.headers
    if "tool" in row:
        registry = build_tool_registry(app.state.settings)
        sessions: async_sessionmaker[AsyncSession] = app.state.db.session_factory
        async with sessions() as session:
            outcome = await registry.execute(
                row["tool"],
                fill(row["args"], w),
                ToolContext(uuid.UUID(users.bob.id), session, "corr", "fake-1", "fake"),
            )
        return not outcome.ok and outcome.error_code in ("not_found", "invalid_arguments")
    method, path, body = row["method"], fill(row["path"], w), fill(row["body"], w)
    response = await http.request(method, path, headers=bob, json=body, follow_redirects=True)
    if row["expect"] == 404:
        twin = await http.request(
            method,
            fill(row["path"], unknown(w)),
            headers=bob,
            json=fill(row["body"], unknown(w)),
            follow_redirects=True,
        )
        return (
            response.status_code == 404
            and twin.status_code == 404
            and response.json()["detail"] == twin.json()["detail"]
            and not leaks(response.text, w)
        )
    if row["expect"] == 422:
        return response.status_code == 422 and not leaks(response.text, w)
    if row["expect"] == "empty":
        return response.status_code == 200 and response.json() == []
    return response.status_code == 200 and not leaks(response.text, w)  # "no_alice"


async def test_p12_cross_user_access_is_denied_everywhere(
    app: FastAPI,
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    w = await world(app, http, two_users)
    verdicts = {
        row["id"]: await verdict(app, http, two_users, row, w) for row in load("p12_cross_user")
    }
    judge("p12_cross_user", verdicts)
    assert json.dumps(w["assumptions"])  # the world is complete
