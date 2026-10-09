# Continuous integration

Workflows live in `.github/workflows/`. Each runs only when files in its area change (path filters) and on manual dispatch.

| Workflow | Job (check name) | What it enforces |
|---|---|---|
| `mobile.yml` | `format, analyze, test (incl. goldens)` | `dart format`, `flutter analyze`, `flutter test --coverage` on ubuntu-24.04 (goldens are authoritative here) |
| `mobile.yml` | `android debug build` | `flutter build apk --debug` |
| `mobile.yml` | `ios compile (no codesign)` | `flutter build ios --no-codesign` on macOS |
| `backend.yml` | `lint, types, tests, migrations` | `ruff format --check`, `ruff check`, `mypy` (strict), OpenAPI contract up to date and Spectral-clean, Alembic upgrade/check/downgrade/upgrade and single head, `pytest` with coverage (`--cov-fail-under=85`) against PostgreSQL (pgvector) and Redis service containers |

## Required checks (to be enforced in P01-T15)
When branch protection is switched on, these check names become mandatory for merging to `main`: the five jobs above, plus the security scans (P01-T11) and the tracker validation (`python scripts/track.py validate`).

## Notes
- Locked installs: the backend uses `uv sync --locked`, so a change to `pyproject.toml` without an updated `uv.lock` fails CI.
- CI database credentials are throwaway values for ephemeral service containers; real secrets never go in workflow files (use GitHub Environments and OIDC, P12-T06).
- Concurrency groups cancel superseded runs on the same ref.
- Run the same checks locally: see `backend/README.md` and `docs/dev-setup.md`.
