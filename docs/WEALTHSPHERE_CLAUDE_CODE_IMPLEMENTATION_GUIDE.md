# WealthSphere - Claude Code Implementation Guide

## 1. Project Mission

Build **WealthSphere**, a secure, cloud-ready, AI-powered personal wealth intelligence platform delivered initially as native-feeling **Android and iOS mobile applications from one Flutter codebase**.

The product must allow a user to:

- Create one or more investment portfolios.
- Track multiple investment vehicles and currencies.
- Record transactions, valuations, income, fees, liabilities, and cash flows.
- Measure investment and portfolio performance.
- Forecast wealth growth using compound-interest and recurring-contribution models.
- Create financial goals and measure progress.
- Track passive income and net worth.
- Receive current market and investment research through an AI Investment Intelligence module.
- Ask natural-language questions about the user's own portfolio.
- Explore investment opportunities using transparent evidence, risk analysis, suitability, and scenario modelling.
- Never present an AI forecast as a guaranteed return.

---

## 2. Product Principles

1. **Mobile first** - Android and iOS are first-class clients.
2. **API first** - all business capabilities are exposed through versioned APIs.
3. **Financial calculations are deterministic** - calculations happen in tested services, not inside the LLM.
4. **LLM is an explanation/orchestration layer** - market facts come from trusted data providers and portfolio facts from controlled APIs.
5. **Security by design** - encryption, MFA/biometrics, least privilege, audit trails, secrets management, and strong tenant/user isolation.
6. **Evidence before recommendation** - AI opportunity analysis must show data timestamp, rationale, risks, assumptions, and sources.
7. **Human decision remains final** - AI provides research and scenarios, not guaranteed outcomes.
8. **Extensible asset model** - new investment types can be added without redesigning the whole platform.
9. **Multi-currency from day one**.
10. **Cloud portable** - containerized services should run on AWS, GCP, OCI, or another Kubernetes/container platform.

---

## 3. Recommended Technology Stack

### Mobile
- Flutter
- Dart
- Riverpod for state management
- GoRouter for navigation
- Dio for HTTP networking
- Freezed/json_serializable for immutable models and JSON mapping
- flutter_secure_storage for secrets/tokens
- local_auth for Face ID / Touch ID / Android biometrics
- Drift or Isar for encrypted/offline local cache where appropriate
- fl_chart or Syncfusion Flutter Charts for financial visualizations
- Firebase Cloud Messaging / APNs abstraction for notifications

### Backend
- Python 3.13+
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic migrations
- PostgreSQL
- pgvector for embeddings/retrieval where required
- Redis for caching, sessions, rate limits, and short-lived computed data
- RabbitMQ + Celery for asynchronous jobs initially
- Pandas / NumPy for analytics jobs
- httpx for external API clients

### Identity and Security
- Keycloak as the preferred open-source identity provider
- OAuth 2.1 / OpenID Connect
- Authorization Code + PKCE for mobile
- MFA
- Mobile biometric unlock for local application access
- JWT access tokens with short expiry
- Refresh token rotation
- RBAC/ABAC where appropriate
- HashiCorp Vault or cloud-native secret manager
- TLS everywhere

### AI
- OpenAI API through a dedicated `ai-orchestrator` service
- Tool/function calling only against allow-listed internal services
- Retrieval layer for research documents
- Prompt/version registry
- AI audit records
- Guardrails and structured output schemas
- Provider abstraction so another LLM can be added later

### Cloud / DevOps
- Docker
- Docker Compose for local development
- GitHub Actions
- Terraform for infrastructure as code
- Managed PostgreSQL in production
- Managed Redis in production
- S3-compatible object storage
- Kubernetes only when operational scale justifies it; start with managed containers if simpler
- OpenTelemetry
- Prometheus
- Grafana
- Sentry or equivalent application error monitoring

---

## 4. High-Level Architecture

```text
Android App                 iOS App
     \                        /
      \------ Flutter -------/
               |
          API Gateway
               |
   +-----------+-------------+-------------------+
   |           |             |                   |
Identity   Portfolio      Analytics         AI Orchestrator
Service    Service        Service               |
   |           |             |           +------+------+
   |           |             |           |             |
   |       PostgreSQL     Redis/Jobs   Internal      Research/
   |                                    Tools       Market Tools
   |                                      |             |
   +--------------------------------------+-------------+
                                          |
                               Market / FX / News APIs
```

### Critical AI rule

