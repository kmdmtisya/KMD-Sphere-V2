"""LLM providers (P10-T05): adapters against recorded-shape payloads, the fake, retry and fallback,
and key custody. No adapter has been run against a live service (no key exists, ADR-0017)."""

import ast
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.ai.providers.anthropic_adapter import AnthropicProvider
from app.ai.providers.anthropic_adapter import build_body as anthropic_body
from app.ai.providers.errors import (
    LlmAuthError,
    LlmBadRequest,
    LlmInvalidOutput,
    LlmNotConfigured,
    LlmRateLimited,
    LlmUnavailable,
)
from app.ai.providers.fake import FakeLlmProvider, text_reply, tool_reply
from app.ai.providers.http import HttpxLlm
from app.ai.providers.models import (
    ChatRequest,
    Message,
    StreamDone,
    TextDelta,
    ToolCall,
)
from app.ai.providers.openai_adapter import OpenAIProvider
from app.ai.providers.openai_adapter import build_body as openai_body
from app.ai.providers.registry import build_llm
from app.ai.providers.resilience import FallbackLlm, RetryingLlm
from app.ai.tools.base import ToolSpec
from app.core.config import Settings

KEY = "sk-TEST-KEY-do-not-leak-12345"
APP = Path(__file__).resolve().parents[2] / "app"

SPEC = ToolSpec(
    "get_net_worth",
    "The user's net worth",
    {"type": "object", "properties": {"currency": {"type": "string"}}},
)
REQUEST = ChatRequest(
    messages=(
        Message("system", "You explain portfolio data."),
        Message("user", "What is my net worth?"),
    ),
    tools=(SPEC,),
    max_output_tokens=300,
)


def handler_to_provider(
    kind: str, handler: Any, key: str = KEY
) -> OpenAIProvider | AnthropicProvider:
    http = HttpxLlm(transport=httpx.MockTransport(handler))
    if kind == "openai":
        return OpenAIProvider(SecretStr(key), "model-x", http)
    return AnthropicProvider(SecretStr(key), "model-y", http)


def json_response(payload: dict[str, Any], status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=json.dumps(payload))


def sse(lines: list[str]) -> httpx.Response:
    return httpx.Response(
        200,
        content="\n".join(lines).encode(),
        headers={"content-type": "text/event-stream"},
    )


# ------------------------------------------------------------------------------ OpenAI
OPENAI_TEXT = {
    "id": "chatcmpl-1",
    "model": "model-x-2026-01-01",
    "choices": [
        {
            "message": {"role": "assistant", "content": "Your net worth is shown above."},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 21, "completion_tokens": 7},
}
OPENAI_TOOL = {
    "id": "chatcmpl-2",
    "model": "model-x-2026-01-01",
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_9",
                        "type": "function",
                        "function": {"name": "get_net_worth", "arguments": '{"currency": "USD"}'},
                    }
                ],
            },
            "finish_reason": "tool_calls",
        }
    ],
    "usage": {"prompt_tokens": 30, "completion_tokens": 12},
}


async def test_openai_request_shape_and_answer() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(OPENAI_TEXT)

    response = await handler_to_provider("openai", handler).complete(REQUEST)
    [request] = seen
    body = json.loads(request.content)
    assert request.url.host == "api.openai.com"
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert KEY not in str(request.url)
    assert body["model"] == "model-x" and body["max_completion_tokens"] == 300
    assert body["messages"][0] == {"role": "system", "content": "You explain portfolio data."}
    assert body["tools"][0]["function"]["name"] == "get_net_worth"
    assert "temperature" not in body, "left to the provider unless set"
    assert response.content == "Your net worth is shown above."
    assert (response.usage.input_tokens, response.usage.output_tokens) == (21, 7)
    assert (response.provider, response.model, response.request_id) == (
        "openai",
        "model-x-2026-01-01",
        "chatcmpl-1",
    )


