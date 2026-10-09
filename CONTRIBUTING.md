# Contributing to WealthSphere

Read `CLAUDE.md` first (non-negotiable rules, Definition of Done), then `EXECUTION_PLAN.md` section 4 (how work is executed and tracked).

## Setup
See `docs/dev-setup.md`. Then install the hooks once:

```bash
uv tool install pre-commit
pre-commit install            # installs the pre-commit and commit-msg hooks
pre-commit run --all-files    # run every hook on the whole repository
```
The `gitleaks` hook needs the gitleaks binary (`winget install Gitleaks.Gitleaks`, or your package manager).

## Working on a task
1. Pick an eligible task: `python scripts/track.py next`. Never start a task whose prerequisites or phase approval are missing.
2. `python scripts/track.py start <ID>` (records the real start time).
3. Make the smallest coherent change inside the task's scope. Do not modify unrelated modules.
4. Run the checks for the area you touched (below), then verify quality-gate criteria with evidence.
5. `python scripts/track.py complete <ID> --evidence "..."` (or `verify` first when the task needs user approval).
6. Commit and push. Never hand-edit statuses, checkboxes or timestamps in the tracking files.

## Checks
| Area | Command (from the directory shown) |
|---|---|
| Mobile (`mobile/wealthsphere_app`) | `dart format --output=none --set-exit-if-changed . && flutter analyze && flutter test` |
| Backend (`backend`) | `uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest --cov` |
| Migrations (`backend`) | `uv run alembic upgrade head && uv run alembic check && uv run alembic downgrade base && uv run alembic upgrade head` |
| API contract (`backend`) | `uv run python ../scripts/export_openapi.py --check` and Spectral (`docs/ci.md`) |
| Tracking (repo root) | `python scripts/track.py validate` |

CI runs the same checks (`docs/ci.md`). Tests are never deleted or weakened to make a build pass.

## Branches and pull requests
- `main` is protected (ruleset, no bypass): changes arrive only through pull requests whose required checks pass (`backend gate`, `mobile gate`, `security gate`, `tracker validate`). Direct pushes, force-pushes and branch deletion are blocked.
- Work on a short-lived branch named `<type>/<task-id>-<slug>`, for example `feat/p05-t04-transaction-ledger`. Rebase on `main` before opening the pull request.
- Open the pull request early with `gh pr create`, wait for the checks, then merge (`gh pr merge --merge --delete-branch`). Tracker-only changes follow the same path; they are quick because the heavy jobs skip when their area is untouched.
- CODEOWNERS requests the maintainer automatically. Required approvals are 0 while there is a single maintainer (see ADR-0008); user approval is recorded by the tracker for tasks and gates that require it.
- Never force-push shared branches or rewrite pushed history without approval.

## Commit messages
Conventional commits, enforced by the `commit-msg` hook:

```
<type>: <task id> <short imperative summary>

Optional body explaining why.
```
Types: `feat`, `fix`, `docs`, `chore`, `ci`, `test`, `refactor`, `perf`, `build`, `revert`, and `track` (tracker-only changes such as task state, evidence and logs). Examples: `feat: P05-T04 add transaction ledger API`, `track: complete P01-T11 with evidence`.

## Pull requests
Use the template (Definition of Done checklist, quality gates, evidence). Describe failures and remaining risks honestly. A pull request touching money, authorization, AI tools or migrations needs a second review.

## Rules that never bend
No secrets in source control; no binary floating point for money; backend is authoritative for financial calculations; every protected resource checks ownership server-side; AI gets only allow-listed tools; no guaranteed-return language; no automatic trade execution. See `CLAUDE.md`, `docs/security.md` and `docs/ai-governance.md`.

## Security issues
Do not open public issues for vulnerabilities; follow `SECURITY.md`.