Do **not** give the LLM unrestricted SQL access.

Use:

```text
User question
    -> AI Orchestrator
    -> Intent + authorization check
    -> Approved internal tool/API
    -> Deterministic query/calculation
    -> Structured result
    -> LLM explanation
    -> User
```

All tool calls must carry authenticated user context and enforce resource ownership server-side.

---

## 5. Suggested Repository Structure

```text
wealthsphere/
├── README.md
├── CLAUDE.md
├── .env.example
├── docker-compose.yml
├── Makefile
├── docs/
│   ├── architecture.md
│   ├── security.md
│   ├── ai-governance.md
│   ├── api-conventions.md
│   └── adr/
├── mobile/
│   └── wealthsphere_app/
│       ├── android/
│       ├── ios/
│       ├── lib/
│       │   ├── app/
│       │   ├── core/
│       │   ├── shared/
│       │   └── features/
│       │       ├── auth/
│       │       ├── dashboard/
│       │       ├── portfolios/
│       │       ├── investments/
│       │       ├── transactions/
│       │       ├── analytics/
│       │       ├── calculator/
│       │       ├── goals/
│       │       ├── income/
│       │       ├── net_worth/
│       │       ├── market/
│       │       ├── ai_wealth/
│       │       ├── watchlist/
│       │       └── settings/
│       └── test/
├── services/
│   ├── api-gateway/
│   ├── identity-service/
│   ├── portfolio-service/
│   ├── analytics-service/
│   ├── market-data-service/
│   ├── notification-service/
│   └── ai-orchestrator/
├── packages/
│   ├── python-common/
│   └── contracts/
├── infrastructure/
│   ├── terraform/
│   ├── docker/
│   └── k8s/
├── scripts/
└── .github/
    └── workflows/
```

For an MVP, services may begin as a **modular monolith** in one FastAPI deployment while preserving clear module boundaries. Extract services only when scale/team needs justify it.

---

## 6. Core Product Modules

### 6.1 Identity and User Profile
Features:
- Registration and login.
- Email verification.
- MFA.
- Password reset.
- Biometric application unlock.
- User profile.
- Base currency.
- Locale/time zone.
- Risk-profile questionnaire.
- Investment horizon.
- Financial goals.
- Notification preferences.
- Consent/privacy settings.

### 6.2 Portfolio Management
Features:
- Create multiple portfolios.
- Personal, family, retirement, geographic, or strategy portfolios.
- Portfolio base currency.
- Current valuation.
- Historical valuation.
- Allocation.
- Performance.
- Portfolio-level notes/documents.

### 6.3 Investment Vehicles
Initial supported asset classes:
- Stocks
- ETFs
- Bonds
- Money Market Funds
- Fixed Deposits
- Mutual Funds
- REITs
- Real Estate
- Cryptocurrency
- Commodities
- Pension/Retirement
- SACCO/Co-operative holdings
- Private Business/Private Equity
- Cash/Savings
- Custom Assets

Use a common `asset` entity plus type-specific metadata rather than creating an unrelated system for every asset class.

### 6.4 Transactions
Transaction types:
- BUY
- SELL
- DEPOSIT
- WITHDRAWAL
- DIVIDEND
- INTEREST
- COUPON
- RENT
- DISTRIBUTION
- FEE
- TAX
- TRANSFER_IN
- TRANSFER_OUT
- VALUATION_ADJUSTMENT

Transactions should be append-only where possible. Corrections should create reversing/adjustment entries to preserve auditability.

### 6.5 Portfolio Analytics
Calculate:
- Invested capital
- Market value
- Absolute gain/loss
- Percentage return
- Realized P/L
- Unrealized P/L
- Income
- Yield
- CAGR
- XIRR / money-weighted return
- Time-weighted return
- Allocation by asset class
- Allocation by country
- Allocation by sector
- Allocation by currency
- Concentration
- Historical portfolio value
- Drawdown
- Volatility
- Benchmark comparison (later)
- Sharpe ratio (later)

### 6.6 Compound Growth and Forecasting
Support:
- Initial lump sum.
- Recurring monthly/quarterly/annual contributions.
- Contribution escalation.
- Expected annual return.
- Compounding frequency.
- Time horizon.
- Inflation.
- Fees.
- Tax assumptions where explicitly modelled.
- Conservative/base/aggressive user-defined scenarios.

Core lump-sum formula:

```text
FV = PV * (1 + r)^n
```