async def test_openai_tool_call_and_its_result_in_the_next_request() -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return json_response(OPENAI_TOOL if len(bodies) == 1 else OPENAI_TEXT)

    provider = handler_to_provider("openai", handler)
    first = await provider.complete(REQUEST)
    [call] = first.tool_calls
    assert (call.id, call.name, dict(call.arguments)) == (
        "call_9",
        "get_net_worth",
        {"currency": "USD"},
    )
    follow = ChatRequest(
        messages=(
            *REQUEST.messages,
            Message("assistant", "", tool_calls=(call,)),
            Message("tool", '{"ok": true}', tool_call_id="call_9"),
        ),
        tools=REQUEST.tools,
    )
    await provider.complete(follow)
    assistant, tool = bodies[1]["messages"][2:]
    assert assistant["tool_calls"][0]["function"]["arguments"] == '{"currency": "USD"}'
    assert tool == {"role": "tool", "tool_call_id": "call_9", "content": '{"ok": true}'}


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, LlmAuthError),
        (403, LlmAuthError),
        (429, LlmRateLimited),
        (500, LlmUnavailable),
        (400, LlmBadRequest),
    ],
)
async def test_http_failures_map_to_provider_errors_without_leaking(
    kind: str, status: int, error: type[Exception], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=f"bad key {KEY} and prompt What is my net worth?")

    provider = handler_to_provider(kind, handler)
    with pytest.raises(error) as caught:
        await provider.complete(REQUEST)
    text = str(caught.value) + repr(caught.value) + repr(provider) + caplog.text
    assert KEY not in text
    assert "net worth" not in text, "neither the prompt nor the response body is repeated"


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
async def test_a_transport_failure_hides_the_url_and_key(kind: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout(
            f"timed out talking to {request.url} with {KEY}", request=request
        )

    with pytest.raises(LlmUnavailable) as caught:
        await handler_to_provider(kind, handler).complete(REQUEST)
    assert KEY not in str(caught.value) and "api." not in str(caught.value)
    assert "ConnectTimeout" in str(caught.value)


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
async def test_a_missing_key_is_an_auth_error_without_calling_out(kind: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call the provider without a key")

    with pytest.raises(LlmAuthError):
        await handler_to_provider(kind, handler, key="").complete(REQUEST)


@pytest.mark.parametrize("arguments", ['{"currency": ', "[1, 2]", '"text"'])
async def test_openai_tool_arguments_that_are_not_an_object_are_refused(arguments: str) -> None:
    bad = json.loads(json.dumps(OPENAI_TOOL))
    bad["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = arguments
    with pytest.raises(LlmInvalidOutput):
        await handler_to_provider("openai", lambda r: json_response(bad)).complete(REQUEST)


async def test_unexpected_shapes_are_refused() -> None:
    payloads: list[dict[str, Any]] = [{}, {"choices": []}, {"choices": [{"message": 3}]}]
    for payload in payloads:
        with pytest.raises(LlmInvalidOutput):
            await handler_to_provider("openai", lambda r, p=payload: json_response(p)).complete(
                REQUEST
            )
    with pytest.raises(LlmInvalidOutput):
        await handler_to_provider(
            "openai", lambda r: httpx.Response(200, text="not json")
        ).complete(REQUEST)


async def test_openai_streaming_text_and_tool_calls() -> None:
    def chunk(delta: dict[str, Any], finish: str | None = None) -> str:
        return "data: " + json.dumps(
            {
                "id": "c1",
                "model": "model-x-2026",
                "choices": [{"delta": delta, "finish_reason": finish}],
            }
        )

    lines = [
        chunk({"role": "assistant", "content": "Your "}),
        "",
        chunk({"content": "net worth"}),
        chunk(
            {
                "tool_calls": [
                    {
                        "index": 0,
                        "id": "call_1",
                        "function": {"name": "get_net_worth", "arguments": '{"curr'},
                    }
                ]
            }
        ),
        chunk(
            {"tool_calls": [{"index": 0, "function": {"arguments": 'ency": "USD"}'}}]},
            finish="tool_calls",
        ),
        "data: "
        + json.dumps(
            {
                "id": "c1",
                "model": "model-x-2026",
                "choices": [],
                "usage": {"prompt_tokens": 40, "completion_tokens": 9},
            }
        ),
        "data: [DONE]",
    ]
    provider = handler_to_provider("openai", lambda r: sse(lines))
    events = [e async for e in provider.stream(REQUEST)]
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Your ", "net worth"]
    done = events[-1]
    assert isinstance(done, StreamDone)
    assert done.response.content == "Your net worth"
    assert dict(done.response.tool_calls[0].arguments) == {"currency": "USD"}
    assert (done.response.usage.input_tokens, done.response.usage.output_tokens) == (40, 9)
    assert done.response.finish_reason == "tool_calls"


async def test_a_failed_stream_status_raises_before_any_text() -> None:
    provider = handler_to_provider("openai", lambda r: httpx.Response(429, text="slow down"))
    with pytest.raises(LlmRateLimited):
        async for _ in provider.stream(REQUEST):
            pytest.fail("no event expected")


# ---------------------------------------------------------------------------- Anthropic
ANTHROPIC_TOOL = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "model-y-2026-01-01",
    "content": [
        {"type": "text", "text": "Let me check."},
        {
            "type": "tool_use",
            "id": "toolu_1",
            "name": "get_net_worth",
            "input": {"currency": "USD"},
        },
    ],
    "stop_reason": "tool_use",
    "usage": {"input_tokens": 33, "output_tokens": 14},
}


async def test_anthropic_request_shape_and_tool_use() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return json_response(ANTHROPIC_TOOL)

    response = await handler_to_provider("anthropic", handler).complete(REQUEST)
    [request] = seen
    body = json.loads(request.content)
    assert request.headers["x-api-key"] == KEY and request.headers["anthropic-version"]
    assert "authorization" not in request.headers
    assert body["system"] == "You explain portfolio data."
    assert body["messages"] == [{"role": "user", "content": "What is my net worth?"}]
    assert body["max_tokens"] == 300
    assert body["tools"][0]["input_schema"]["type"] == "object"
    assert response.content == "Let me check."
    [call] = response.tool_calls
    assert (call.id, call.name, dict(call.arguments)) == (
        "toolu_1",
        "get_net_worth",
        {"currency": "USD"},
    )
    assert (response.usage.input_tokens, response.usage.output_tokens) == (33, 14)
    assert (response.provider, response.model, response.finish_reason) == (
        "anthropic",
        "model-y-2026-01-01",
        "tool_use",
    )


def test_anthropic_puts_all_tool_results_of_a_turn_in_one_user_message() -> None:
    calls = (ToolCall("a", "get_net_worth", {}), ToolCall("b", "get_net_worth", {}))
    request = ChatRequest(
        messages=(
            Message("user", "hi"),
            Message("assistant", "", tool_calls=calls),
            Message("tool", "r1", tool_call_id="a"),
            Message("tool", "r2", tool_call_id="b"),
        )
    )
    messages = anthropic_body("m", request, stream=False)["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert [b["tool_use_id"] for b in messages[2]["content"]] == ["a", "b"]
    assert messages[1]["content"][0]["type"] == "tool_use"


async def test_anthropic_streaming() -> None:
    def event(**payload: Any) -> str:
        return "data: " + json.dumps(payload)

    lines = [
        "event: message_start",
        event(
            type="message_start",
            message={"id": "m1", "model": "model-y-2026", "usage": {"input_tokens": 50}},
        ),
        event(type="content_block_start", index=0, content_block={"type": "text", "text": ""}),
        event(
            type="content_block_delta", index=0, delta={"type": "text_delta", "text": "Checking "}
        ),
        event(type="content_block_delta", index=0, delta={"type": "text_delta", "text": "now."}),
        event(type="content_block_stop", index=0),
        event(
            type="content_block_start",
            index=1,
            content_block={
                "type": "tool_use",
                "id": "toolu_2",
                "name": "get_net_worth",
                "input": {},
            },
        ),
        event(
            type="content_block_delta",
            index=1,
            delta={"type": "input_json_delta", "partial_json": '{"curre'},
        ),
        event(
            type="content_block_delta",
            index=1,
            delta={"type": "input_json_delta", "partial_json": 'ncy": "EUR"}'},
        ),
        event(type="content_block_stop", index=1),
        event(type="message_delta", delta={"stop_reason": "tool_use"}, usage={"output_tokens": 18}),
        event(type="message_stop"),
    ]
    provider = handler_to_provider("anthropic", lambda r: sse(lines))
    events = [e async for e in provider.stream(REQUEST)]
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Checking now."
    done = events[-1]
    assert isinstance(done, StreamDone)
    assert dict(done.response.tool_calls[0].arguments) == {"currency": "EUR"}
    assert (done.response.usage.input_tokens, done.response.usage.output_tokens) == (50, 18)
    assert (done.response.model, done.response.request_id) == ("model-y-2026", "m1")


async def test_anthropic_refuses_tool_input_that_is_not_an_object() -> None:
    bad = json.loads(json.dumps(ANTHROPIC_TOOL))
    bad["content"][1]["input"] = ["not", "an", "object"]
    with pytest.raises(LlmInvalidOutput):
        await handler_to_provider("anthropic", lambda r: json_response(bad)).complete(REQUEST)


def test_openai_request_body_omits_tools_when_there_are_none() -> None:
    body = openai_body("m", ChatRequest(messages=(Message("user", "hi"),)), stream=False)
    assert "tools" not in body and "stream" not in body


# ------------------------------------------------------------------------------- fake
async def test_the_fake_is_scripted_deterministic_and_records_requests() -> None:
    fake = FakeLlmProvider([tool_reply("get_net_worth", {"currency": "USD"}), text_reply("Done.")])
    first = await fake.complete(REQUEST)
    assert first.tool_calls[0].name == "get_net_worth" and fake.requests == [REQUEST]
    assert (await fake.complete(REQUEST)).content == "Done."
    with pytest.raises(AssertionError, match="no scripted reply"):
        await fake.complete(REQUEST)


async def test_the_fake_can_fail_and_stream() -> None:
    fake = FakeLlmProvider([LlmUnavailable("down"), text_reply("one two three")])
    with pytest.raises(LlmUnavailable):
        await fake.complete(REQUEST)
    events = [e async for e in fake.stream(REQUEST)]
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "one two three"
    assert isinstance(events[-1], StreamDone) and events[-1].response.model == "fake-1"


async def test_the_fake_can_build_a_reply_from_the_request() -> None:
    fake = FakeLlmProvider([lambda req: text_reply(f"{len(req.messages)} messages")])
    assert (await fake.complete(REQUEST)).content == "2 messages"


# -------------------------------------------------------------------- retry / fallback
async def no_sleep(_: float) -> None:
    return None


async def test_a_transient_failure_is_retried_once() -> None:
    fake = FakeLlmProvider([LlmRateLimited("slow"), text_reply("ok")])
    assert (await RetryingLlm(fake, sleep=no_sleep).complete(REQUEST)).content == "ok"
    assert len(fake.requests) == 2


async def test_a_refused_key_is_not_retried() -> None:
    fake = FakeLlmProvider([LlmAuthError("no"), text_reply("never")])
    with pytest.raises(LlmAuthError):
        await RetryingLlm(fake, sleep=no_sleep).complete(REQUEST)
    assert len(fake.requests) == 1


async def test_a_bad_request_is_not_retried() -> None:
    fake = FakeLlmProvider([LlmBadRequest("too long"), text_reply("never")])
    with pytest.raises(LlmBadRequest):
        await RetryingLlm(fake, sleep=no_sleep).complete(REQUEST)
    assert len(fake.requests) == 1


async def test_the_fallback_answers_when_the_first_provider_is_down() -> None:
    down = FakeLlmProvider([LlmUnavailable("a"), LlmUnavailable("a")])
    up = FakeLlmProvider([text_reply("from the second")])
    chain = FallbackLlm([RetryingLlm(down, sleep=no_sleep), RetryingLlm(up, sleep=no_sleep)])
    assert (await chain.complete(REQUEST)).content == "from the second"


async def test_the_fallback_also_covers_a_refused_key() -> None:
    chain = FallbackLlm([FakeLlmProvider([LlmAuthError("x")]), FakeLlmProvider([text_reply("ok")])])
    assert (await chain.complete(REQUEST)).content == "ok"


async def test_every_provider_failing_is_one_clear_error() -> None:
    chain = FallbackLlm(
        [FakeLlmProvider([LlmUnavailable("a")]), FakeLlmProvider([LlmUnavailable("b")])]
    )
    with pytest.raises(LlmUnavailable, match="all 2 providers failed"):
        await chain.complete(REQUEST)


async def test_streaming_falls_back_before_the_first_token_but_not_after() -> None:
    chain = FallbackLlm(
        [FakeLlmProvider([LlmUnavailable("a")]), FakeLlmProvider([text_reply("hello there")])]
    )
    assert (
        "".join([e.text async for e in chain.stream(REQUEST) if isinstance(e, TextDelta)])
        == "hello there"
    )

    class Dies:
        name, model = "dies", "d"

        async def complete(self, request: ChatRequest) -> Any:
            raise AssertionError

        async def stream(self, request: ChatRequest) -> AsyncIterator[Any]:
            yield TextDelta("partial")
            raise LlmUnavailable("cut off")

    second = FakeLlmProvider([text_reply("x")])
    chain = FallbackLlm([Dies(), second])
    seen: list[Any] = []
    with pytest.raises(LlmUnavailable):
        async for e in chain.stream(REQUEST):
            seen.append(e)
    assert [e.text for e in seen] == ["partial"] and second.requests == []


# ------------------------------------------------------------------------- registry
def settings(**kw: Any) -> Settings:
    return Settings(environment="test", **kw)


def test_the_default_is_the_fake_and_needs_no_key() -> None:
    assert build_llm(settings()).name == "fake"


@pytest.mark.parametrize("kind", ["openai", "anthropic"])
def test_a_real_provider_needs_a_key_and_a_model(kind: str) -> None:
    with pytest.raises(LlmNotConfigured):
        build_llm(settings(ai_provider=kind))
    with pytest.raises(LlmNotConfigured):
        build_llm(settings(ai_provider=kind, **{f"{kind}_api_key": SecretStr(KEY)}))
    with pytest.raises(LlmNotConfigured):
        build_llm(settings(ai_provider=kind, **{f"ai_{kind}_model": "m"}))
    ok = build_llm(
        settings(ai_provider=kind, **{f"{kind}_api_key": SecretStr(KEY), f"ai_{kind}_model": "m"})
    )
    assert ok.name == kind and ok.model == "m"


def test_a_fallback_provider_is_chained() -> None:
    chain = build_llm(
        settings(
            ai_provider="openai",
            ai_fallback_provider="anthropic",
            openai_api_key=SecretStr(KEY),
            anthropic_api_key=SecretStr(KEY),
            ai_openai_model="a",
            ai_anthropic_model="b",
        )
    )
    assert isinstance(chain, FallbackLlm) and chain.name == "openai"


# ----------------------------------------------------------------------- key custody
def test_keys_never_show_in_settings_or_provider_text() -> None:
    s = settings(openai_api_key=SecretStr(KEY), anthropic_api_key=SecretStr(KEY))
    assert KEY not in repr(s) + str(s) + str(s.model_dump())
    for provider in (
        OpenAIProvider(SecretStr(KEY), "m"),
        AnthropicProvider(SecretStr(KEY), "m"),
    ):
        assert KEY not in repr(provider) + str(provider)


def test_the_example_environment_has_no_ai_key_values() -> None:
    text = (APP.parents[1] / ".env.example").read_text(encoding="utf-8")
    values = dict(
        line.split("=", 1) for line in text.splitlines() if "=" in line and not line.startswith("#")
    )
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AI_OPENAI_MODEL", "AI_ANTHROPIC_MODEL"):
        assert values.get(name, "x").strip() == "", name


def test_no_source_file_holds_a_key_like_literal() -> None:
    for path in (APP / "ai").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "sk-" not in text.replace("task-", "").replace("risk-", "").replace("desk-", ""), (
            path.name
        )


# ---------------------------------------------------------------------- architecture
CONSUMER_SAFE = {"base", "models", "errors", "resilience", "registry"}
ROOT = "app.ai.providers"


def _imports(path: Path) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
            if node.module == ROOT:
                found.extend(f"{ROOT}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Import):
            found.extend(a.name for a in node.names)
    return found


def test_consumers_import_only_the_interface_modules() -> None:
    package = APP / "ai" / "providers"
    offenders = []
    for path in APP.rglob("*.py"):
        if package in path.parents:
            continue
        for module in _imports(path):
            if (
                module.startswith(ROOT + ".")
                and module.removeprefix(ROOT + ".").split(".")[0] not in CONSUMER_SAFE
            ):
                offenders.append(f"{path.relative_to(APP)} imports {module}")
    assert offenders == []


def test_the_tool_layer_does_not_import_providers() -> None:
    for path in (APP / "ai" / "tools").rglob("*.py"):
        assert not [m for m in _imports(path) if m.startswith(ROOT)], path.name
