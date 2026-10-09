# WealthSphere

AI-powered portfolio and wealth intelligence platform for Android and iOS (Flutter) with a FastAPI backend.
*Track. Measure. Forecast. Grow.*

## Where things are
| Path | Purpose |
|---|---|
| `CLAUDE.md` | Rules for Claude Code in this repository |
| `docs/` | Product intent, project brief, implementation guide, design concept, ADRs, developer setup |
| `EXECUTION_PLAN.md` | End-to-end roadmap: phases, tasks, waves, acceptance criteria |
| `TASK_CHECKLIST.md` | Live task state with timestamps and evidence (edited only by the tracker) |
| `QUALITY_GATES.md` | Quality-gate register QG-01..QG-12 |
| `PROGRESS_DASHBOARD.md` / `EXECUTION_LOG.md` | Progress summary / chronological log |
| `scripts/track.py` | Execution tracker: `python scripts/track.py status` |

Planned layout: `mobile/wealthsphere_app` (Flutter), `backend/` (FastAPI modular monolith), `infrastructure/` (Docker, Terraform), `.github/workflows`.

## Working with the plan
```bash
python scripts/track.py status     # progress dashboard
python scripts/track.py next       # next eligible tasks
python scripts/track.py validate   # consistency check
```
Environment setup: `docs/dev-setup.md`.