Recurring contribution calculation must be implemented in deterministic tested code.

Outputs:
- Future nominal value.
- Inflation-adjusted value.
- Total contributions.
- Estimated investment growth.
- Year-by-year projection.
- Scenario comparison chart.
- Required contribution to reach a target.

Never label projected returns as guaranteed.

### 6.7 Financial Goals
Examples:
- Reach AED 1,000,000.
- Reach USD 1,000,000.
- Retirement.
- Education fund.
- House deposit.
- Business capital.
- Passive-income target.

Calculate:
- Current progress.
- Target gap.
- Required periodic contribution.
- Estimated completion date.
- On-track/off-track status based on stated assumptions.

### 6.8 Passive Income
Track:
- Dividends.
- Interest.
- Bond coupons.
- Rental income.
- REIT distributions.
- Business distributions.
- Staking/yield where supported.
- Other recurring investment income.

Views:
- Monthly income.
- Annual income.
- Income by asset.
- Yield by asset.
- Historical income.
- Projected income scenario.

### 6.9 Net Worth
Track:
- Investment assets.
- Property.
- Cash.
- Businesses.
- Other assets.
- Mortgages.
- Personal loans.
- Other liabilities.

Formula:

```text
Net Worth = Total Assets - Total Liabilities
```

### 6.10 Market Data and Research
Responsibilities:
- Asset prices.
- FX rates.
- Historical prices.
- Market metadata.
- Economic indicators where licensed.
- Research/news feeds where licensed.
- Data timestamps and provenance.
- Provider failover and caching.

Never scrape or redistribute data in violation of provider terms.

### 6.11 AI Wealth Copilot
Example questions:
- "What is my current net worth?"
- "How much did my portfolio grow this year?"
- "What is my exposure to cryptocurrency?"
- "Which investments generate most of my passive income?"
- "Show my Kenya investments."
- "Model AED 5,000 monthly for 15 years at 5%, 8%, and 12%."
- "How far am I from my AED 1 million goal?"

The AI must use internal tools for calculations and portfolio facts.

### 6.12 AI Investment Intelligence
Purpose: discover and explain **possible investment opportunities for research**, using current data and user context.

Inputs:
- User risk profile.
- Investment horizon.
- Available capital.
- Existing portfolio.
- Concentration.
- Currency exposure.
- Geography.
- Liquidity needs.
- Financial goals.
- Current market prices.
- Valuation metrics.
- Fundamental metrics.
- Macroeconomic indicators.
- Market/news/research signals.
- Data freshness.

Outputs per opportunity:
- Instrument/asset.
- Asset class.
- Thesis.
- Why it surfaced.
- Relevant current evidence.
- Risk level.
- Key risks.
- Suggested research horizon.
- Portfolio impact.
- Diversification impact.
- Scenario assumptions.
- Data timestamp.
- Source references.
- Confidence/data-quality indicator.
- "Research", "Compare", and "Simulate" actions.

Do not use language such as "guaranteed winner" or "certain return."

### 6.13 Portfolio Doctor
Analyze:
- Concentration risk.
- Asset-class allocation.
- Sector allocation.
- Geography.
- Currency.
- Liquidity.
- Volatility.
- Income dependence.
- Goal alignment.

Generate observations and alternative **scenarios**, not automatic trades.

### 6.14 Watchlist and Alerts
Allow users to:
- Add assets to watchlists.
- Create target-price alerts.
- Create portfolio-allocation alerts.
- Receive maturity reminders.
- Receive contribution reminders.
- Receive goal milestone notifications.
- Receive AI research alerts subject to user preferences.

---

## 7. Proposed Database Model

Minimum entities:

```text
users
user_profiles
risk_profiles
portfolios
portfolio_members
assets
asset_metadata
holdings
transactions
valuations
market_prices
fx_rates
income_events
liabilities
goals
goal_scenarios
forecast_scenarios
watchlists
watchlist_items
alerts
research_items
ai_conversations
ai_messages
ai_tool_calls
ai_recommendation_runs
ai_opportunities
audit_events
documents
notification_preferences
```

### Important fields

`portfolios`
- id UUID
- user_id UUID
- name
- base_currency
- portfolio_type
- created_at
- updated_at

`assets`
- id UUID
- symbol nullable
- name
- asset_class
- subtype
- currency
- country
- external_provider_id nullable
- metadata JSONB

