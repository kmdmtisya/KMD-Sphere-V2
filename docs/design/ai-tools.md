# AI tool framework (P10-T02)

Code: `backend/app/ai/tools/` (`base.py`, `registry.py`, `factory.py`). Policy: [ai-governance.md](../ai-governance.md); threats: [ai-threat-model.md](../ai-threat-model.md).

- **One door.** `ToolRegistry.execute(name, arguments, context)` is the only way a tool runs.
- **Who is asking** comes from `ToolContext` (user id, DB session, correlation id, model, provider), built by the orchestrator from the authenticated request. Tool argument models forbid unknown fields, so the model cannot pass a `user_id` (or anything else undeclared). A call without a context is refused.
- **Allow-list.** Only the 12 names in `ALLOWED_TOOLS` can be registered; a test keeps it equal to the table in the governance document. There is no SQL, shell, URL or write tool to call; a static test fails if anything under `app/ai/tools` imports a network, process, raw-SQL or file module.
- **Per call:** per-user budget (default 60 a minute), argument validation, timeout (default 10 s, per-tool override), result validated against the tool's result model and capped in size (default 32 KB), then **one audit event** `ai.tool.call` by `Actor.ai(user)`: tool, SHA-256 of the arguments (not the arguments), status, model, provider, duration and correlation id. Refusals are audited too, as `denied`, without their arguments.
- **What the model sees on failure** is a short code and a fixed message: `no_user_context`, `unknown_tool`, `rate_limited`, `invalid_arguments`, `not_found` (also for another user's resource, exactly as the API answers), `invalid`, `timeout`, `too_large`, `internal`. Exception text never reaches the model or the audit row.
- **Results** are `ToolData` subclasses: structured, with `as_of` and `complete`; money stays decimal strings.
- Settings: `AI_TOOL_CALLS_PER_MINUTE`, `AI_TOOL_TIMEOUT_SECONDS`, `AI_TOOL_MAX_RESULT_BYTES`.

## Core read tools (P10-T03)
`backend/app/ai/tools/core_read.py` registers five tools. Each calls the same service as the API route and returns the API's own answer, so the assistant's figures are the app's figures (tests compare them with the API responses).

| Tool | Arguments | Returns |
|---|---|---|
| `get_portfolio_summary` | optional `portfolio_id`, optional `currency` | the user's portfolios (id, name, currency) and the summary of one portfolio or of all combined; start here to learn ids |
| `get_portfolio_allocation` | `portfolio_id` | allocation by class, currency, country, sector; concentration |
| `get_portfolio_performance` | `portfolio_id` | profit, simple and money-weighted return, plus volatility, drawdown and time-weighted return (the value series is not sent) |
| `get_net_worth` | optional `currency` | assets, liabilities, breakdown, FX rates used, completeness |
| `get_goal_progress` | optional `goal_id` | all goals with status, or one goal's detail; carries the "estimates, not guarantees" notice |

The analytics mapping (`performance_out`, `allocation_out`, `risk_out`) moved from the API handlers to `portfolio/analytics_views.py` so both use one implementation. Results always carry a time-zone-aware `as_of` (services that report a UTC day as midnight are stamped UTC) and `complete`. A foreign or unknown id answers `not_found`, identical for both; the id is never echoed.
