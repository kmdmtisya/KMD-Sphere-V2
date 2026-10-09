# CLAUDE.md

## Execution control (read first)
Work is driven by `EXECUTION_PLAN.md` (roadmap), `TASK_CHECKLIST.md` (state), `QUALITY_GATES.md` (QG-01..QG-12) and `EXECUTION_LOG.md`.
- Follow the per-task procedure in `EXECUTION_PLAN.md` section 4.2. Do one task, wave or phase at a time and never start the next phase without the user's approval.
- Change task, gate and approval state only with `python scripts/track.py ...`; never hand-edit statuses, checkboxes or timestamps, and never fabricate evidence.
- Mark a task complete only after its acceptance criteria and quality gates are verified.

## Project
WealthSphere - AI-Powered Portfolio & Wealth Intelligence Platform.

## Required Reading Order
Before changing code, read:
1. `docs/SOLUTION_INTENT.md`
2. `docs/WEALTHSPHERE_CLAUDE_CODE_IMPLEMENTATION_GUIDE.md`
3. Relevant files under `/docs`
4. Existing code and tests for the affected module

`docs/SOLUTION_INTENT.md` defines the product direction. Do not implement features that conflict with it without explicitly documenting the conflict.

## Mission
Build a secure, scalable Android/iOS personal wealth intelligence platform using the architecture and engineering constraints defined by the project documents.

## Non-Negotiable Rules
- Do not bypass authentication or authorization.
- Do not give an LLM unrestricted database, SQL, shell, or arbitrary URL access.
- Do not put API keys, credentials, tokens or secrets in source code.
- Do not use binary floating point as the authoritative representation of money.
- Do not modify unrelated modules during a scoped task.
- Do not delete or weaken tests merely to make a build pass.
- Do not weaken validation, authorization or security controls to fix an error.
- All database schema changes require migrations.
- All API changes require typed request/response schemas and OpenAPI compatibility.
- All financial formulas require deterministic implementations and automated tests.
- The backend is authoritative for financial calculations; Flutter must not become the source of financial truth.
- Every AI tool call accessing user information must enforce server-side authorization.
- AI investment analysis must distinguish facts, calculations, assumptions and AI interpretation.
- AI opportunity output must include risks, assumptions, data freshness and evidence/source references where available.
- Never present a forecast, scenario or opportunity score as a guaranteed return.
- Do not implement automatic trade execution unless a future approved requirement explicitly introduces it.
- Prefer small, reviewable changes.

## Architecture Defaults
- Mobile: Flutter/Dart.
- State: Riverpod.
- Navigation: GoRouter.
- HTTP: Dio.
- Backend: Python/FastAPI.
- Validation: Pydantic v2.
- Persistence: PostgreSQL + SQLAlchemy 2 + Alembic.
- Cache: Redis.
- Identity: Keycloak/OIDC unless superseded by an approved ADR.
- Messaging: RabbitMQ/Celery where asynchronous processing is required.
- AI: dedicated orchestrator with allow-listed tools.
- Infrastructure: Docker and Terraform.
- Start as a modular monolith; extract services only for justified scale or operational reasons.

## Financial Data Rules
- Use `NUMERIC/DECIMAL` for monetary values and precision-sensitive quantities.
- Preserve transaction currency and relevant FX information.
- Prefer append-oriented/auditable transaction history.
- Timestamp valuations, prices, FX data and research.
- Make rounding conventions explicit and test them.
- Financial calculations must not depend on an LLM.

## AI Rules
The LLM is an explanation/orchestration layer, not the source of truth.

Approved pattern:
`User -> AI Orchestrator -> Authorization -> Allow-Listed Tool -> Deterministic/Trusted Result -> LLM -> Validated Response`

Never:
- expose raw database credentials;
- construct unrestricted SQL from LLM output;
- trust model-generated market facts without provider evidence;
- allow cross-user portfolio access;
- allow model-generated URLs to be fetched without controls;
- invent expected returns.

## Security Rules
- Use OAuth/OIDC Authorization Code + PKCE for mobile.
- Support MFA.
- Store tokens only in secure mobile storage.
- Validate ownership/authorization server-side on every protected resource.
- Add tests for IDOR/cross-user access.
- Keep secrets outside source control.
- Use TLS in deployed environments.
- Maintain audit events for material financial changes and AI recommendation/tool activity.
- Do not log secrets or unnecessary sensitive financial payloads.

## Development Workflow
For every task:
1. Read the relevant project documentation.
2. Inspect existing implementation and tests.
3. State a concise implementation plan.
4. Identify assumptions and affected modules.
5. Implement the smallest coherent change.
6. Add/update tests.
7. Run formatter, linter, type checks and tests.
8. Report commands executed.
9. List changed files.
10. Report remaining risks, failures or follow-up work honestly.

## Definition of Done
A feature is not complete until:
- acceptance criteria pass;
- relevant tests pass;
- authorization boundaries are preserved;
- financial calculations are tested;
- API schemas are documented;
- migrations exist where needed;
- mobile loading/error/empty states exist where relevant;
- logs/metrics are present where appropriate;
- no secrets are committed;
- AI structured output is validated where relevant;
- documentation is updated.

## Initial Development Order
1. Repository + CI
2. Identity
3. PostgreSQL schema
4. Portfolio + assets
5. Transactions + holdings
6. Multi-currency
7. Dashboard
8. Analytics
9. Compound calculator
10. Goals
11. Net worth + passive income
12. Market/FX integration
13. AI tool layer
14. AI Wealth Copilot
15. AI Investment Intelligence
16. Production hardening
17. Android/iOS release

Do not start by building the AI recommendation interface. Establish trusted portfolio data, calculations, authorization and market-data provenance first.

## Mandatory UI/UX Rules (v1.1)
- Follow the `UI/UX Design Specification` in `docs/SOLUTION_INTENT.md` and the implementation guide.
- Build Android/iOS from a shared Flutter design system with semantic theme tokens.
- Primary tabs: Home, Portfolio, AI Wealth, Goals, More.
- Implement the 13 documented screens; prioritize Home, Portfolio, Calculator, Forecast, AI Wealth.
- Reuse shared chart, card, investment, goal, AI, risk and state widgets.
- Support dark/light mode, text scaling, accessibility, safe areas, loading/error/empty/offline states.
- Keep mock values explicitly labeled DEMO and do not imply mock investment opportunities are live.
- UI must not independently calculate financial truth or bypass AI tool authorization.
- Add Flutter widget and integration tests for navigation and key user journeys.