`transactions`
- id UUID
- portfolio_id
- asset_id nullable
- transaction_type
- trade_date
- settlement_date nullable
- quantity nullable
- unit_price nullable
- gross_amount
- fees
- taxes
- currency
- fx_rate_to_portfolio_currency
- source
- created_at

`goals`
- id UUID
- user_id
- name
- target_amount
- target_currency
- target_date
- goal_type
- expected_return_assumption
- inflation_assumption

`ai_opportunities`
- id UUID
- recommendation_run_id
- asset_id nullable
- opportunity_type
- rationale JSONB
- risks JSONB
- evidence JSONB
- suitability JSONB
- model_score nullable
- score_explanation JSONB
- data_as_of
- created_at

Use `NUMERIC/DECIMAL`, not floating-point, for money and transaction quantities where precision matters.

---

## 8. API Design

Prefix REST endpoints with `/api/v1`.

Examples:

```text
POST   /api/v1/auth/register
GET    /api/v1/me
PATCH  /api/v1/me/preferences

GET    /api/v1/portfolios
POST   /api/v1/portfolios
GET    /api/v1/portfolios/{id}
GET    /api/v1/portfolios/{id}/summary
GET    /api/v1/portfolios/{id}/allocation
GET    /api/v1/portfolios/{id}/performance

POST   /api/v1/portfolios/{id}/transactions
GET    /api/v1/portfolios/{id}/transactions

GET    /api/v1/assets/search
GET    /api/v1/assets/{id}
GET    /api/v1/assets/{id}/market-data

POST   /api/v1/forecasts/compound
POST   /api/v1/forecasts/goal
POST   /api/v1/forecasts/scenarios

GET    /api/v1/goals
POST   /api/v1/goals
GET    /api/v1/goals/{id}/progress

GET    /api/v1/net-worth
GET    /api/v1/income/summary

POST   /api/v1/ai/chat
POST   /api/v1/ai/portfolio-doctor
POST   /api/v1/ai/opportunities
POST   /api/v1/ai/compare
POST   /api/v1/ai/simulate

GET    /api/v1/watchlists
POST   /api/v1/watchlists/{id}/items
```

Use OpenAPI generated from FastAPI as the contract source. Generate Dart API clients where practical.

---

## 9. AI Tool Contract

The AI orchestrator may call only explicit tools such as:

```text
get_portfolio_summary(portfolio_id)
get_portfolio_allocation(portfolio_id)
get_portfolio_performance(portfolio_id, period)
get_net_worth()
get_goal_progress(goal_id)
run_compound_forecast(input)
run_goal_forecast(input)
get_market_snapshot(asset_ids)
search_investment_universe(filters)
get_asset_research(asset_id)
compare_assets(asset_ids)
run_portfolio_risk_analysis(portfolio_id)
```

Rules:
- Every tool validates authorization.
- No raw SQL tool.
- No shell tool.
- No arbitrary URL fetching from model-generated URLs.
- Validate tool inputs with Pydantic.
- Return structured JSON.
- Log tool name, actor, timestamp, arguments hash, result status, model version, and request correlation ID.
- Redact secrets and sensitive tokens from logs.

---

## 10. AI Opportunity Pipeline

```text
1. Read user investment constraints
2. Read portfolio exposure
3. Load current investment universe
4. Apply hard eligibility filters
5. Load market/fundamental/macro evidence
6. Compute deterministic quantitative features
7. Calculate transparent candidate scores
8. Run diversification/suitability checks
9. Retrieve supporting research
10. LLM produces structured explanation
11. Validate output schema
12. Persist recommendation run + evidence timestamp
13. Present opportunities with risks and assumptions
14. Allow user to compare or simulate
```

The LLM should **not invent expected returns**. Forecast assumptions must either:
- be entered by the user,
- come from a clearly identified research methodology/data source, or
- be presented as illustrative scenario values.

---

## 11. Mobile Navigation

Bottom navigation:

```text
Home | Portfolio | AI Wealth | Goals | More
```

### Home
- Total portfolio value.
- Net worth.
- YTD performance.
- Portfolio chart.
- Allocation.
- Passive income.
- Goal progress.
- AI insight cards.

### Portfolio
- Portfolio selector.
- Holdings.
- Transactions.
- Allocation.
- Performance.
- Income.
- Add investment.

### AI Wealth
- Ask Wealth AI.
- Opportunities.
- Trending research.
- Portfolio Doctor.
- Compare investments.
- Scenario Simulator.
- Market Intelligence.
- Watchlist.

