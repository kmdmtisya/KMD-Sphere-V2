# WealthSphere Architecture

Derived from `SOLUTION_INTENT.md` (sections 22, 26, 27) and the implementation guide (sections 4, 5, 7, 12). Decisions: see `docs/adr/`.

## 1. System context

```text
Android / iOS (Flutter)
        |  HTTPS, OIDC (Authorization Code + PKCE), JSON /api/v1
        v
   FastAPI modular monolith  ---- Redis (cache, rate limits)
        |        |            ---- RabbitMQ + Celery workers (market data, alerts, AI jobs)
        |        +--------------- Keycloak (identity)
        v
   PostgreSQL (+ pgvector)
        ^
        |  allow-listed tools only
   AI orchestrator ---- LLM provider (OpenAI first, behind an abstraction)
        |
   Market / FX / research providers (behind provider interfaces)
```

The backend is the single source of financial truth. The mobile app displays and formats; it does not calculate. The LLM explains and orchestrates; it never calculates or invents market facts.

## 2. Modules and boundaries

Each module lives in `backend/app/modules/<name>/` with `api`, `service`, `repository`, `schemas`. Modules depend only on other modules' **service interfaces**, never on their repositories or tables.

| Module | Responsibility | Depends on |
|---|---|---|
| identity | users, profiles, risk profile, preferences, token validation | (platform) |
| portfolio | portfolios, membership, summaries | identity, assets, transactions, analytics |
| assets | asset catalogue, class metadata, search | (platform) |
| transactions | append-only ledger, holdings derivation, valuations | portfolio, assets, market_data (FX) |
| analytics | performance, allocation, concentration, risk metrics | transactions, market_data |
| forecasting | compound and goal forecasts (pure, deterministic) | (none) |
| goals | goals and progress | forecasting, portfolio |
| networth | assets, liabilities, income | portfolio, transactions |
| market_data | provider abstraction, prices, FX, freshness | (platform) |
| notifications | alerts, push, preferences | identity, market_data |
| ai | tool registry, orchestrator, opportunity pipeline | all through tool services only |

Cross-cutting platform code (`backend/app/core`): configuration, logging with correlation IDs, error model (RFC 7807), database session, authorization helpers, audit writer, rate limiting.

## 3. Mobile architecture

`mobile/wealthsphere_app/lib`: `app/` (app widget, router), `core/` (network, auth, preferences), `shared/design_system/` (tokens, theme, formatting, components, charts), `features/<feature>/{domain,data,presentation}`.

- State: Riverpod. Navigation: GoRouter with a five-tab stateful shell.
- Repositories are interfaces; `Demo*` implementations (labelled DEMO) are replaced by `Live*` implementations in P09 without changing presentation code.
- Money: `Decimal` + currency code, amounts as strings (ADR-0003).

## 4. Data architecture

- PostgreSQL, UUID primary keys, `NUMERIC` for money and quantities, timestamps on every price, FX rate and valuation (provenance).
- Transactions are append-only; corrections are reversing or adjusting entries.
- Holdings, summaries and analytics are derived, never hand-edited.
- Every schema change has an Alembic migration with a tested downgrade; CI enforces a single migration head.

## 5. Request flow

1. The client obtains tokens from Keycloak (PKCE) and stores them in secure storage.
2. Each API call carries a bearer token; the backend validates signature, issuer, audience and expiry.
3. A dependency resolves the current user; every resource access verifies ownership server-side.
4. Services call repositories; financial values are computed by deterministic services.
5. Material changes emit audit events; responses use typed Pydantic schemas published in OpenAPI.

## 6. AI flow

`User -> AI Orchestrator -> authorization -> allow-listed tool -> deterministic result -> LLM -> validated response`. See `docs/ai-governance.md`.

## 7. Environments

Local: `docker-compose.yml` (Postgres, Redis, RabbitMQ, Keycloak). Cloud: Terraform-managed, containerised, with isolated staging and production (P14).

## 8. Quality attributes

Security, auditability and correctness are primary; see `docs/security.md` and `QUALITY_GATES.md`. Observability: structured logs, OpenTelemetry traces and Prometheus metrics (P01-T12).
