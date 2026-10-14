# ruff: noqa: F811 (imported pytest fixtures are used by name as test parameters)
"""The Forex Copilot through the real chat endpoint (P13-T10.2, T10.6), with a scripted model: the
forex rules join the system prompt only when forex is on, a quote answer carries the server's
sources and simulated-data caveat, an answer that tells the user to trade is sent back once and
a clean one accepted, and a request to place a trade is declined with the paper account named."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import FastAPI

from app.ai.providers.fake import FakeLlmProvider, text_reply, tool_reply
from app.core.config import Settings
from app.modules.forex.marketdata.feed import prepare
from tests.ai.test_chat import CHAT, make_app, parse
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.forex.test_paper_api import quote

pytestmark = [pytest.mark.integration, pytest.mark.security]


@pytest.fixture
def llm() -> FakeLlmProvider:
    return FakeLlmProvider()


@pytest.fixture
async def app(migrated_settings: Settings, llm: FakeLlmProvider) -> AsyncIterator[FastAPI]:
    settings = migrated_settings.model_copy(update={"forex_enabled": True})
    application = make_app(settings, llm)
    await prepare(application.state.db.session_factory, settings, datetime.now(UTC))
    yield application
    await application.state.db.dispose()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def answer(text: str, interpretation: str) -> str:
    return json.dumps(
        {
            "observed": [{"text": text, "source": "get_forex_quote"}],
            "interpretation": interpretation,
        }
    )


async def test_a_quote_answer_carries_sources_and_the_simulated_caveat(
    app: FastAPI,
    http: httpx.AsyncClient,
    llm: FakeLlmProvider,
    two_users: TwoUsers,
) -> None:
    await quote(app.state.db.session_factory, "EUR_USD", "1.08610", "1.08622")
    llm.queue(
        tool_reply("get_forex_quote", {"instrument": "EUR_USD"}),
        text_reply(answer("EUR/USD was bid at 1.0861.", "This is a snapshot of the feed.")),
    )
    r = await http.post(CHAT, headers=two_users.alice.headers, json={"message": "EUR/USD price?"})
    assert r.status_code == 200, r.text
    done = parse(r.text)[-1][1]
    structured = done["structured"]
    (source,) = structured["sources"]
    assert source["tool"] == "get_forex_quote" and source["as_of"]
    assert source["data_types"] == ["simulated"]
    assert any("simulated development feed" in c for c in structured["caveats"])
    system = llm.requests[0].messages[0].content
    assert "Forex (when forex tools are offered)" in system
    assert "get_forex_quote" in {t.name for t in llm.requests[0].tools}


async def test_a_trade_instruction_is_sent_back_and_a_clean_answer_accepted(
    app: FastAPI,
    http: httpx.AsyncClient,
    llm: FakeLlmProvider,
    two_users: TwoUsers,
) -> None:
    await quote(app.state.db.session_factory, "EUR_USD", "1.08610", "1.08622")
    llm.queue(
        tool_reply("get_forex_quote", {"instrument": "EUR_USD"}),
        text_reply(answer("EUR/USD was bid at 1.0861.", "You should buy EUR/USD now.")),
        text_reply(answer("EUR/USD was bid at 1.0861.", "I cannot tell you to buy or sell.")),
    )
    r = await http.post(CHAT, headers=two_users.alice.headers, json={"message": "Buy or not?"})
    done = parse(r.text)[-1][1]
    assert "buy EUR/USD now" not in json.dumps(done)
    assert done["structured"]["interpretation"] == "I cannot tell you to buy or sell."
    correction = llm.requests[2].messages[-1].content
    assert "do not tell the user to buy" in correction


async def test_a_request_to_trade_is_declined_with_the_paper_account_named(
    http: httpx.AsyncClient, llm: FakeLlmProvider, two_users: TwoUsers
) -> None:
    r = await http.post(
        CHAT, headers=two_users.alice.headers, json={"message": "Buy 1 lot of EUR/USD for me"}
    )
    assert r.status_code == 200
    text = "".join(d.get("text", "") for t, d in parse(r.text) if t == "token")
    assert "cannot place orders" in text and "paper account" in text
    assert llm.requests == []  # no model was asked


async def test_with_forex_off_the_prompt_and_tools_have_no_forex(
    migrated_settings: Settings, two_users: TwoUsers
) -> None:
    llm = FakeLlmProvider([text_reply(json.dumps({"interpretation": "Hello."}))])
    off = make_app(migrated_settings, llm)
    transport = httpx.ASGITransport(app=off, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(CHAT, headers=two_users.alice.headers, json={"message": "Hi"})
    finally:
        await off.state.db.dispose()
    assert "Forex (when" not in llm.requests[0].messages[0].content
    assert not any(t.name.startswith("get_forex") for t in llm.requests[0].tools)