### Goals
- Goal cards.
- Progress.
- Required contribution.
- Scenario modelling.

### More
- Net worth.
- Calculator.
- Reports.
- Alerts.
- Documents.
- Profile.
- Security.
- Settings.

---

## 12. Security Requirements

Treat these as acceptance criteria:

- TLS 1.2+; prefer TLS 1.3.
- Encryption at rest.
- MFA support.
- OAuth/OIDC with PKCE.
- Short-lived access tokens.
- Secure refresh token handling.
- Tokens stored only in secure mobile storage.
- Never store passwords in the app.
- Server-side authorization on every portfolio/resource access.
- IDOR tests.
- Rate limiting.
- Brute-force protection.
- Input validation.
- Parameterized queries/ORM.
- CSP and web security controls for any web client.
- Secrets outside source control.
- Audit trail for financial changes.
- Audit trail for AI recommendation runs.
- Database backups and restore testing.
- Dependency scanning.
- SAST.
- Container scanning.
- SBOM generation.
- Logging without leaking financial data unnecessarily.
- Privacy/data retention policy.
- Account deletion/export workflow.
- OWASP MASVS review before production mobile release.
- OWASP API Security review before production API release.

---

## 13. Testing Strategy

### Backend
- Unit tests.
- API integration tests.
- Database integration tests.
- Financial calculation golden tests.
- Property-based tests for calculation edge cases.
- Authorization tests.
- AI tool authorization tests.
- External provider contract tests.

### Mobile
- Widget tests.
- State-management tests.
- Navigation tests.
- Integration tests.
- Android/iOS smoke tests.
- Offline/cache behavior tests.
- Secure storage tests.

### Financial engine
Test:
- Zero interest.
- Negative scenario rates where supported.
- Very long periods.
- Monthly contributions.
- Annual contribution increases.
- Currency conversions.
- Rounding.
- Fees.
- Inflation.
- Leap/date boundary behavior where dates matter.

### AI
- Structured-output validation.
- Hallucination regression suite.
- Prompt injection tests.
- Tool permission tests.
- Stale-data tests.
- Missing-data behavior.
- Citation/source-preservation tests.
- Adversarial requests for cross-user portfolio access.

---

## 14. MVP Delivery Plan

### Phase 0 - Engineering Foundation
Deliver:
- Monorepo.
- Flutter Android/iOS app shell.
- FastAPI application.
- PostgreSQL.
- Redis.
- Keycloak.
- Docker Compose.
- CI pipeline.
- OpenAPI.
- Logging/telemetry.
- Development standards.

### Phase 1 - Portfolio Core
Deliver:
- User profile.
- Portfolio CRUD.
- Asset model.
- Transactions.
- Holdings.
- Manual valuations.
- Multi-currency.
- Dashboard.

### Phase 2 - Analytics and Wealth Planning
Deliver:
- Performance engine.
- Allocation analytics.
- Passive income.
- Net worth.
- Compound calculator.
- Goal forecasting.
- Scenario comparison.

### Phase 3 - Market Data
Deliver:
- Market provider abstraction.
- Price updates.
- FX rates.
- Historical data.
- Automatic valuations.
- Watchlists.

### Phase 4 - AI Wealth Copilot
Deliver:
- AI orchestrator.
- Portfolio tools.
- Calculator tools.
- Secure chat.
- Portfolio Doctor.
- Conversation history.
- AI audit trail.

### Phase 5 - AI Investment Intelligence
Deliver:
- Investment-universe screening.
- Evidence ingestion.
- Opportunity pipeline.
- Suitability checks.
- Explainable scoring.
- Compare/simulate workflow.
- Research sources and timestamps.

### Phase 6 - Production Hardening
Deliver:
- Penetration/security testing.
- Performance/load testing.
- Backup/restore test.
- Disaster recovery.
- App Store release.
- Google Play release.
- Observability dashboards.
- Incident/runbook documentation.

---

## 15. Claude Code Working Instructions

Create a root `CLAUDE.md` containing the following rules:

