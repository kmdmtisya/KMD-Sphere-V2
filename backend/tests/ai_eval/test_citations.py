"""Citation preservation (P10-T09): every tool an answer rests on is named in the stream with its
as-of time, and the cited tool is kept in the stored answer."""

from typing import Any

import httpx
import pytest

from app.ai.providers.fake import FakeLlmProvider, tool_reply
from tests.ai_eval.harness import RECORDER
from tests.ai_eval.scenario import World, ask, parse, structured_reply
from tests.authz_harness import TwoUsers, two_users  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]

COMPOUND: dict[str, Any] = {
    "initial_investment": {"amount": "10000.00", "currency": "USD"},
    "contribution": {"amount": "500.00", "currency": "USD"},
    "annual_return_percent": "8.00",
    "years": 20,
}
GOAL: dict[str, Any] = {
    "initial_investment": {"amount": "5000.00", "currency": "USD"},
    "annual_return_percent": "6.00",
    "years": 10,
    "target": {"amount": "50000.00", "currency": "USD"},
}


async def test_every_tool_an_answer_uses_is_cited_in_the_stream_and_in_the_stored_answer(
    http: httpx.AsyncClient,
    llm: FakeLlmProvider,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    world = await World(http, two_users).seed()
    alice = two_users.alice.headers
    pid = world.alice_portfolio
    cases: list[tuple[str, dict[str, Any]]] = [
        ("get_portfolio_summary", {}),
        ("get_portfolio_allocation", {"portfolio_id": pid}),
        ("get_portfolio_performance", {"portfolio_id": pid}),
        ("get_net_worth", {}),
        ("get_goal_progress", {}),
        ("run_compound_forecast", {"inputs": COMPOUND}),
        ("run_goal_forecast", {"inputs": GOAL}),
    ]
    for tool, args in cases:
        llm.reset()
        llm.queue(
            tool_reply(tool, args),
            structured_reply(
                observed=[{"text": "The data was retrieved.", "source": tool}],
                interpretation="This is an illustration, not a guarantee.",
            ),
        )
        events = parse((await ask(http, alice, "Please check.")).text)
        sources = [d for t, d in events if t == "source"]
        assert [s["tool"] for s in sources] == [tool], tool
        assert sources[0]["as_of"], tool
        done = events[-1][1]
        assert done["structured"]["observed"][0]["source"] == tool
        # the rendered answer keeps the citation next to the fact
        text = "".join(d["text"] for t, d in events if t == "token")
        assert f"[{tool}]" in text, tool
        RECORDER.accepted_outputs.append(text)


async def test_an_answer_cannot_cite_a_tool_that_did_not_run(
    http: httpx.AsyncClient,
    llm: FakeLlmProvider,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    bad = structured_reply(observed=[{"text": "A fact.", "source": "get_net_worth"}])
    llm.queue(tool_reply("get_portfolio_summary"), bad, bad)
    events = parse((await ask(http, two_users.alice.headers, "Please check.")).text)
    assert events[-1][0] == "error" and events[-1][1]["code"] == "invalid_answer"
