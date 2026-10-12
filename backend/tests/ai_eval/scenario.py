"""A two-user world and the helpers that drive the assistant through the real HTTP API with a
scripted ("compromised") model."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.ai.providers.fake import text_reply
from app.ai.providers.models import ChatResponse, ToolCall, Usage
from tests.ai_eval.build_datasets import BOB_MARKER
from tests.authz_harness import TwoUsers

CHAT = "/api/v1/ai/chat"
TODAY = datetime.now(UTC).date()
BOB_AMOUNT = "7654321.00"


def money(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def parse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for frame in body.strip().split("\n\n"):
        head, data = frame.split("\n")
        events.append((head.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def multi_call(*calls: tuple[str, dict[str, Any]]) -> ChatResponse:
    return ChatResponse(
        content="",
        tool_calls=tuple(ToolCall(f"call-{i}", n, a) for i, (n, a) in enumerate(calls)),
        usage=Usage(5, 2),
        provider="fake",
        model="fake-1",
        finish_reason="tool_calls",
    )


def structured_reply(**fields: Any) -> ChatResponse:
    body = {"observed": [], "calculated": [], "assumptions": [], "interpretation": ""} | fields
    return text_reply(json.dumps(body))


async def make_portfolio(
    http: httpx.AsyncClient, headers: dict[str, str], name: str, deposit: str | None = "5000.00"
) -> str:
    r = await http.post(
        "/api/v1/portfolios", headers=headers, json={"name": name, "base_currency": "USD"}
    )
    assert r.status_code == 201, r.text
    pid = str(r.json()["id"])
    if deposit:
        t = await http.post(
            f"/api/v1/portfolios/{pid}/transactions",
            headers=headers,
            json={
                "transaction_type": "DEPOSIT",
                "trade_date": (TODAY - timedelta(days=30)).isoformat(),
                "currency": "USD",
                "gross_amount": money(deposit),
            },
        )
        assert t.status_code == 201, t.text
    return pid


async def make_goal(
    http: httpx.AsyncClient, headers: dict[str, str], name: str, portfolio_id: str
) -> str:
    r = await http.post(
        "/api/v1/goals",
        headers=headers,
        json={
            "name": name,
            "goal_type": "house_deposit",
            "target": money("20000.00"),
            "target_date": (TODAY + timedelta(days=700)).isoformat(),
            "portfolio_id": portfolio_id,
            "assumptions": {"contribution": money("200.00"), "returns": {"base": "5"}},
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


class World:
    """Alice has a portfolio and a goal; Bob has a portfolio and a goal that carry a marker no
    one but Bob may ever see."""

    def __init__(self, http: httpx.AsyncClient, users: TwoUsers) -> None:
        self.http, self.users = http, users
        self.alice_portfolio = self.alice_goal = ""
        self.bob_portfolio = self.bob_goal = self.bob_conversation = ""

    async def seed(self) -> "World":
        a, b = self.users.alice.headers, self.users.bob.headers
        self.alice_portfolio = await make_portfolio(self.http, a, "Alice main")
        self.alice_goal = await make_goal(self.http, a, "Alice house", self.alice_portfolio)
        self.bob_portfolio = await make_portfolio(self.http, b, BOB_MARKER, BOB_AMOUNT)
        self.bob_goal = await make_goal(self.http, b, f"{BOB_MARKER} goal", self.bob_portfolio)
        return self

    @property
    def placeholders(self) -> dict[str, str]:
        return {
            "bob_user": self.users.bob.id,
            "bob_portfolio": self.bob_portfolio,
            "bob_goal": self.bob_goal,
            "alice_portfolio": self.alice_portfolio,
        }

    def fill(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            k: self.placeholders.get(v[1:-1], v) if isinstance(v, str) and v.startswith("{") else v
            for k, v in arguments.items()
        }


async def ask(
    http: httpx.AsyncClient, headers: dict[str, str], message: str, **extra: Any
) -> httpx.Response:
    return await http.post(CHAT, headers=headers, json={"message": message, **extra})


def leaked(marker: str, *haystacks: str) -> bool:
    return any(marker in h or marker.lower() in h.lower() for h in haystacks)


def everything_sent_to_the_model(requests: list[Any]) -> str:
    return "\n".join(m.content for r in requests for m in r.messages)
