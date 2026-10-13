# AI Governance

Derived from CLAUDE.md (AI Rules), `SOLUTION_INTENT.md` sections 14-20 and 28-29 and the implementation guide sections 9-10. Completed in P10-T01 with the AI threat model ([ai-threat-model.md](ai-threat-model.md)) and the provider decision ([ADR-0017](adr/0017-llm-provider-and-key-custody.md)).

## Role of the LLM
The LLM is an explanation and orchestration layer, **not** a source of truth. It is never authoritative for balances, transactions, calculations, market prices, FX rates or ownership. It must not invent expected returns.

## Approved pattern
`User -> AI Orchestrator -> authorization -> allow-listed tool -> deterministic or trusted result -> LLM -> validated response`

## Hard prohibitions
- No raw database credentials or unrestricted SQL for the model.
- No shell tool and no fetching of model-generated URLs.
- No cross-user portfolio access.
- No automatic trade execution, and no tool that writes anything on the user's behalf.
- No guaranteed-return, "certain" or "guaranteed winner" language.
- No model-generated market fact without provider evidence from a tool.

## 1. Tool allow-list (P10-T01.1)

The model can call **only** these tools. There is no generic "query", "fetch", "execute" or "write" tool, and none can be added without changing this document and its test (`tests/ai/test_tool_allow_list.py`, P10-T02), which fails if the registry holds a name not listed here.

| Tool | Wraps (existing, authorised service) | Inputs | Returns |
|---|---|---|---|
| `get_portfolio_summary` | `SummaryService` | portfolio id or "all", optional currency | totals, P/L parts, freshness, unpriced assets |
| `get_portfolio_allocation` | `AllocationService` | portfolio id | slices by class, currency, country, sector; concentration |
| `get_portfolio_performance` | performance and risk services | portfolio id, period | return, money-weighted return, volatility, drawdown, completeness |
| `get_net_worth` | `NetWorthService` | optional currency | assets, liabilities, net worth, FX rates used |
| `get_goal_progress` | `GoalService` | goal id or list | progress, gap, scenarios, notice |
| `run_compound_forecast` | forecasting engine | validated forecast inputs | scenarios with the engine's notice |
| `run_goal_forecast` | forecasting engine | goal id, assumptions | required contribution, completion estimate |
| `get_market_snapshot` | `AssetPriceService`, FX service | asset ids (visible to the user), currency pairs | stored price, provider, as-of, stale flag |
| `search_investment_universe` | asset catalogue search | text, asset class filters | matching catalogue assets (id, symbol, name, class) |
| `get_asset_research` | `ResearchService` (P12-T05): public research only | asset id (visible to the user) | evidence items with source, licence status, published and retrieved times, or "none"; source URLs are provenance and never fetched |
| `compare_assets` | catalogue and price services | 2-5 asset ids | side-by-side stored facts with as-of |
| `run_portfolio_risk_analysis` | risk service | portfolio id | volatility, concentration, drawdown, with completeness |
| `get_current_fx_rate` | FX snapshot service (P11-T04) | two supported currency codes | rate, path, provider, time, status, snapshot id (indicative) |
| `get_historical_fx_rate` | FX service, historical rule (P11-T05) | two currency codes, a past day | that day's rate with provider and time, or not found |
| `convert_currency` | conversion engine (P11-T04/T05) | amount and currency, target, optional day | converted amount, rate, time, providers; audited as `ai_answer` (DEC-28) |
| `get_portfolio_value` | `SummaryService` under one snapshot (P11-T06) | portfolio id or all, optional currency | value, holdings, cash and every rate used |
| `get_fx_exposure` | `AllocationService` | portfolio id | value per currency (base currency) and weights |
| `get_portfolio_diagnosis` | `DoctorService` (P12-T01) | portfolio id | Portfolio Doctor findings with severity, thresholds and assumptions; hypothetical scenarios marked `is_trade: false` |

**Every tool is read-only.** None calls an external URL on its own initiative: data comes from our database through the same services the API uses, which already enforce ownership (ADR-0011).