```markdown
# CLAUDE.md

## Mission
Build WealthSphere according to `/docs/architecture.md` and this repository's accepted ADRs.

## Non-negotiable rules
- Do not bypass authentication or authorization.
- Do not give the LLM direct database access.
- Do not put API keys or secrets in source code.
- Do not use binary floating point for money.
- Do not modify unrelated modules during a scoped task.
- Do not delete tests to make a build pass.
- Do not weaken validation or security controls to fix an error.
- All database schema changes require Alembic migrations.
- All API changes require OpenAPI-compatible schemas.
- All financial formulas require unit tests.
- All AI tool calls require server-side authorization.
- AI-generated investment analysis must include assumptions, risks, data timestamp, and evidence/source references when available.
- Do not represent forecast scenarios as guaranteed outcomes.
- Prefer small, reviewable commits.

## Workflow for every task
1. Read the relevant architecture/module documentation.
2. Inspect existing code before proposing changes.
3. State a concise implementation plan.
4. Implement the smallest coherent change.
5. Add/update tests.
6. Run formatter, linter, type checks, and tests.
7. Report changed files and any remaining risks.
```

---

## 16. First Claude Code Prompt

Use this after creating the repository:

```text
You are the lead engineer for WealthSphere, an Android/iOS AI-powered portfolio and wealth-management application.

Read CLAUDE.md and all files under /docs before changing code.

TASK:
Create Phase 0 - Engineering Foundation.

Requirements:
1. Create a Flutter application under mobile/wealthsphere_app that builds for Android and iOS.
2. Use Riverpod, GoRouter, Dio, Freezed/json_serializable, flutter_secure_storage, and local_auth.
3. Create a FastAPI backend with Pydantic v2, SQLAlchemy 2, Alembic, PostgreSQL, and Redis.
4. Configure Keycloak for local OAuth/OIDC development.
5. Add Docker Compose for PostgreSQL, Redis, Keycloak, RabbitMQ, and backend.
6. Add /health/live and /health/ready endpoints.
7. Add structured logging and correlation IDs.
8. Add environment configuration using .env.example without committing secrets.
9. Add pytest and Flutter test foundations.
10. Add GitHub Actions for backend lint/type/test and Flutter analyze/test.
11. Create docs/architecture.md, docs/security.md, docs/api-conventions.md, and docs/ai-governance.md.
12. Do not implement investment business features yet.

Before coding:
- inspect the repository;
- propose the exact file/folder plan;
- identify assumptions;
- avoid unnecessary dependencies.

After coding:
- run all available tests;
- show commands used;
- list changed files;
- explain any failures without hiding them.
```

---

## 17. Second Claude Code Prompt - Portfolio Core

```text
Read CLAUDE.md and architecture docs.

Implement Phase 1 - Portfolio Core without changing unrelated infrastructure.

Create:
- user preferences including base currency;
- portfolio CRUD;
- extensible asset model;
- transactions;
- holdings calculation;
- manual valuations;
- multi-currency transaction storage;
- portfolio summary endpoint;
- Flutter portfolio list/detail/add-investment screens.

Requirements:
- UUID primary keys.
- PostgreSQL NUMERIC for money.
- Alembic migrations.
- Server-side resource ownership checks.
- Pydantic request/response models.
- Repository/service/API separation.
- Unit and integration tests.
- Do not calculate portfolio truth in Flutter; backend is authoritative.
- Do not add AI functionality in this phase.
```

---

## 18. Third Claude Code Prompt - Forecast Engine

```text
Implement the WealthSphere deterministic forecasting engine.

Support:
- lump-sum compounding;
- recurring monthly contributions;
- annual contribution escalation;
- user-selected expected return;
- investment period;
- inflation;
- fees;
- conservative/base/aggressive scenarios;
- required monthly contribution for a target.

Return:
- final projected value;
- total contributed capital;
- projected investment growth;
- inflation-adjusted value;
- yearly series for charts.

Add comprehensive tests and document formulas/rounding conventions.
The engine must not depend on an LLM.
```

---

## 19. Fourth Claude Code Prompt - AI Wealth Copilot

```text
Implement the AI Wealth Copilot architecture.

Do not give the model SQL access.

Create an AI orchestrator with allow-listed tools:
- get_portfolio_summary
- get_portfolio_allocation
- get_portfolio_performance
- get_net_worth
- get_goal_progress
- run_compound_forecast

Every tool must:
- receive authenticated user context;
- verify resource ownership;
- use Pydantic schemas;
- return structured JSON;
- emit an audit event.

Create POST /api/v1/ai/chat.

Use an LLM provider abstraction with OpenAI as the first provider.
Keep API credentials server-side.
Persist model/provider/version, tool calls, timestamps, and correlation IDs without logging secrets.
Add prompt-injection and cross-user authorization tests.
```

---

