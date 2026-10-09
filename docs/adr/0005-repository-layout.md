# ADR-0005: Repository layout

Status: Accepted (user approval, 2026-10-09)

## Decision
A single monorepo:

```text
mobile/wealthsphere_app/   Flutter app (app/, core/, shared/design_system/, features/)
backend/                   FastAPI modular monolith, Alembic migrations, tests
infra/docker/              container assets for local development
infrastructure/terraform/  cloud infrastructure (P13)
docs/                      product docs, ADRs, design, architecture, security
scripts/                   repository tooling (track.py, OpenAPI export)
.github/workflows/         CI/CD
```

Root files: CLAUDE.md, EXECUTION_PLAN.md, TASK_CHECKLIST.md, QUALITY_GATES.md, PROGRESS_DASHBOARD.md, EXECUTION_LOG.md, docker-compose.yml, Makefile and `.env.example`.

## Consequences
One place for the whole product and its tracking, with CI path filters per area. `infra/` (local development) and `infrastructure/` (cloud) are deliberately distinct.
