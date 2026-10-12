# ADR-0017: LLM provider, key custody, budget and retention (DEC-05)

Status: Accepted (proposed in P10-T01, 2026-10-12; choices made by the user on 2026-10-12). **Provider data-handling terms are reviewed before first use of each provider (section 5).**

## Context
The AI Wealth Copilot (P10) needs an LLM as an explanation and orchestration layer. The model is not a source of truth ([ai-governance.md](../ai-governance.md)); tools supply the facts. The provider receives minimised prompts, so which provider, who holds the key, what it may cost and how long conversations are kept are security and privacy decisions, not only engineering ones.

## Decision
1. **Two providers from the start, behind one interface.** `LlmProvider` (chat completion with tool calls and structured output, token usage, request id, timeouts) has an **OpenAI** adapter and an **Anthropic** adapter; configuration picks the active one (and can name a fallback). Tools, the orchestrator and the screens never import a vendor SDK; an architecture test enforces it (as for market data, ADR-0014). A deterministic **fake provider** serves development and tests with no key and no network.
2. **Models are configuration, not code.** The model id and version for each provider are settings, pinned per environment and recorded with every run (audit and the stored answer). A change of model re-runs the evaluation suite (QG-07) before it is used in production.
3. **Key custody.** One key per provider **per environment** (development, staging, production), each with a provider-side spend cap. Keys are read from the server environment locally and from the secret manager in deployed environments (P14). They are `SecretStr` settings, sent only in the request header, never in the mobile app, source, logs, traces, errors or API responses, and covered by gitleaks. Rotating a key means changing the secret and restarting workers; a leaked key is revoked at the provider first.
4. **Budget.** Monthly cap **USD 50** across providers while in development and beta, a configuration value. The orchestrator tracks token cost per request; alarm at 80% of the cap; at 100% the AI answers "temporarily unavailable" (the rest of the app is unaffected). Per user: 30 questions a day, at most 20 tool calls per question, input length capped. All are settings.
5. **Retention.** Conversations are stored server-side per user, encrypted at rest with the database, for **90 days**, then deleted; the user can delete any conversation at any time and all are deleted with the account. Audit events (tool, hashed arguments, status, model/provider version, cost; no content) follow the audit policy. Prompts, answers and tool results are never written to logs or traces.
6. **Data minimisation to the provider** follows the classification in the governance document: no identity, no secrets, only the tool results a question needs.

## 5. Provider terms to review before first use (open items, not assumed)
For each provider, before its adapter is switched on with real data: whether API data is excluded from training by default; the retention period for API requests and whether zero/short retention can be enabled; where data is processed (regions) against the jurisdictions in DEC-10; sub-processors; breach notification; and the commercial terms for the expected use. I have not read these terms in this session and record none of them as accepted. Until the review is recorded here, the adapters run only against the fake provider and synthetic data.

## Consequences
- Both adapters double the integration and test surface; the shared contract tests (as for market data) keep them honest.
- Vendor choice can change without touching tools or screens.
- No real user data reaches a provider until the terms review above is recorded.
