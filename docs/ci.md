# Continuous integration

Workflows live in `.github/workflows/`. Each workflow runs on every pull request and push to `main`, plus manual dispatch; change detection inside the workflow decides which heavy jobs are needed.

| Workflow | Job (check name) | What it enforces |
|---|---|---|
| `mobile.yml` | `detect changes` | Decides whether `mobile/**` or the workflow changed (runs everything when unsure) |
| `mobile.yml` | `format, analyze, test (incl. goldens)` | `dart format`, `flutter analyze`, `flutter test --coverage` on ubuntu-24.04 (goldens are authoritative here) |
| `mobile.yml` | `android debug build` / `ios compile (no codesign)` | `flutter build apk --debug`; `flutter build ios --no-codesign` on macOS |
| `mobile.yml` | **`mobile gate`** | Fails if any job above failed or was wrongly skipped |
| `backend.yml` | `lint, types, tests, migrations` | `ruff format --check`, `ruff check`, `mypy` (strict), OpenAPI contract up to date and Spectral-clean, Alembic upgrade/check/downgrade/upgrade and single head, `pytest` with coverage (`--cov-fail-under=85`) and the per-module policy against PostgreSQL (pgvector) and Redis service containers |
| `backend.yml` | **`backend gate`** | Same gate pattern as mobile |
| `security.yml` | secret scan, dependency audit, CodeQL, Trivy, SBOM | See `SECURITY.md` |
| `security.yml` | **`security gate`** | Fails unless all five security jobs succeeded |
| `tracker.yml` | **`tracker validate`** | `python scripts/track.py validate` and the tracker test suite (`tests/tracker`, 88 tests: lifecycle, validation, quality gates, robustness) |

## Required checks (ruleset "main protection")
`backend gate`, `mobile gate`, `security gate` and `tracker validate` must pass before a pull request can merge to `main`; direct pushes, force-pushes and deletion of `main` are blocked and there are no bypass actors (ADR-0008). Every workflow runs on every pull request and decides internally whether its heavy jobs are needed, so a required check never stays pending.

## Notes
- Locked installs: the backend uses `uv sync --locked`, so a change to `pyproject.toml` without an updated `uv.lock` fails CI.
- CI database credentials are throwaway values for ephemeral service containers; real secrets never go in workflow files (use GitHub Environments and OIDC, P12-T06).
- Concurrency groups cancel superseded runs on the same ref.
- Per-module coverage is written to the job summary of the backend run (`scripts/coverage_by_module.py`); policy in `backend/coverage-policy.toml`.
- Third-party actions are pinned to commit SHAs and updated by Dependabot.
- Run the same checks locally: see `backend/README.md` and `docs/dev-setup.md`.
