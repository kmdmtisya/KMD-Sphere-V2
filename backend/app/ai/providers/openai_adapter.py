"""OpenAI Chat Completions adapter (P10-T05, ADR-0017).

Built against the documented API shape and tested against recorded payloads; it has not been run
against the live service (no key exists yet, and provider terms are reviewed first, ADR-0017
section 5). The key is sent only in the Authorization header; it is held as a `SecretStr`, is not
in `repr`, and is never in an error or a log line.
"""

import json
from collections.abc import AsyncIterator, Mapping
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

URL = "https://api.openai.com/v1/chat/completions"


def _message(m: Message) -> dict[str, Any]:
    if m.role == "tool":
        return {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
    out: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.tool_calls:
        out["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": json.dumps(dict(c.arguments))},
            }
            for c in m.tool_calls
        ]
    return out


def build_body(model: str, request: ChatRequest, *, stream: bool) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [_message(m) for m in request.messages],
        "max_completion_tokens": request.max_output_tokens,
    }
    if request.tools:
        body["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in request.tools
        ]
    if request.temperature is not None:
        body["temperature"] = request.temperature
    if stream:
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    return body


def _tool_calls(raw: list[dict[str, Any]]) -> tuple[ToolCall, ...]:
    calls = []
    for item in raw:
        function = item.get("function") or {}
        name, call_id = function.get("name"), item.get("id")
        if not isinstance(name, str) or not isinstance(call_id, str):
            raise LlmInvalidOutput("openai sent a tool call without a name or id")
        calls.append(
            ToolCall(call_id, name, parse_tool_arguments("openai", function.get("arguments") or ""))
        )
    return tuple(calls)


class OpenAIProvider:
    def __init__(
        self, api_key: SecretStr, model: str, http: LlmHttp | None = None, url: str = URL
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._http = http or HttpxLlm()
        self._url = url

    def __repr__(self) -> str:
        return f"OpenAIProvider(model={self._model!r})"

    @property
    def name(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    def _headers(self) -> dict[str, str]:
        key = self._api_key.get_secret_value()
        if not key:
            raise LlmAuthError("openai is not configured (no API key)")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    async def complete(self, request: ChatRequest) -> ChatResponse:
        result = await self._http.post(
            self._url, self._headers(), build_body(self._model, request, stream=False)
        )
        raise_for_status("openai", result)
        data = parse_json("openai", result.text)
        try:
            choice = data["choices"][0]
            message = choice["message"]
            usage = data.get("usage") or {}
            return ChatResponse(
                content=message.get("content") or "",
                tool_calls=_tool_calls(message.get("tool_calls") or []),
                usage=Usage(
                    int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
                ),
                provider="openai",
                model=str(data.get("model") or self._model),
                request_id=data.get("id"),
                finish_reason=str(choice.get("finish_reason") or "stop"),
            )
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise LlmInvalidOutput("openai answered in an unexpected shape") from None

    async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
        text: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        usage, model, request_id, finish = Usage(), self._model, None, "stop"
        async for line in self._http.post_stream(
            self._url, self._headers(), build_body(self._model, request, stream=True)
        ):
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            chunk = parse_json("openai", payload)
            try:
                model = str(chunk.get("model") or model)
                request_id = chunk.get("id") or request_id
                if chunk.get("usage"):
                    u: Mapping[str, Any] = chunk["usage"]
                    usage = Usage(
                        int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))
                    )
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    if delta.get("content"):
                        text.append(delta["content"])
                        yield TextDelta(delta["content"])
                    for part in delta.get("tool_calls") or []:
                        slot = calls.setdefault(
                            int(part["index"]), {"id": "", "name": "", "args": ""}
                        )
                        slot["id"] = part.get("id") or slot["id"]
                        function = part.get("function") or {}
                        slot["name"] = function.get("name") or slot["name"]
                        slot["args"] += function.get("arguments") or ""
                    finish = str(choice.get("finish_reason") or finish)
            except (KeyError, TypeError, ValueError, AttributeError):
                raise LlmInvalidOutput("openai streamed an unexpected shape") from None
        tool_calls = _tool_calls(
            [
                {"id": c["id"], "function": {"name": c["name"], "arguments": c["args"]}}
                for _, c in sorted(calls.items())
            ]
        )
        yield StreamDone(
            ChatResponse(
                content="".join(text),
                tool_calls=tool_calls,
                usage=usage,
                provider="openai",
                model=model,
                request_id=request_id,
                finish_reason=finish,
            )
        )
