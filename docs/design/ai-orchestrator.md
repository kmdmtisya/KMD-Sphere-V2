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
3. **Review** (P10-T08): the final text goes through the answer policy described below. Nothing is streamed before it passes, so a rejected answer is never partly shown. A reply that fails is sent back to the model once (`AI_MAX_ANSWER_RETRIES`) with fixed wording per problem code; a reply that still fails is refused with `invalid_answer` and is neither stored nor shown.
4. **Stream** the events, then store the assistant message, the tool-call records and one `ai.chat.answer` audit event (model, provider, tool count, token counts; no content).

## Events

`event: <type>` plus one JSON `data:` line, types `tool`, `source`, `token`, `done`, `error`.

| Type | Carries |
|---|---|
| `tool` | `name`, `status` (`running`, `ok`, `error`), `error_code`; never arguments or results |
| `source` | `tool`, `as_of`, `complete`: the trusted data the answer rests on |
| `token` | `text`, pieces of the reviewed answer |
| `done` | `conversation_id`, `message_id`, `model`, `provider`, `tool_calls`, `structured` (the four sections and caveats, or `{"refusal": category}`) |
| `error` | fixed `code` (`ai_unavailable`, `invalid_answer`, `refused`) and message; provider error text never reaches the client |

## The answer policy (P10-T08)

The model is told to reply with one JSON object: `observed` and `calculated` (each item `{text, source}`), `assumptions`, `interpretation`. The server parses it strictly (unknown keys, wrong types, over-long text, prose or empty answers are rejected) and then checks, in order:

| Check | Problem code | Rule |
|---|---|---|
| Structure | `not_structured` | exactly the object above; the model cannot write `caveats` |
| Sources | `source_not_used` | every `source` is a tool that returned data in this turn |
| Number provenance | `unsupported_figure` | every figure equals a figure in a tool result, a tool argument or a user message of the turn, allowing rounding to the precision shown (5,505 for 5505.37; 5.5k; 12.5% for 12.5 or 0.125). Bare integers up to 10, years and the digits of dates, times, ids and labels such as Q4 are not figures |
| Guarantee language | `guarantee_language`, `certainty_language` | "guaranteed", "risk-free" and similar words are allowed only in a denial ("not a guarantee"); "no risk", "can't lose", "sure thing", "definitely will" are never allowed |
| Forecast wording | `unhedged_forecast` | when a forecast or goal tool ran, "will reach / be worth / have ..." needs a hedge (could, if, under these assumptions, scenario ...) |
| Links | `link_in_answer` | no URLs or `javascript:`/`data:` addresses |

The checks work on strings and give codes, never the offending text; the audit event `ai.chat.rejected` records the codes and retries, not the reply.

**Server-added qualifications** (`caveats`, whatever the model wrote): tool data that is incomplete or older than `AI_STALE_AFTER_HOURS` (48) is named as stale; tools that failed are named as not retrieved; any forecast or goal estimate carries "illustrations under the stated assumptions, not predictions or guaranteed returns".

**Refusals before the model** (`ai.chat.refused`, outcome denied): placing orders or moving money, promising or guaranteeing returns, other users' data, and requests for instructions, secrets or "ignore your rules". The rules are narrow on purpose: "should I buy this ETF?" and "is my return guaranteed?" are answered. They are the plain-request floor; the tool allow-list, the server-side scope and the answer checks hold regardless of phrasing.

Known limits: the number check cannot tell a correct calculation from a coincidental match, and a model can restate a supported figure misleadingly; text without digits ("a million") escapes it. These are covered by the quality suite (P10-T09) and the human review in the phase gate.

## Refusals and scope

- A tool name outside the allow-list, arguments that do not fit the tool's schema (including a smuggled `user_id`), or an over-budget call return a fixed error to the model and are recorded and audited (`unknown_tool`, `invalid_arguments`, `rate_limited`, `limit_reached`); nothing runs.
- **Scope** is validated on the server (the portfolio must be the caller's) and fixed for the life of a conversation. Every tool that takes a `portfolio_id` is run with the scoped one; a call naming another portfolio is refused as `out_of_scope`. Tools that are not about one portfolio (net worth, goals, forecasts) are the user's own data and stay available.
- Free text from the user or from tool results is never placed in the system prompt.

## Not logged

Questions, answers, prompts and tool results are not logged anywhere (a test checks the logs).

## Known limits

- Tokens are sent after the answer is reviewed, so the first token arrives when generation ends, not while it runs. This is deliberate (validation before display); token-level streaming of an unreviewed answer is not offered.
- Run against the scripted fake provider only; the real adapters wait for the provider terms review recorded as open in ADR-0017.
