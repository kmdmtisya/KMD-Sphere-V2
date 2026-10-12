"""Anthropic Messages adapter (P10-T05, ADR-0017).

Built against the documented API shape and tested against recorded payloads; it has not been run
against the live service (no key exists yet, and provider terms are reviewed first, ADR-0017
section 5). The key is sent only in the `x-api-key` header; it is held as a `SecretStr`, is not in
`repr`, and is never in an error or a log line.
"""

from collections.abc import AsyncIterator
from typing import Any

from pydantic import SecretStr

from app.ai.providers.errors import LlmAuthError, LlmInvalidOutput
from app.ai.providers.http import (
    HttpxLlm,
    LlmHttp,
    parse_json,
    parse_tool_arguments,
    raise_for_status,
)
from app.ai.providers.models import (
    ChatRequest,
    ChatResponse,
    Message,
    StreamDone,
    StreamEvent,
    TextDelta,
    ToolCall,
    Usage,
)

URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"


def _messages(messages: tuple[Message, ...]) -> tuple[str, list[dict[str, Any]]]:
    """System text, and the conversation in the Messages format (tool results are user turns)."""
    system = "\n\n".join(m.content for m in messages if m.role == "system")
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            continue
        if m.role == "tool":
            block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)  # several results answer one assistant turn
            else:
                out.append({"role": "user", "content": [block]})
        elif m.role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.content:
                blocks.append({"type": "text", "text": m.content})
            blocks += [
                {"type": "tool_use", "id": c.id, "name": c.name, "input": dict(c.arguments)}
                for c in m.tool_calls
            ]
            out.append({"role": "assistant", "content": blocks or m.content})
        else:
            out.append({"role": "user", "content": m.content})
    return system, out


def build_body(model: str, request: ChatRequest, *, stream: bool) -> dict[str, Any]:
    system, messages = _messages(request.messages)
    body: dict[str, Any] = {
        "model": model,
        "max_tokens": request.max_output_tokens,
        "messages": messages,
    }
    if system:
        body["system"] = system
    if request.tools:
        body["tools"] = [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in request.tools
        ]
    if request.temperature is not None:
        body["temperature"] = request.temperature
    if stream:
        body["stream"] = True
    return body


class AnthropicProvider:
    def __init__(
        self, api_key: SecretStr, model: str, http: LlmHttp | None = None, url: str = URL
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._http = http or HttpxLlm()
        self._url = url

    def __repr__(self) -> str:
        return f"AnthropicProvider(model={self._model!r})"

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def model(self) -> str:
        return self._model

    def _headers(self) -> dict[str, str]:
        key = self._api_key.get_secret_value()
        if not key:
            raise LlmAuthError("anthropic is not configured (no API key)")
        return {
            "x-api-key": key,
            "anthropic-version": API_VERSION,
            "Content-Type": "application/json",
        }

    async def complete(self, request: ChatRequest) -> ChatResponse:
        result = await self._http.post(
            self._url, self._headers(), build_body(self._model, request, stream=False)
        )
        raise_for_status("anthropic", result)
        data = parse_json("anthropic", result.text)
        try:
            text: list[str] = []
            calls: list[ToolCall] = []
            for block in data["content"]:
                if block["type"] == "text":
                    text.append(block["text"])
                elif block["type"] == "tool_use":
                    arguments = block.get("input") or {}
                    if not isinstance(arguments, dict):
                        raise LlmInvalidOutput("anthropic sent tool input that is not an object")
                    calls.append(ToolCall(str(block["id"]), str(block["name"]), arguments))
            usage = data.get("usage") or {}
            return ChatResponse(
                content="".join(text),
                tool_calls=tuple(calls),
                usage=Usage(int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))),
                provider="anthropic",
                model=str(data.get("model") or self._model),
                request_id=data.get("id"),
                finish_reason=str(data.get("stop_reason") or "stop"),
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            raise LlmInvalidOutput("anthropic answered in an unexpected shape") from None

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        text: list[str] = []
        blocks: dict[int, dict[str, Any]] = {}
        in_tokens = out_tokens = 0
        model, request_id, finish = self._model, None, "stop"
        async for line in self._http.post_stream(
            self._url, self._headers(), build_body(self._model, request, stream=True)
        ):
            if not line.startswith("data:"):
                continue
            event = parse_json("anthropic", line[5:].strip())
            try:
                kind = event["type"]
                if kind == "message_start":
                    message = event["message"]
                    model = str(message.get("model") or model)
                    request_id = message.get("id")
                    in_tokens = int((message.get("usage") or {}).get("input_tokens", 0))
                elif kind == "content_block_start":
                    block = event["content_block"]
                    blocks[int(event["index"])] = {
                        "type": block["type"],
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "args": "",
                    }
                elif kind == "content_block_delta":
                    delta = event["delta"]
                    if delta["type"] == "text_delta":
                        text.append(delta["text"])
                        yield TextDelta(delta["text"])
                    elif delta["type"] == "input_json_delta":
                        blocks[int(event["index"])]["args"] += delta.get("partial_json", "")
                elif kind == "message_delta":
                    finish = str((event.get("delta") or {}).get("stop_reason") or finish)
                    out_tokens = int((event.get("usage") or {}).get("output_tokens", out_tokens))
                elif kind == "error":
                    raise LlmInvalidOutput("anthropic reported an error while streaming")
            except (KeyError, TypeError, ValueError, AttributeError):
                raise LlmInvalidOutput("anthropic streamed an unexpected shape") from None
        calls = tuple(
            ToolCall(b["id"], b["name"], parse_tool_arguments("anthropic", b["args"]))
            for _, b in sorted(blocks.items())
            if b["type"] == "tool_use"
        )
        yield StreamDone(
            ChatResponse(
                content="".join(text),
                tool_calls=calls,
                usage=Usage(in_tokens, out_tokens),
                provider="anthropic",
                model=model,
                request_id=request_id,
                finish_reason=finish,
            )
        )
