# LLM providers (P10-T05, ADR-0017)

Code: `backend/app/ai/providers/`. Consumers (the orchestrator, P10-T06) import `base`, `models`, `errors`, `resilience` and `registry` only; a test fails if anything else imports an adapter or the fake.

| Module | Role |
|---|---|
| `base.py` | `LlmProvider`: `name`, `model`, `complete(request)`, `stream(request)` |
| `models.py` | Vendor-neutral `Message`, `ToolCall`, `ChatRequest`, `ChatResponse` (content, tool calls, token usage, provider, **served model**, request id, finish reason), `TextDelta`, `StreamDone` |
| `openai_adapter.py` | OpenAI Chat Completions (`Authorization: Bearer`) |
| `anthropic_adapter.py` | Anthropic Messages (`x-api-key`, `anthropic-version`); system text lifted out, tool results sent as user turns |
| `fake.py` | Scripted provider: queued replies, records every request, can fail or stream. No network, no key |
| `resilience.py` | `RetryingLlm` (transient failures retried once; refused key and bad request are not) and `FallbackLlm` (next provider on unavailable, key refused, not configured or unusable output; streaming falls back only before the first token) |
| `registry.py` | The one place that names vendors: `build_llm(settings)` |
| `http.py` | The HTTP boundary: status -> error mapping, URL/key/prompt/body never in messages, tool arguments parsed as untrusted JSON objects |

## Configuration (`.env.example`)
`AI_PROVIDER` (`fake` default | `openai` | `anthropic`), optional `AI_FALLBACK_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `AI_OPENAI_MODEL`, `AI_ANTHROPIC_MODEL`, `AI_REQUEST_TIMEOUT_SECONDS`, `AI_MAX_OUTPUT_TOKENS`. **There is no default model**: a real provider without a key and a model name refuses to build (`LlmNotConfigured`). Model and version actually served come back in every response and are recorded with each run.

## Key custody
Keys are `SecretStr` settings from the environment (secret manager in deployed environments), sent only in the request header, never in `repr`, errors, logs, URLs or responses (tests feed hostile response bodies and transport errors that echo the key). One key per environment (ADR-0017). The mobile app never holds one.

## Honest status
Both adapters are built against the documented request and response shapes and tested against payloads in those shapes and SSE streams. **Neither has been run against the live service**: no key exists, and provider data-handling terms are reviewed first (ADR-0017 section 5). Treat the first live run as a verification step; the contract tests will need re-recording from real responses.
