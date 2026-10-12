# Live Copilot on mobile (P10-T10)

Server side: [ai-orchestrator.md](ai-orchestrator.md). The app talks to `POST /api/v1/ai/chat` and the conversation routes; nothing about what the assistant says is written in Dart.

## Data source

`copilotRepositoryProvider` follows `WS_DATA_SOURCE`: demo mode plays the scripted fixtures and says DEMO; live mode uses `LiveCopilotRepository`. In live mode the screen shows no DEMO label, its own introduction and suggested questions (localised), and the history button.

## Streaming

`LiveCopilotRepository.ask` posts the question and reads the response as server-sent events (`parseSse`, tolerant of chunk boundaries anywhere, CRLF, comments, multi-byte characters). The server checks a whole answer before it sends any of it, so the order is: `tool` (which data is being read), `source` (the data the answer rests on, with its as-of time), `token` (the answer text), `done` (the validated answer in four sections plus the server's notices). The repository turns that into the events the screen already shows:

| Server event | App event |
|---|---|
| `tool` running | progress line "Checking your net worth..." (named in the user's language from the tool id) |
| `source` | an evidence chip (named data, WealthSphere, as-of time); a source without a time is not shown |
| `done` with `structured` | the sections: observed, calculated, assumptions, interpretation, and the notices as "Please note" |
| `done` with a refusal | the refusal card with the server's fixed text |
| `error` | the server's fixed message with a retry |
| `token` | only the fallback text when `done` has no sections |

A stream that ends without `done` or `error`, or an event that does not have the expected shape, is a failure, never a half answer shown as complete. Unknown event types from a newer server are ignored. The first token arrives when the server has finished and checked the answer (see "Known limits" in the server note), so the app shows the progress line while it works; the request waits up to 90 seconds.

## Scope

The scope chip is sent as `scope.portfolio_id` for a portfolio only; the all-portfolios view, a forecast and a goal narrow nothing on the server, and the scope sheet says so. The server validates the portfolio and fixes the scope for the conversation, so a changed or removed scope starts a new conversation in the app (it never sends a scope that contradicts a stored one).

## History

A history button (live mode only) opens the stored conversations: loading, error with retry, empty, list. Opening one shows its questions and checked answers and continues it with the next question; deleting one or all asks first for all; deleting the open conversation clears the screen. The sheet states the retention (90 days, per ADR-0017). The first question starts a new stored conversation and the app keeps its id for the next one; "New conversation" forgets it.

## Failures

| Cause | Message |
|---|---|
| Daily limit (429) | "You have reached today's limit of questions. Try again later." |
| Assistant down (5xx) | "The assistant is unavailable right now. Try again shortly." |
| Anything else (network, shape) | "The assistant couldn't answer. Try again." |

Raw errors, correlation ids and server text other than the fixed `error` messages are never shown.

## Tests

Unit: SSE parser, event mapping, request body, HTTP failures, conversation parsing, controller (continuity, scope change, failure messages, stop). Widget: live empty state, answer sections and notices, named sources, scope chip, refusal, retry, offline, history states, deletion, accessibility at 2x text. End to end: journey 7 asks a question against the real backend (scripted model, real database) and sees the stored conversation.