## 20. Fifth Claude Code Prompt - AI Investment Intelligence

```text
Implement AI Investment Intelligence as a research and scenario module.

Do not let the LLM invent market facts or expected returns.

Build:
1. market/research provider interfaces;
2. investment-universe screening;
3. deterministic quantitative feature calculation;
4. eligibility filters;
5. explainable candidate scoring;
6. portfolio concentration/diversification analysis;
7. opportunity structured schema;
8. LLM explanation generation from retrieved evidence;
9. evidence/source timestamps;
10. Compare and Simulate actions.

Each opportunity response must include:
- asset/instrument;
- asset class;
- thesis;
- why it surfaced;
- current evidence;
- key risks;
- portfolio impact;
- assumptions;
- data-as-of timestamp;
- sources/evidence references;
- score explanation if a score is used.

No automatic trade execution.
No guaranteed-return language.
Add tests for stale data, missing evidence, prompt injection, unauthorized portfolio access, and invalid structured LLM output.
```

---

## 21. Definition of Done

A feature is complete only when:
- acceptance criteria pass;
- tests pass;
- security boundaries are preserved;
- API schemas are documented;
- migrations are included;
- mobile loading/error/empty states exist;
- logs/metrics are present where appropriate;
- no secrets are committed;
- financial calculations are deterministic and tested;
- AI output is validated;
- documentation is updated.

---

## 22. Recommended First Development Sequence

Start in this order:

```text
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
11. Net worth + income
12. Market/FX integration
13. AI tool layer
14. AI Wealth Copilot
15. Investment Intelligence
16. Production hardening
17. Android/iOS store release
```

Do not start with the AI recommendation UI. Establish trusted portfolio data, financial calculations, authorization, and market-data provenance first.


---

# UI/UX Design Specification — Approved Product Direction (v1.1)

## Design intent
WealthSphere must deliver a premium, approachable fintech experience on **both Android and iOS**, combining digital-banking simplicity with professional portfolio analysis. The concept board is a **visual direction**, not a pixel-perfect specification or proof of working functionality. Figures, opportunities, scores, and charts in the mockups are illustrative sample data only.

### Brand tokens
| Token | Value | Use |
|---|---|---|
| `color.navy.900` | `#102A43` | Headers, dark backgrounds, primary text |
| `color.teal.600` | `#0D9488` | Positive actions, portfolio growth, success states |
| `color.gold.400` | `#F2B84B` | Premium accent, highlights, goal milestones |
| `color.blue.600` | `#2563EB` | Primary CTA and selected navigation |
| `color.surface.light` | `#FFFFFF` | Light cards and screens |
| `color.surface.subtle` | `#F5F7FA` | Light app background |
| `color.text.muted` | `#64748B` | Supporting text |
| `color.danger` | `#DC2626` | Loss and risk signals, always with text/icons |

Use semantic tokens rather than hard-coded widget colors. Provide dark-mode equivalents and WCAG-aware contrast. Typography: platform-appropriate sans serif, scalable with system text settings; 8-point spacing grid; rounded cards (12–20dp), 44pt iOS / 48dp Android minimum touch targets where feasible.

## Primary navigation
**Home | Portfolio | AI Wealth | Goals | More**. Keep tab selection stable; nested flows use standard back navigation. AI chat can also open contextually from asset, portfolio, forecast and goal screens.

## Screen inventory and required UX behavior
| # | Screen | Required UI elements and behavior |
|---|---|---|
| 1 | Welcome & Onboarding | Brand intro, value proposition, onboarding carousel, Get Started / Sign In, skip accessible where appropriate |
| 2 | Sign In / Sign Up | Email, password or configured identity flow, MFA, secure reset, biometrics for returning users, validation and error feedback |
| 3 | Home Dashboard | Total wealth, return and period selector, chart, portfolio/net worth/income/goal cards, AI insight summary, personalized reorderable widgets |
| 4 | Portfolio Overview | Portfolio selector, value, P/L, line chart, allocation donut and legend, performance metrics, drill-down to holdings |
| 5 | Investments / Holdings | Search, asset-class chips, sortable holdings, native currency and converted value, positive/negative change with accessible text |
| 6 | AI Wealth Copilot | Conversation thread, suggested questions, contextual portfolio scope, source/data timestamps, streaming/loading, refusal and retry states |
| 7 | Investment Details | Symbol/name, latest value, chart and period selector, fundamentals, income, holdings, transaction history, research, watchlist action |
| 8 | Transactions | Filter chips, grouped dated activity, amounts/fees/currencies, add transaction flow, confirmation, edit/correction audit trail |
| 9 | Compounding Calculator | Initial capital, recurring contribution, return assumption, horizon, contribution growth, inflation/fees advanced inputs, Calculate |
| 10 | Wealth Forecast | Conservative/base/growth selectable scenario cards, comparison chart, final value, contributions vs growth, nominal/real toggle, assumptions disclosure |
| 11 | Financial Goals | Goal cards, target and date, progress rings with numeric labels, on-track status, add/edit goal, required contribution |
| 12 | Portfolio Doctor | Health overview, concentration/currency/liquidity/volatility findings, severity + explanation, alternative scenario actions |
| 13 | AI Investment Opportunities | Research category chips, candidate cards, evidence, risk, data-as-of, explainable ranking, Compare/Research/Simulate actions |

