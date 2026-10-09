# WealthSphere backend

FastAPI modular monolith (ADR-0004). Python 3.13+, managed with uv.

```bash
cd backend
uv sync
make -C .. up                       # PostgreSQL + Redis + RabbitMQ + Keycloak (repo root)
uv run uvicorn app.main:app --reload --port 8000

# quality gate (CK-B)
uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest --cov
```

Configuration comes from the environment (and the repository-root `.env` for local runs); there are no default secrets.
Endpoints so far: `GET /health/live`, `GET /health/ready`. Errors use RFC 7807 problem+json and every response carries `X-Correlation-ID`.