### Tool contract
Every tool must:
1. receive the authenticated user context from the orchestrator (never from the model's arguments);
2. verify resource ownership server-side (an id the model supplies is only a request; foreign ids answer "not found" exactly as the API does);
3. validate inputs with Pydantic (types, ranges, allowed enums, id formats) and return structured JSON with as-of timestamps and a completeness flag;
4. enforce timeouts, row/size limits and per-user rate limits;
5. emit an audit event (tool name, actor `ai:<user>`, timestamp, `hash_arguments`, result status, model and provider version, correlation id);
6. redact secrets and tokens from logs, and never log result payloads.

### Explicitly not tools
Raw SQL or any database handle; shell or code execution; HTTP fetch of any URL; file system access; email or messaging; creating, changing or deleting portfolios, transactions, goals, alerts or settings; placing orders; reading other users' data; reading secrets or configuration; memory that persists across users.

## 2. Data classification and minimisation (P10-T01.1)

| Class | Examples | To the LLM provider? |
|---|---|---|
| Secret | tokens, API keys, passwords, DB credentials | **Never** |
| Identity | email, display name, user id, device tokens | **Never** (the model sees no identity; the user is "the user") |
| Account structure | portfolio names, asset names/symbols, goal names | Only the fields a tool result needs; user-typed free text (names, notes) is data, not instructions |
| Financial figures | balances, values, P/L, allocation | Only what the question needs, from tools; rounded as the API rounds |
| Public market data | stored prices, FX, catalogue facts | Yes, with provider and as-of |
| Conversation | the user's questions and the model's answers | Yes (needed); see retention |

Rules: the orchestrator sends the minimum tool results the question needs (it trims lists, drops unused fields, and never forwards raw API payloads). Pseudonymous ids replace database ids in the prompt where the model does not need them. Free text from users or from third-party sources is wrapped as quoted data and never placed in the system/instruction part of a prompt.

## 3. Logging and retention (P10-T01.1)

- **Audit (kept per the audit policy):** one event per tool call and per AI answer: who, which tool, `hash_arguments`, status, model and provider version, correlation id, token counts and cost. No prompts, answers or result payloads.
- **Conversation history** (so a chat can continue): stored server-side per user, encrypted at rest with the database, 90 days then deleted, deletable by the user at any time and with the account (limits to be confirmed in ADR-0017). Never shared across users; never used for anything but that user's chat.
- **Application logs:** correlation ids, tool names, status and timings only. Prompts, answers and tool results are never logged; the redaction module still runs on everything.
- **Provider side:** requests use the provider's no-training API setting and the shortest retention available; the actual terms are reviewed and approved in ADR-0017 before first use.

## 4. Answer structure
Every answer separates:
- **Observed data** (trusted facts with source and as-of time);
- **Calculated data** (deterministic WealthSphere results);
- **Assumptions** (user-selected or explicitly sourced);
- **AI interpretation** (the model's explanation of the above).

Outputs are validated against schemas before reaching the user; invalid output is rejected and retried or refused. Stale, missing or contradictory data is stated explicitly. Numbers in an answer must come from a tool result of the same turn; an answer containing a figure that no tool returned is rejected (P10-T08).

## 5. Investment opportunities
Pipeline: eligibility filters -> market, fundamental and macro evidence -> quantitative features -> explainable scoring -> portfolio compatibility and suitability -> retrieved research -> LLM explanation from the retrieved evidence only -> schema validation -> persisted run.

Each opportunity includes instrument and asset class, thesis, why it surfaced, evidence with sources and as-of time, risk level and key risks, assumptions, portfolio and diversification impact, research horizon and a score explanation where scoring is used. Scores are analytical aids, not promises. Actions are Research, Compare and Simulate only. Implemented in P12-T06 (docs/design/opportunities.md). The model receives only the candidates' deterministic facts, never the user's identity or amounts. Its explanation is refused if it adds a figure, a forecast, a guarantee, a link or unknown evidence; after one correction a fixed template is used. Runs are stored unchanged and audited (`ai.opportunities.run`). Instruments and research stay DEMO until licensed sources are approved.

## 6. Quality and testing
Structured-output validation, prompt-injection, cross-user, tool-permission, hallucination-regression, stale/missing-data and citation-preservation suites, using documented evaluation datasets and acceptance thresholds (QG-07, DEC-17). Model, provider and version are recorded with each run. Results, method and limits: [ai-evaluation.md](ai-evaluation.md).

## 7. Provider policy
OpenAI first behind a provider abstraction (so another provider can be swapped without touching tools or screens). Keys stay server-side in a secret manager; the model, monthly budget and per-user limits are configuration. Provider data-handling and retention terms are reviewed and approved before use. Decision record: [ADR-0017](adr/0017-llm-provider-and-key-custody.md).
