# AI Governance

Derived from CLAUDE.md (AI Rules), `SOLUTION_INTENT.md` sections 14-20 and 28-29 and the implementation guide sections 9-10. The AI threat model and provider policy are completed in P10-T01.

## Role of the LLM
The LLM is an explanation and orchestration layer, **not** a source of truth. It is never authoritative for balances, transactions, calculations, market prices, FX rates or ownership. It must not invent expected returns.

## Approved pattern
`User -> AI Orchestrator -> authorization -> allow-listed tool -> deterministic or trusted result -> LLM -> validated response`

## Hard prohibitions
- No raw database credentials or unrestricted SQL for the model.
- No shell tool and no fetching of model-generated URLs.
- No cross-user portfolio access.
- No automatic trade execution.
- No guaranteed-return, "certain" or "guaranteed winner" language.

## Tool contract
Allow-listed tools: `get_portfolio_summary`, `get_portfolio_allocation`, `get_portfolio_performance`, `get_net_worth`, `get_goal_progress`, `run_compound_forecast`, `run_goal_forecast`, `get_market_snapshot`, `search_investment_universe`, `get_asset_research`, `compare_assets`, `run_portfolio_risk_analysis`.

Every tool must:
1. receive the authenticated user context;
2. verify resource ownership server-side;
3. validate inputs with Pydantic and return structured JSON with as-of timestamps;
4. enforce timeouts and rate limits;
5. emit an audit event (tool name, actor, timestamp, arguments hash, result status, model version, correlation ID);
6. redact secrets and sensitive tokens from logs.

## Answer structure
Every answer separates:
- **Observed data** (trusted facts with source and as-of time);
- **Calculated data** (deterministic WealthSphere results);
- **Assumptions** (user-selected or explicitly sourced);
- **AI interpretation** (the model's explanation of the above).

Outputs are validated against schemas before reaching the user; invalid output is rejected and retried or refused. Stale, missing or contradictory data is stated explicitly.

## Investment opportunities
Pipeline: eligibility filters -> market, fundamental and macro evidence -> quantitative features -> explainable scoring -> portfolio compatibility and suitability -> retrieved research -> LLM explanation from the retrieved evidence only -> schema validation -> persisted run.

Each opportunity includes instrument and asset class, thesis, why it surfaced, evidence with sources and as-of time, risk level and key risks, assumptions, portfolio and diversification impact, research horizon and a score explanation where scoring is used. Scores are analytical aids, not promises. Actions are Research, Compare and Simulate only.

## Quality and testing
Structured-output validation, prompt-injection, cross-user, tool-permission, hallucination-regression, stale/missing-data and citation-preservation suites, using documented evaluation datasets and acceptance thresholds (QG-07, DEC-17). Model, provider and version are recorded with each run.

## Provider policy
OpenAI first behind a provider abstraction; keys stay server-side in a secret manager. Provider data-handling and retention terms are reviewed and approved before use (P10-T01).