## Shared Flutter component library
Build reusable and independently testable widgets: `WealthSummaryCard`, `MetricCard`, `PerformanceLineChart`, `AllocationDonutChart`, `PeriodSelector`, `PortfolioSwitcher`, `InvestmentRow`, `TransactionTile`, `ScenarioCard`, `ForecastComparisonChart`, `GoalProgressCard`, `PortfolioHealthCard`, `OpportunityCard`, `EvidenceSourceChip`, `RiskLabel`, `CurrencyAmount`, `EmptyState`, `ErrorState`, `SkeletonLoader`, `WealthBottomNav`, `AIChatComposer`, `DisclosurePanel`.

## Interaction rules
- Charts: period selection, accessible data summary, tooltips, loading/empty states, currency-aware formatting and date labels.
- Forecast: tap scenario to update chart and values; label assumptions prominently; show contributed capital separately from modeled returns.
- AI opportunity: `Research` opens evidence; `Compare` opens side-by-side analysis; `Simulate` pre-fills a scenario with clearly marked assumptions. No automatic trades.
- Dashboard: configurable card order and visibility, persistent per-user preferences.
- Contextual AI: portfolio/asset/goal context must be explicitly shown and authorized; users can change or remove context.
- Use skeleton loading, clear offline/stale-data banners, retry states and understandable validation errors.
- Support push-notification deep links, safe-area insets, iOS swipe/back conventions and Android system back navigation.
- Support light/dark themes, reduced motion, screen readers, dynamic text scaling, RTL-ready layout, localization and non-color-only indicators.
- Do not embed investment advice as fixed UI text; opportunity content must come from authorized, timestamped, evidence-backed services.

## Mobile responsiveness and testing
Support small and large Android phones and current iPhone sizes; tablets may use adaptive layouts in a later phase. Use Flutter breakpoints and avoid fixed pixel positioning. Verify portrait layouts, keyboards, notches, safe areas, long translated strings, large text, dark mode and accessibility. Add widget/golden tests for design-system components and integration tests for key journeys.

## UX delivery gates
1. Establish design tokens, themes, typography and navigation shell.
2. Implement high-fidelity Home, Portfolio, Calculator, Forecast and AI Wealth screens using mock data with an explicit `DEMO` indicator.
3. Add remaining eight screens and shared component states.
4. Connect backend APIs and replace mock data; ensure loading/error/offline states.
5. Complete accessibility and Android/iOS QA; compare implementation against the concept board.

## Visual reference
Reference concept board: `docs/design/wealthsphere-ui-concept.png` (copy the supplied design reference into the repository). The image is inspirational, not a strict source for copy, calculations, portfolio data, asset prices, or recommendations.

## Claude Code Prompt — UI/UX Implementation

```text
Read SOLUTION_INTENT.md, CLAUDE.md, and the UI/UX Design Specification in this guide. Implement a cohesive Flutter design system and the 13 specified Android/iOS screens. Begin with design tokens, theme switching, GoRouter navigation, reusable components, then build Home, Portfolio Overview, Compounding Calculator, Wealth Forecast, and AI Wealth Copilot first. Use typed demo fixtures clearly labeled DEMO; do not invent live market prices or investment recommendations. Include responsive safe-area layouts, dark/light mode, dynamic type, screen-reader labels, accessible chart summaries, loading/empty/error/offline states, and widget tests. Preserve existing backend contracts. Before coding, inspect the repository and propose a file-by-file plan. After coding, run flutter analyze and flutter test, and report results.
```
