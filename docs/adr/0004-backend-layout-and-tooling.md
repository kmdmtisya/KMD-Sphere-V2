# ADR-0004: Backend layout and tooling

Status: Proposed (tooling choices = DEC-07)

## Context
CLAUDE.md requires a modular monolith; the guide sketches many `services/*` folders.

## Decision
One FastAPI deployable in `backend/`, with domain modules under `backend/app/modules/`: identity, portfolio, assets, transactions, analytics, forecasting, goals, networth, market_data, notifications, ai. Each module has `api`, `service`, `repository` and `schemas` layers. Modules call each other only through service interfaces.

- **Stack:** Python 3.13+, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, PostgreSQL, Redis, Celery with RabbitMQ.
- **Tooling:** uv (environments and lockfile), ruff (lint and format), mypy (strict on `app/`), pytest with coverage reporting.
- **Data:** all money columns are `NUMERIC`; all keys are UUIDs.

## Consequences
Clear extraction seams without microservice overhead, and a fast, reproducible toolchain. Replacing a tool requires amending this ADR.
