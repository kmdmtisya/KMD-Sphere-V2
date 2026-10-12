# AI orchestrator and chat API (P10-T06)

Pattern: `User -> Orchestrator -> authorization -> allow-listed tool -> deterministic result -> LLM -> validated response` ([AI governance](../ai-governance.md)). Providers: [ai-providers.md](ai-providers.md). Tools: [ai-tools.md](ai-tools.md). Storage: [ai-conversations.md](ai-conversations.md).

## Endpoints (`/api/v1/ai`)

| Route | Purpose |
|---|---|
| `POST /chat` | Ask a question; the answer streams as server-sent events |
| `GET /conversations`, `GET /conversations/{id}` | Stored history (owner only; foreign ids are 404) |
| `DELETE /conversations/{id}`, `DELETE /conversations` | Delete one or all conversations |

Request: `{message (1..4000 chars, not blank), conversation_id?, scope?: {portfolio_id?}}`; unknown fields are refused. Errors that can be answered before streaming are ordinary problem+json: 401, 404 (conversation or portfolio that is not yours), 422 (blank, too long, scope that contradicts the conversation), 429 with `Retry-After` (30 questions per user per rolling 24 hours, counted from stored questions so it holds across processes), 503 (no model configured).

## One question

1. **Accept** (`prepare`): validate the scope against the caller's portfolios, load or create the conversation, enforce the daily limit, store the question.
2. **Loop** (`answer`): send the fixed system prompt (plus today's date and the scope), the last `AI_HISTORY_MESSAGES` stored messages and the 12 tool descriptions to the model. When it asks for tools, run each one through `ToolRegistry.execute` only, with the identity taken from the access token and never from the model; feed the results back as data. At most `AI_MAX_TOOL_CALLS_PER_QUESTION` (20) tool calls and `AI_MAX_MODEL_ROUNDS` (8) model rounds; once the call budget is spent or on the last round no tools are offered, so the model must answer.
3. **Review**: the final text goes through the answer policy (P10-T06: must not be empty; P10-T08 replaces it with the full checks). Nothing is streamed before it passes, so a rejected answer is never partly shown.
4. **Stream** the events, then store the assistant message, the tool-call records and one `ai.chat.answer` audit event (model, provider, tool count, token counts; no content).

## Events

`event: <type>` plus one JSON `data:` line, types `tool`, `source`, `token`, `done`, `error`.

| Type | Carries |
|---|---|
| `tool` | `name`, `status` (`running`, `ok`, `error`), `error_code`; never arguments or results |
| `source` | `tool`, `as_of`, `complete`: the trusted data the answer rests on |
| `token` | `text`, pieces of the reviewed answer |
| `done` | `conversation_id`, `message_id`, `model`, `provider`, `tool_calls` |
| `error` | fixed `code` (`ai_unavailable`, `invalid_answer`, `refused`) and message; provider error text never reaches the client |

## Refusals and scope

- A tool name outside the allow-list, arguments that do not fit the tool's schema (including a smuggled `user_id`), or an over-budget call return a fixed error to the model and are recorded and audited (`unknown_tool`, `invalid_arguments`, `rate_limited`, `limit_reached`); nothing runs.
- **Scope** is validated on the server (the portfolio must be the caller's) and fixed for the life of a conversation. Every tool that takes a `portfolio_id` is run with the scoped one; a call naming another portfolio is refused as `out_of_scope`. Tools that are not about one portfolio (net worth, goals, forecasts) are the user's own data and stay available.
- Free text from the user or from tool results is never placed in the system prompt.

## Not logged

Questions, answers, prompts and tool results are not logged anywhere (a test checks the logs).

## Known limits

- Tokens are sent after the answer is reviewed, so the first token arrives when generation ends, not while it runs. This is deliberate (validation before display); token-level streaming of an unreviewed answer is not offered.
- Run against the scripted fake provider only; the real adapters wait for the provider terms review recorded as open in ADR-0017.
