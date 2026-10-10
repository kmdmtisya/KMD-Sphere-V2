# WealthSphere — Master Execution Plan

_Version 1.0 · created 2026-10-09T12:49:16+04:00 · status: **DRAFT — awaiting user approval (P00-GATE)**_

This is the authoritative end-to-end roadmap for building WealthSphere from the current repository state to production release. It covers the Flutter design system and all 13 screens for Android/iOS, backend services, database, portfolio management, analytics, the compounding calculator, AI Wealth Copilot, AI Investment Intelligence, security, CI/CD, cloud infrastructure, testing and release.

**Size:** 17 phases · 185 tasks (incl. 17 phase gates) · 746 subtasks · 25 quality gates with 146 criteria (QUALITY_GATES.md). Phase P13 and gates QG-13..QG-20 are the Forex Trading Intelligence workstream (FX, approved 2026-10-09). Phase P11 and gates QG-21..QG-25 are the Multi-Currency Reporting & FX Management workstream (FXCUR), proposed 2026-10-10 and **awaiting user approval**; see ADR-0010 and docs/design/multi-currency-design.md.

## 1. Document map

| File | Purpose | Edited by |
|---|---|---|
| `EXECUTION_PLAN.md` (this file) | Roadmap: phases, waves, tasks, dependencies, acceptance criteria, verification, rules | Humans / Claude via a plan-change task |
| `TASK_CHECKLIST.md` | Checkbox per task and subtask with status, timestamps, duration, evidence | **`scripts/track.py` only** |
| `QUALITY_GATES.md` | **Authoritative quality-gate register** QG-01…QG-20 (QG-13…QG-20 are the Forex gates QG-FX-01…08): criteria, owner, timestamps, evidence, blocking issues, approvals, waivers | **`scripts/track.py qg …` only** |
| `PROGRESS_DASHBOARD.md` | Counts, current phase, next executable tasks, blockers | `scripts/track.py dashboard` (auto block) + hand-kept sections |
| `EXECUTION_LOG.md` | Append-only chronological record | `scripts/track.py` (and manual notes for decisions/issues) |
| `docs/UI_EXECUTION_PLAN.md` | Supplementary UI step detail (see `Ref` on tasks) | Reference only |
| `docs/SOLUTION_INTENT.md`, `CLAUDE.md`, brief, guide, PDF | Product direction and rules; **SOLUTION_INTENT wins** on conflict | — |

## 2. Baseline reconciliation (verified evidence)

Inspected 2026-10-09T12:27:16+04:00 onward. Nothing is claimed as implemented beyond what this table shows.

| Area | Evidence found | Status |
|---|---|---|
| Source documents | `docs/`: CLAUDE.md, SOLUTION_INTENT.md, WEALTHSPHERE_PROJECT_BRIEF.md, WEALTHSPHERE_CLAUDE_CODE_IMPLEMENTATION_GUIDE.md, WealthSphere_Project_Brief_UIUX_Updated.pdf (9 pages; concept board image on page 8) | Present |
| Git repository | `git status` → not a git repository | Not started |
| Mobile app | No `mobile/` directory, no pubspec | Not started |
| Backend / database | No `backend/`, no migrations | Not started |
| Tests / CI / containers / IaC | No workflows, Dockerfiles, compose or Terraform | Not started |
| Concept board file | `docs/design/` absent; image exists only inside the PDF | Not started |
| Tracking system | Created by P00-T02 (this plan) | Awaiting verification |
| Toolchain | Flutter 3.47.5 / Dart 3.13.4 (Android toolchain `[!]`); Python 3.14.5; uv; Docker CLI 29.5.3 (daemon unresponsive at check time); Git 2.56; Node 24; gh; make. Terraform missing. | Env tasks in P01-T01 |

Conflicts and resolutions found in the documents:

| # | Finding | Resolution |
|---|---|---|
| D1 | CLAUDE.md development order puts backend foundations before the dashboard; the UI spec's delivery gates build the first screens on demo data. | Both are satisfied: UI lane (P02/P03/P07) runs on DEMO data while the backend lane (P04–P06/P08) builds the truth; P09 joins them. Recorded as ADR-0001 in P01-T03. |
| D2 | Concept board nav is Home/Portfolio/Invest/AI/More; written spec is Home/Portfolio/AI Wealth/Goals/More. | Follow the written spec (ADR-0002). |
| D3 | Calculator/Forecast need numbers, but Flutter must not be the source of financial truth. | Canned DEMO fixtures in P03; real engine in P06; wired in P09-T03. |
| D4 | 'No binary floating point for money' applies to the client as well. | `Decimal` + currency code, amounts as strings in JSON; `double` only inside chart widgets (ADR-0003). |
| D5 | Several brand tokens fail WCAG AA as text (teal 3.74:1, gold 1.79:1 on white; muted 4.43:1 on #F5F7FA; blue/red/teal/muted on navy 2.8–3.9:1). | Brand colours remain fills/accents; P02-T01 derives text-safe shades and enforces contrast with a test. |
| D6 | Concept board shows a Buy button on Investment Details. | Not built: no trade execution in the initial release (P07-T04). |
| D7 | iOS cannot be built on this Windows machine. | macOS CI job (P01-T10) compiles iOS; device QA needs a Mac or cloud device (P03-T07, P15-T06). |
| D8 | CLAUDE.md lives in docs/; Claude Code loads it from the repo root. | Moved to root in P01-T02. |
| D9 | Guide §16 lists Dio, secure storage and local_auth for the shell. | Deferred to P04-T06/T07 when first used (avoid unnecessary dependencies). |
| D10 | The project brief says 'Phase 0–6'; CLAUDE.md lists 17 steps; SOLUTION_INTENT lists Phase 0–10. | This roadmap uses P00–P16 and maps each source phase in the traceability appendix. |
| D11 | Guide §5 shows many `services/*` folders; CLAUDE.md says start as a modular monolith. | Single `backend/` modular monolith with domain modules (ADR-0004). |

## 3. Identifiers, status model and timestamps

- **Phase** `Pnn` · **Task** `Pnn-Tnn` · **Phase gate** `Pnn-GATE` · **Subtask** `Pnn-Tnn.k` · **Wave** `Pnn.Wk` (phase-local) · **Quality gate** `QG-nn` · **Criterion** `QG-nn.k` · **Check suite** `CK-*` (command suites, §7.1) · **Decision** `DEC-nn` · **Waiver** `W-nnn`.
- Statuses: `NOT_STARTED` ⬜ → `IN_PROGRESS` 🔄 → `AWAITING_VERIFICATION` 🔎 → `COMPLETED` ✅; `BLOCKED` ⛔ may interrupt any open state. Only `COMPLETED` renders `[x]`.
- A task is **COMPLETED** only when: all subtasks are ticked, its CK check suites pass, each acceptance criterion has evidence recorded, every criterion in its `Gates-done` is verified (or validly waived), and (if *Approval: yes*) the user has approved.
- Timestamps (`Started`, `Completed`) are produced by `scripts/track.py` from the system clock in ISO 8601 with offset. They are never typed by hand. Duration = Completed − Started (wall clock). Work done before the tracker existed is labelled `not recorded`.
- Progress history is the append-only `EXECUTION_LOG.md`; every tracker action adds an entry.

## 4. Execution control protocol

### 4.1 Commands you can give Claude Code

| You say | Claude does |
|---|---|
| `Execute the next eligible task` | Runs `track.py next`, picks the first eligible task in the lowest approved phase/wave, executes it per §4.2, stops. |
| `Execute task P05-T04` | Same for one named task. |
| `Execute wave P05.W2` | Executes all tasks in that wave (parallel only if §5 permits), then stops. |
| `Execute phase P05` | Executes the phase wave by wave, stopping at the gate. Never crosses into the next phase. |
| `Approve phase P05` | Runs `track.py approve-phase P05 --by <you>` after you confirm. |
| `Show status` | Runs `track.py status` and summarises. |
| `Unblock P05-T04: <resolution>` | Runs `track.py unblock`. |

### 4.2 Per-task procedure (mandatory)

1. **Preflight** — `python scripts/track.py validate`; confirm the phase is `APPROVED`, every dependency (incl. prerequisite phase gates) is `COMPLETED`, the task's `Gates-start` are satisfied, no failed quality gate lists it under Blocks, and the task is `NOT_STARTED`. Read the task's section here, the `Ref`, and the documents it cites (CLAUDE.md reading order). If a prerequisite is unmet, **stop and report** — do not work around it.
2. **Plan** — state the files to be created/changed and assumptions (CLAUDE.md workflow step 3–4); stop for the user if a Decision (DEC-nn) it needs is *Open*.
3. **Start** — `python scripts/track.py start <ID>` (records the real start time).
4. **Execute** — smallest coherent change inside the task's paths only; tick subtasks with `track.py check <ID>.k` as each is genuinely done.
5. **Verify** — run every CK suite and command listed in *Verification* plus format/lint/type/tests; capture command results. Then verify the quality-gate criteria the task is bound to (`Gates-done`) with `python scripts/track.py qg check <QG-nn.k> --evidence '…'`. Failures are reported, never hidden, and recorded with `qg fail … --blocks …` when a gate criterion fails; tests are never weakened to pass.
6. **Record** — if *Approval: yes*: `track.py verify <ID> --evidence "…"` and wait for the user, then `track.py complete <ID> --evidence "…" --approved-by <name>`. Otherwise `track.py complete <ID> --evidence "…"`. Evidence = commands run + results + commit hash or file list.
7. **Summarise** — report: result, commands executed, changed files, acceptance-criteria status, remaining risks, newly eligible tasks. **Stop.** Do not start the next task unless the instruction covered it.

### 4.3 Phase boundaries

- Each phase starts `PENDING`. Work in it can begin only after the user approves it (`approve-phase`). The tracker refuses `start` otherwise.
- Each phase ends with `Pnn-GATE` (user review) whose `Gates-done` lists every quality criterion due in that phase. Completing a gate does **not** approve the next phase.
- A failed mandatory quality gate blocks the tasks it lists and everything that depends on them until it is resolved and re-verified; independent tasks may continue.
- A phase may be approved while another is open if its prerequisites are `COMPLETED` (see §6 lanes).

## 5. Parallel execution rules

- Tasks in the **same wave** of an approved phase have no dependency on each other and may run concurrently **if** their write paths are disjoint (the *Conflict notes* under each wave state this). Tasks in different waves of one phase are sequential by dependency.
- Parallel work uses separate git worktrees/branches (subagents with `isolation: worktree`). **Workers never edit the tracking files**; the coordinating session runs `track.py start` for all tasks before dispatch and `check/complete` as each worker returns. This avoids write conflicts and keeps timestamps honest.
- Shared append-only files (route registry, `app_en.arb`, provider-override registry) use per-feature files or namespaced keys; resolve merge conflicts at integration and re-run the gates after merging.
- **Alembic:** at most one task per wave adds a migration revision; CI enforces a single head. Backend tasks that touch the same module are never parallel.
- Never parallelise: tasks sharing a dependency chain, anything writing the same module, security-sensitive refactors, or approval-required tasks awaiting the same user decision.

## 6. Program structure

| Phase | Title | Lane | Prerequisite phases | Tasks | Waves |
|---|---|---|---|---|---|
| P00 | Planning, Reconciliation & Governance | PLAN | — | 5 | 4 |
| P01 | Repository, Environment & Engineering Foundation | FOUNDATION | P00 | 17 | 7 |
| P02 | Flutter Design System (UX Gate 1) | MOBILE | P01 (P01-T06, P01-T10) | 9 | 6 |
| P03 | Priority Screens with DEMO Data (UX Gate 2) | MOBILE | P02 | 8 | 5 |
| P04 | Identity & Security Foundation | BACKEND | P01 | 10 | 6 |
| P05 | Portfolio Core: Database & Backend | BACKEND | P04 | 11 | 7 |
| P06 | Analytics, Forecasting & Wealth Planning (Backend) | BACKEND | P05 (P06-T01/T02 may start after P01-T07 once P06 is approved) | 11 | 6 |
| P07 | Remaining Screens with DEMO Data (UX Gate 3) | MOBILE | P03 | 10 | 5 |
| P08 | Market Data & Research Integration (Backend) | BACKEND | P05 | 10 | 6 |
| P09 | Mobile-Backend Integration (UX Gate 4) | INTEGRATION | P03, P04, P05, P06, P07, P08 | 11 | 6 |
| P10 | AI Tool Layer & Wealth Copilot | AI | P04, P05, P06 (P09-T01 for mobile wiring) | 11 | 7 |
| P11 | Multi-Currency Reporting & FX Management (FXCUR workstream) | CORE | P05, P06, P08, P09, P10 | 13 | 11 |
| P12 | AI Investment Intelligence & Portfolio Doctor | AI | P08, P10, P11 | 11 | 6 |
| P13 | Forex Trading Intelligence (FX workstream) | FX | P08, P09, P10, P11, P12 | 15 | 13 |
| P14 | Cloud Infrastructure & Deployment Pipeline | INFRA | P01 (early start allowed); deployment tasks need P04-T01 | 12 | 8 |
| P15 | Production Hardening & Quality Assurance | HARDENING | P09, P10, P11, P12, P14 | 12 | 6 |
| P16 | Release & Production Deployment | RELEASE | P15 | 9 | 7 |

**Valid single-lane order:** P00 → P01 → P02 → P03 → P04 → P05 → P06 → P07 → P08 → P09 → P10 → P11 → P12 → P13 → P14 → P15 → P16 (numeric order satisfies every dependency).

**Parallel lanes** (after `P01-GATE`, each needs its own phase approvals and worktree):

```text
P00 → P01 ─┬─ MOBILE  : P02 → P03 → P07 ──────────────┐
           ├─ BACKEND : P04 → P05 → P06 → P08 ────────┼─ P09 (join, UX gate 4) → P10 → P12 ─┐
           │            ▲ P04-T08 needs P02-GATE        │                                      ├─ P15 → P16
           │            ▲ P05-T10 needs P03-T01         │                                      │
           └─ INFRA   : P14 (T01 decision, T04 images, then IaC…) ─────────────────────────────┘
```

**Multi-currency reporting (P11, FXCUR):** placed after P10 because it needs the P05 FX service, P06 analytics, P08 FX ingestion and provider abstraction, the P09 live screens and the P10 AI tool framework; placing it before P12 means AI Intelligence, Forex and hardening get the reporting currency natively instead of retrofitting it.

**Forex workstream (P13):** runs after P12 and before P14. It is off the critical path of the core release, and its production enablement waits for P15 and the staging smoke tests in P14-T11.

**Critical path (longest dependency chain):** P00-GATE → P01 foundation → P04 identity → P05 core → P06 analytics → P09 integration → P10 Copilot → P11 multi-currency reporting → P12 Intelligence → P15 hardening → P16 release. P06-T01 (forecast engine) is pure code and can start right after P01 to de-risk the calculator early.

**Long-lead items to start early:** Apple/Google developer accounts (DEC-09), cloud decision (DEC-02), market-data licensing (DEC-04), LLM provider/budget (DEC-05), legal review (DEC-10), Android toolchain (P01-T01).

## 7. Check suites and platform quality gates

### 7.1 Check suites (CK-*)

| Gate | Applies to | Commands (run from the stated directory) |
|---|---|---|
| **CK-M** Mobile | `mobile/wealthsphere_app` | `dart format --output=none --set-exit-if-changed .` · `flutter analyze` · `flutter test` |
| **CK-G** Goldens | mobile | `flutter test --tags golden` (authoritative on CI ubuntu) |
| **CK-I** Integration | mobile | `flutter test integration_test -d <emulator-id>` |
| **CK-B** Backend | `backend/` | `ruff format --check .` · `ruff check .` · `mypy .` · `pytest` |
| **CK-DB** Migrations | `backend/` | `alembic upgrade head` · `alembic check` · `alembic downgrade base` · `alembic upgrade head` · single-head test |
| **CK-API** Contract | `backend/` | `python scripts/export_openapi.py --check` · `spectral lint openapi.json` |
| **CK-S** Security | repo root | `gitleaks detect` · `pip-audit` · `bandit -r backend/app` (or semgrep) · `trivy image <img>` · `syft` SBOM · Dart `flutter pub outdated` review |
| **CK-INF** Infrastructure | `infrastructure/terraform` | `terraform fmt -check -recursive` · `terraform validate` · `tflint` · `checkov -d .` |
| **CK-TRK** Tracking | repo root | `python scripts/track.py validate` (run after every tracker change) |

Tool choices (ruff, mypy, uv, Spectral, k6) are proposals recorded in ADR-0004/0007 (P01-T03) and can be changed there before use. A task may only be completed when its listed gates pass **and** its acceptance criteria are evidenced.

### 7.2 Platform quality gates (QG-01 … QG-25)

**QUALITY_GATES.md is the authoritative quality-gate register.** Each gate lists its criteria as checkboxes with a stable id (`QG-06.2`), the phase in which the criterion first becomes required, the task that produces its evidence, and a CRITICAL flag for security, financial-integrity and authorisation criteria. Gate statuses: `NOT_STARTED`, `IN_PROGRESS`, `BLOCKED`, `FAILED`, `PASSED`, `WAIVED`.

| Gate | Name | Criteria | Critical | Required in phases |
|---|---|---|---|---|
| QG-01 | Architecture and Design | 5 | 0 | P01, P02, P05, P15 |
| QG-02 | Code Quality | 6 | 1 | P01 |
| QG-03 | Automated Testing | 6 | 1 | P01, P05, P06, P09 |
| QG-04 | Android Platform | 7 | 0 | P01, P03, P04, P15, P16 |
| QG-05 | iOS Platform | 6 | 0 | P01, P03, P04, P15, P16 |
| QG-06 | Financial Accuracy and Data Integrity | 7 | 7 | P05, P06, P08 |
| QG-07 | AI Reliability and Investment Intelligence | 8 | 4 | P10, P12 |
| QG-08 | Security and Privacy | 8 | 6 | P01, P04, P14, P15 |
| QG-09 | Performance and Scalability | 6 | 0 | P08, P15 |
| QG-10 | CI/CD and Infrastructure | 8 | 0 | P01, P14 |
| QG-11 | End-to-End Integration | 6 | 1 | P08, P09, P10 |
| QG-12 | Production Release Readiness | 8 | 3 | P15, P16 |
| QG-13 (QG-FX-01) | Forex Market Data Integrity | 5 | 2 | P13 |
| QG-14 (QG-FX-02) | Forex Technical Indicator Accuracy | 3 | 0 | P13 |
| QG-15 (QG-FX-03) | Forex Prediction Model Validation | 6 | 0 | P13 |
| QG-16 (QG-FX-04) | Forex Trading Risk Accuracy | 5 | 5 | P13 |
| QG-17 (QG-FX-05) | Forex Backtesting Integrity | 4 | 1 | P13 |
| QG-18 (QG-FX-06) | Forex AI Trading Intelligence | 5 | 2 | P13 |
| QG-19 (QG-FX-07) | Forex Mobile Experience | 5 | 0 | P13 |
| QG-20 (QG-FX-08) | Forex Release and Regulatory Readiness | 5 | 4 | P13 |
| QG-21 (QG-FXCUR-01) | Exchange Rate Accuracy | 5 | 5 | P11 |
| QG-22 (QG-FXCUR-02) | Portfolio Consistency | 5 | 5 | P11 |
| QG-23 (QG-FXCUR-03) | FX Data Reliability | 5 | 0 | P11 |
| QG-24 (QG-FXCUR-04) | Multi-Currency Android and iOS | 7 | 0 | P11 |
| QG-25 (QG-FXCUR-05) | Multi-Currency AI Integration | 5 | 4 | P11 |

**Gate types per phase (spec 8.2):**

| Type | Meaning | How it is enforced |
|---|---|---|
| Entry gates | Conditions before a phase begins | Prerequisite phase gates (`Pnn-GATE`) are added as dependencies of every wave-1 task (one documented exception: P06-T01 may start after P01-GATE). Phase approval by the user is also required. |
| Task-level gates | Checks before a task is marked complete | The task's CK check suites and acceptance criteria are evidenced; tasks bound to QG criteria carry `Gates-done` and `track.py complete` refuses until those criteria are verified or validly waived. |
| Exit gates | Conditions before the phase is complete | `Pnn-GATE` carries `Gates-done` = every criterion first required in that phase; the gate cannot complete, and the phase cannot be closed, until they are satisfied. |
| Release gates | Extra conditions before staging or production | `Gates-start` on P14-T11 (staging), P16-T03 (production deployment) and P16-T07 (store submission); `track.py start` refuses until satisfied. CI repeats the check with `track.py qg require`. |

**Enforcement rules (tracker-implemented):**

- A phase cannot be completed unless all of its mandatory exit-gate criteria are satisfied (verified with evidence, or under an active waiver).
- `qg fail <criterion> --issue … --blocks <task ids>` sets the gate `FAILED`, unticks the criterion and lists the blocked tasks; `start` and `complete` of those tasks (and therefore their dependents) are refused until `qg resolve` and a fresh `qg check` with new evidence. Tasks not listed and not dependent on them continue.
- `qg check` requires an evidence statement and records the verification timestamp; `QG-12.1` additionally verifies that every core criterion due by P15 is satisfied (all gates except QG-12 and the optional Forex gates QG-13…QG-20; the multi-currency gates QG-21…QG-25 are core).
- A gate becomes `PASSED` only via `qg pass` once every criterion is satisfied; `QG-12` and any gate with waived criteria also require `--approved-by`.
- `validate` reports a COMPLETED task whose gate criteria are no longer satisfied as a regression warning, and fails if a gate shows PASSED/WAIVED without satisfied criteria, evidence and ISO 8601 timestamps.
- Nothing is auto-ticked: only `qg check` with evidence ticks a criterion; timestamps always come from the system clock.

**Waivers (spec 8.3):** `qg waive <criterion> --justification … --approved-by … --risk-owner … --expires YYYY-MM-DD` records an entry in the waiver register of QUALITY_GATES.md. A waiver needs explicit approval, justification, a future expiry/review date and a named risk owner; expired waivers fail `validate`. **Criteria flagged CRITICAL (all of QG-06, authorisation/security items in QG-07/QG-08, QG-02.4 secrets, QG-03.4, QG-11.3, QG-12.3/.7/.8) are never waived by the tracker**: relaxing one requires a user-approved plan change recorded in EXECUTION_LOG.md.

**Completion procedure for each gate or criterion (spec 8.5):**

1. `qg start <gate>` — records the real start timestamp (also set automatically by the first `qg check`).
2. Run the validation commands listed in the criterion's evidence task and the CK suites.
3. Capture results and reports; store reports under `reports/quality/` and cite them as evidence.
4. Failures: `qg fail … --issue … --blocks …`; create remediation tasks through a plan-change entry; remediate.
5. `qg resolve <gate> --note …`, then re-run the failed checks.
6. `qg check <criterion…> --evidence …` with fresh evidence; `qg pass <gate> --evidence …` when all criteria are satisfied.
7. End and verification timestamps are recorded by the tracker; `qg reverify` refreshes the verification timestamp on later re-runs.
8. The tracker refreshes QUALITY_GATES.md, PROGRESS_DASHBOARD.md and EXECUTION_LOG.md.

**CI/CD integration (spec 8.4):** P01-T15 makes backend, mobile, security and tracker checks required status checks with branch protection; P14-T08 builds the pipeline so staging deploys only after build, test, security and integration jobs succeed and production needs a protected-environment approval plus `track.py qg require` on the production start gates; P14-T11, P16-T03 and P16-T07 are the corresponding release-gate tasks. Gate results are written to QUALITY_GATES.md, surfaced in PROGRESS_DASHBOARD.md and referenced in EXECUTION_LOG.md by the tracker.

### 7.3 Phase gate matrix

| Phase | Entry (prerequisite phases) | Exit criteria required | Release gates |
|---|---|---|---|
| P00 | — | none | — |
| P01 | P00 | QG-01.1–2; QG-02.1–6; QG-03.1,6; QG-04.1–3; QG-05.1–2; QG-08.3,6; QG-10.1,3 | — |
| P02 | P01 | QG-01.5 | — |
| P03 | P02 | QG-04.4; QG-05.3 | — |
| P04 | P01 | QG-04.5; QG-05.4; QG-08.1 | — |
| P05 | P04 | QG-01.3; QG-03.2; QG-06.2,5 | — |
| P06 | P05 | QG-03.4–5; QG-06.1,3,4,6 | — |
| P07 | P03 | none | — |
| P08 | P05 | QG-06.7; QG-09.5; QG-11.4 | — |
| P09 | P03, P04, P05, P06, P07, P08 | QG-03.3; QG-11.1,2,5,6 | — |
| P10 | P04, P05, P06 | QG-07.1,2,3,5,6,8; QG-11.3 | — |
| P11 | P05, P06, P08, P09, P10 | QG-21 … QG-25 (every criterion) | P11-T11, P11-T12 (QG-21..QG-25 satisfied before start) |
| P12 | P08, P10, P11 | QG-07.4,7 | — |
| P13 | P08, P09, P10, P11, P12 | QG-13 … QG-20 (every criterion) | P13-T13, P13-T14 (QG-13..QG-19 satisfied before start) |
| P14 | P01 | QG-08.4,5,7; QG-10.2,4,5,6,7,8 | P14-T11 |
| P15 | P09, P10, P11, P12, P14 | QG-01.4; QG-04.6; QG-05.5; QG-08.2,8; QG-09.1,2,3,4,6; QG-12.1,3,4,7 | — |
| P16 | P15 | QG-04.7; QG-05.6; QG-12.2,5,6,8 | P16-T03, P16-T07 |


## 8. Decision register

| ID | Decision / input needed | Needed by | Owner | State |
|---|---|---|---|---|
| DEC-01 | App identifiers (organisation reverse-domain, Android applicationId, iOS bundle ID) | P01-T06 | User | Resolved: com.kmdmtisya |
| DEC-02 | Cloud provider (AWS / GCP / OCI), region(s) and data-residency approach (UAE/Kenya users) | P14-T01 | User | Open |
| DEC-03 | Forecast numbers in the demo UI. Resolved by structure: canned fixtures in P03 (no maths in Dart), real engine from P06-T01 wired in P09-T03. User may pull P06-T01/T02 earlier. | P03-T04 | Plan | Resolved (override allowed) |
| DEC-04 | Market-data and research providers, budget and licence terms | P08-T01 | User | Open |
| DEC-05 | LLM provider, model, monthly budget and API-key custody (docs name OpenAI first) | P10-T01 | User | Open |
| DEC-06 | Money rounding convention (half-up vs half-even) and minor-unit handling | P01-T03 | User + Claude | Resolved: ROUND_HALF_UP (ADR-0006) |
| DEC-07 | Backend tooling: uv + ruff + mypy + pytest (proposed) | P01-T03 | Claude proposes | Resolved: uv, ruff, mypy, pytest (ADR-0004) |
| DEC-08 | Push-notification path (FCM + APNs) and Firebase project | P09-T08 | User | Open |
| DEC-09 | Apple Developer and Google Play accounts / legal entity (long lead time: start during P09) | P16-T01 | User | Open |
| DEC-10 | Jurisdictions, regulatory classification and disclaimer wording (legal review) | P12-T10 / P15-T05 | User + legal | Open |
| DEC-11 | Penetration-test provider (external vs internal) | P15-T03 | User | Open |
| DEC-12 | Offline cache storage (encrypted Drift vs alternatives) | P09-T06 | Claude proposes, user approves | Open |
| DEC-13 | Charts library: fl_chart (open-source, proposed) vs Syncfusion (licence) | P02-T06 | User | Resolved: fl_chart (confirmed 2026-10-09) |
| DEC-15 | Supported Android versions (minimum API level) and iOS versions/devices | P01-T16 | User | Resolved: Android 8.0 (API 26), iOS 16.0 |
| DEC-16 | Measurable performance targets: app start-up, memory, crash rate, API p95/p99 SLOs, database query thresholds | P01-T16 | User | Resolved: targets approved (design workload to be revisited at P06 baseline) |
| DEC-17 | AI evaluation datasets and acceptance thresholds for QG-07 | P01-T16 / P10-T09 | User + Claude | Resolved: approach and zero-tolerance list approved; datasets drafted in P10-T09 |
| DEC-18 | Quality-gate owners and risk owners for waivers (default Unassigned) | P01-T15 | User | Open |
| DEC-14 | Concept-board tab labels differ from the written spec: follow the spec (ADR-0002) | P01-T03 | Plan | Resolved |
| DEC-19 | Forex market-data provider(s): streaming licence, redistribution and display rights, cost, instrument coverage (candidates to evaluate: OANDA, Interactive Brokers, other licensed vendors); tradable vs indicative quotes | P13-T01 / P13-T02 | User | Open |
| DEC-20 | Forex launch markets, regulatory classification (information vs advice), disclosure wording and legal review | P13-T01 / P13-T14 | User + legal | Open |
| DEC-21 | Time-series storage: PostgreSQL native partitioning (proposed) vs TimescaleDB extension | P13-T02 | Claude proposes, user approves | Open |
| DEC-22 | Forecasting stack and v1 model scope: statsmodels, scikit-learn, LightGBM/XGBoost baselines (proposed); LSTM/GRU/Transformer research-only behind a separate gate | P13-T05 | Claude proposes, user approves | Open |
| DEC-23 | Forex release strategy: ship with v1 or after v1 behind a feature flag (proposed: after v1, flagged) | P13-T01 | User | Open |
| DEC-24 | Source of instrument contract specifications (lot size, pip location, margin rules): provider API vs maintained, reviewed table | P13-T07 | Claude proposes, user approves | Open |
| DEC-25 | FX rate provider(s) for reporting conversion: primary and fallback (candidates: Open Exchange Rates, ExchangeRate-API, Currencylayer, OANDA, or the P08/DEC-04 provider), licence for in-app display and caching, quota | P11-T01 / P11-T03 | User | Open |
| DEC-26 | Rate refresh cadence and staleness thresholds (current / cached / stale) per provider tier | P11-T03 | Claude proposes, user approves | Open |
| DEC-27 | Cross-rate pivot currency (proposed USD) and per-currency display precision | P11-T04 | Claude proposes, user approves | Open |
| DEC-28 | Conversion-audit scope and retention: which conversions are financial records (proposed: AI and report conversions, not cosmetic UI switches) | P11-T02 / P11-T12 | User | Open |
| DEC-29 | Optional FX scenario overlay on forecasts in v1, or later (proposed: later) | P11-T06 | User | Open |

## 9. Key risks

| Risk | Mitigation |
|---|---|
| Demo UI diverges from the real API | Typed repositories mirror the planned endpoints; P05-T10 reconciles DTOs vs OpenAPI before P09. |
| Financial formula errors | Deterministic engines, golden/property tests, independent recomputation and user review (P06-T10). |
| Cross-user data leakage (critical) | Ownership harness (P04-T03), IDOR tests per endpoint (P05-T09), AI tool authz tests (P10-T09), cache isolation tests. |
| LLM invents facts or guarantees returns | Allow-listed tools, validated four-section output, guarantee-language guard, evidence-only opportunity explanations. |
| Market-data licence or cost surprises | Licensing decision before adapters (P08-T01); fake provider keeps development unblocked. |
| iOS verification gap on Windows | macOS CI build now; Mac/cloud device for VoiceOver and release builds. |
| Store review delays for a finance app | Accounts and declarations started early (DEC-09, P16-T05); no advice/guarantee wording. |
| Gates become paperwork (criteria ticked without real evidence) | Tracker requires an evidence statement and timestamp per criterion, `validate` checks them, critical criteria cannot be waived, and P15-T11 re-verifies everything on the release candidate. |
| Scope creep into trading/robo-advice | Explicit non-goal; no execution affordances (D6). The Forex module (P13) is bounded to decision support and paper trading; live execution needs a separate approved phase (ADR-0009). |
| Forex data licence or redistribution limits (display, storage, streaming) | DEC-19 and the licence review (P13-T14) before any provider is wired to users; fake provider keeps development unblocked; indicative rates are labelled and never shown as executable quotes. |
| Forex regulatory classification (advice or arrangement of dealing) in a launch market | DEC-20 legal review before release; information-only wording, risk disclosures, no personalised recommendations or execution. |
| Overfitted or leaky forecasts create false confidence | Time-series-aware splits, walk-forward evaluation, leakage tests, baseline comparison reported even when the baseline wins, calibration labelling (QG-15, QG-17). |
| Leverage and stop-loss misunderstandings harm users | Risk engine returns margin and leverage warnings and states that stops can gap or slip; paper trading first; disclosures reviewed (QG-16, QG-20). |
| Streaming outage or stale prices shown as live | Heartbeat, stale-data detection, explicit feed status in the UI and API, no invented prices (QG-13). |
| Reporting-currency figures disagree between screens, reports and AI | One rate snapshot per view/report, reconciliation tests, AI tools use the same conversion service (QG-22, QG-25). |
| A display-currency switch mutates stored amounts | Conversion is read-only; originals and transaction rates are immutable; tests assert unchanged records (QG-22.2). |
| FX provider outage or quota exhaustion | Fallback provider, central cache, backoff, explicit cached/unavailable status; never invented rates (QG-23). |

## 10. Phase and task detail

### P00 — Planning, Reconciliation & Governance

- **Goal:** Reconcile the documentation against the repository, produce the roadmap and tracking system, and obtain user approval before any application work.
- **Entry criteria:** None (bootstrap).
- **Exit criteria:** Plan and tracking documents reviewed and approved by the user in writing.
- **Prerequisite phases:** — · **Lane:** PLAN
- **Entry gates:** prerequisite phase gates completed (none); cumulative quality criteria none; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** none (required by `P00-GATE`) plus user review.
- **Release gates:** —

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P00.W1 | P00-T01, P00-T03 | Parallel-safe | Phase approved and cross-phase prerequisites complete | — |
| P00.W2 | P00-T02 | Single task | All dependencies from earlier waves of P00 complete | — |
| P00.W3 | P00-T04 | Single task | All dependencies from earlier waves of P00 complete | — |
| P00.W4 | P00-GATE | Single task | All dependencies from earlier waves of P00 complete | — |

#### P00-T01 — Review documentation and reconcile repository state

`DOC` · Size S · Wave P00.W1 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Read CLAUDE.md, SOLUTION_INTENT.md, the project brief, the implementation guide and the UI/UX PDF; inventory the repository; record what is and is not implemented.
- **Depends on:** —
- **Parallel with:** P00-T03
- **Unblocks:** P00-T02, P00-GATE
- **Deliverables:** Reconciliation findings in EXECUTION_LOG.md and the baseline section of EXECUTION_PLAN.md.
- **Acceptance criteria:**
  - Baseline states only documentation exists; no source, tests, CI, containers or infrastructure are claimed as done.
  - Conflicts between documents are listed with a proposed resolution.
- **Verification:** Re-run `find . -type f` and `git status`; confirm the baseline table matches.
- **Subtasks:** `P00-T01.1` Read the four Markdown documents and the PDF (incl. the concept board on page 8) · `P00-T01.2` Inventory repository files and toolchain versions · `P00-T01.3` Record conflicts and decisions (D1-D9, DEC-01..DEC-14)

#### P00-T02 — Create the execution plan and tracking system

`DOC` · Size M · Wave P00.W2 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Produce EXECUTION_PLAN.md, TASK_CHECKLIST.md, PROGRESS_DASHBOARD.md, EXECUTION_LOG.md and scripts/track.py.
- **Depends on:** P00-T01
- **Parallel with:** — (sequential)
- **Unblocks:** P00-T04, P00-GATE
- **Deliverables:** Four tracking documents plus the tracker script.
- **Acceptance criteria:**
  - `python scripts/track.py validate` passes (unique IDs, acyclic dependencies, wave order, checkbox/status consistency).
  - No task other than P00 tasks is marked started or completed; no timestamps are fabricated.
- **Verification:** `python scripts/track.py validate && python scripts/track.py dashboard`
- **Subtasks:** `P00-T02.1` Define task, wave and status model · `P00-T02.2` Write the roadmap data for P00-P16 · `P00-T02.3` Implement and test scripts/track.py on a scratch copy · `P00-T02.4` Generate the four documents

#### P00-T03 — Draft the UI-specific execution plan (supplementary)

`DOC` · Size S · Wave P00.W1 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Detailed UI step guidance for the design system and priority screens, kept as a reference for P01-T06 and P02/P03 tasks.
- **Depends on:** —
- **Parallel with:** P00-T01
- **Unblocks:** P00-GATE
- **Deliverables:** docs/UI_EXECUTION_PLAN.md (supplementary; EXECUTION_PLAN.md is authoritative where they differ).
- **Acceptance criteria:**
  - File exists and is cross-referenced from the relevant P01/P02/P03 tasks via the Ref field.
- **Verification:** `ls docs/UI_EXECUTION_PLAN.md`
- **Subtasks:** `P00-T03.1` Draft plan · `P00-T03.2` Add supersession note pointing to EXECUTION_PLAN.md

#### P00-T04 — Define the quality-gate framework and register

`DOC` · Size M · Wave P00.W3 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Add the mandatory platform quality gates QG-01..QG-12 (spec section 8) as first-class dependencies: authoritative register, phase entry/task/exit/release gate bindings, waiver rules, tracker enforcement.
- **Depends on:** P00-T02
- **Parallel with:** — (sequential)
- **Unblocks:** P00-GATE
- **Deliverables:** QUALITY_GATES.md, tracker `qg` commands, gate bindings in EXECUTION_PLAN.md and TASK_CHECKLIST.md, dashboard section.
- **Acceptance criteria:**
  - `python scripts/track.py validate` passes including QUALITY_GATES.md checks (criteria, bindings, waivers).
  - Every phase gate lists the criteria it requires; release tasks list start-gates.
  - No gate or criterion is marked passed; no timestamps fabricated.
- **Verification:** CK-TRK; `python scripts/track.py qg status`
- **Subtasks:** `P00-T04.1` Transcribe QG-01..QG-12 criteria with required-at phase and evidence tasks · `P00-T04.2` Bind gates to phase gates and release tasks · `P00-T04.3` Implement qg commands, waiver rules and enforcement in scripts/track.py · `P00-T04.4` Test on a scratch copy · `P00-T04.5` Regenerate tracking documents

#### P00-GATE — Plan approval gate

`GATE` · Size S · Wave P00.W4 · Approval: **USER REVIEW REQUIRED**

- **Objective:** User reviews and approves the roadmap, decisions and tracking approach.
- **Depends on:** P00-T01, P00-T02, P00-T03, P00-T04
- **Parallel with:** — (sequential)
- **Unblocks:** P01-T01, P01-T02
- **Deliverables:** Written user approval recorded in EXECUTION_LOG.md.
- **Acceptance criteria:**
  - User confirmed the plan, or listed changes that were then applied and re-reviewed.
- **Verification:** User statement; `python scripts/track.py validate`.
- **Subtasks:** `P00-GATE.1` Present plan summary · `P00-GATE.2` Apply requested changes · `P00-GATE.3` Record approval

### P01 — Repository, Environment & Engineering Foundation

- **Goal:** A versioned monorepo with a working local stack, backend and mobile skeletons, CI, security scanning and engineering standards. No business features.
- **Entry criteria:** P00 approved; DEC-01 (app identifiers) and DEC-06/DEC-07 decided or defaulted.
- **Exit criteria:** All skeleton apps build and test green in CI; local stack starts with one command; ADRs and architecture docs approved.
- **Prerequisite phases:** P00 · **Lane:** FOUNDATION
- **Entry gates:** prerequisite phase gates completed (P00); cumulative quality criteria none; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria; additionally quality criteria: P01-T15 → QG-02.3,5; QG-03.6; P01-T16 → QG-04.3; QG-05.2.
- **Exit gates:** QG-01.1–2; QG-02.1–6; QG-03.1,6; QG-04.1–3; QG-05.1–2; QG-08.3,6; QG-10.1,3 (required by `P01-GATE`) plus user review.
- **Release gates:** —

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P01.W1 | P01-T01, P01-T02 | Parallel-safe | Phase approved and cross-phase prerequisites complete | — |
| P01.W2 | P01-T03, P01-T04, P01-T05, P01-T06 | Parallel-safe | All dependencies from earlier waves of P01 complete | T03 and T04 write only docs/; T05 writes infra/docker; T06 writes mobile/. Disjoint paths. |
| P01.W3 | P01-T07, P01-T10, P01-T16 | Parallel-safe | All dependencies from earlier waves of P01 complete | T07 writes backend/; T10 writes .github/workflows/mobile.yml. Disjoint paths. |
| P01.W4 | P01-T08, P01-T09 | Parallel-safe | All dependencies from earlier waves of P01 complete | T08 writes backend/app/db and alembic; T09 writes .github/workflows/backend.yml. |
| P01.W5 | P01-T11, P01-T12, P01-T13, P01-T14 | Parallel-safe | All dependencies from earlier waves of P01 complete | — |
| P01.W6 | P01-T15 | Single task | All dependencies from earlier waves of P01 complete | — |
| P01.W7 | P01-GATE | Single task | All dependencies from earlier waves of P01 complete | — |

#### P01-T01 — Verify local environment readiness

`ENV` · Size S · Wave P01.W1 · Approval: no

- **Objective:** Confirm every tool the roadmap needs is installed and working, and list user actions for anything missing.
- **Depends on:** P00-GATE
- **Parallel with:** P01-T02
- **Unblocks:** P01-T05, P01-T06, P01-GATE
- **Deliverables:** Environment report in the evidence field; install notes in docs/dev-setup.md.
- **Acceptance criteria:**
  - Docker daemon responds to `docker info`.
  - `flutter doctor` shows no [!] for Android toolchain and an emulator boots.
  - Terraform (>=1.9) installed, or an explicit decision to defer to P14.
  - Python >=3.13 and uv available.
- **Verification:** `docker info`, `flutter doctor -v`, `terraform version`, `python --version`, `uv --version`, `emulator -list-avds`
- **Subtasks:** `P01-T01.1` Start Docker Desktop and confirm `docker info` · `P01-T01.2` Run `flutter doctor --android-licenses` and fix Android toolchain · `P01-T01.3` Create/boot an Android emulator · `P01-T01.4` Install Terraform (or defer) · `P01-T01.5` Record versions

#### P01-T02 — Initialise repository and governance files

`REPO` · Size S · Wave P01.W1 · Approval: no · Ref: UI plan Step 0

- **Objective:** Create the git repo and root files the guides assume.
- **Depends on:** P00-GATE
- **Parallel with:** P01-T01
- **Unblocks:** P01-T03, P01-T04, P01-T05, P01-T06, P01-GATE
- **Deliverables:** git history, .gitignore, .editorconfig, README.md, root CLAUDE.md (reading-order paths fixed), docs/design/wealthsphere-ui-concept.png.
- **Acceptance criteria:**
  - `git log` shows an initial commit on `main`.
  - CLAUDE.md is at the repository root and its paths point to docs/.
  - Concept board image extracted from the PDF page 8 and opens.
- **Verification:** `git log --oneline`; `ls CLAUDE.md docs/design/`
- **Subtasks:** `P01-T02.1` git init (default branch main) and first commit of existing docs · `P01-T02.2` Add .gitignore/.editorconfig/README · `P01-T02.3` Move CLAUDE.md to root and fix paths (D8) · `P01-T02.4` Extract concept board PNG from the PDF

#### P01-T03 — Record foundational ADRs

`DOC` · Size S · Wave P01.W2 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Document the decisions that later tasks depend on.
- **Depends on:** P01-T02
- **Parallel with:** P01-T04, P01-T05, P01-T06
- **Unblocks:** P01-T07, P01-T16, P01-GATE, P02-T03, P06-T01
- **Deliverables:** docs/adr/0001..0007: UI-first with demo data; primary navigation; client money representation; modular-monolith backend layout and Python tooling; repo layout; money rounding conventions; testing strategy.
- **Acceptance criteria:**
  - Each ADR has Context / Decision / Consequences.
  - Rounding convention (DEC-06) is explicit and testable.
- **Verification:** Review the ADR files; `git diff --stat`.
- **Subtasks:** `P01-T03.1` ADR-0001 UI-first (D1) · `P01-T03.2` ADR-0002 navigation (D2) · `P01-T03.3` ADR-0003 client money (D4) · `P01-T03.4` ADR-0004 backend layout and tooling (DEC-07) · `P01-T03.5` ADR-0005 repo layout · `P01-T03.6` ADR-0006 rounding conventions (DEC-06) · `P01-T03.7` ADR-0007 test strategy

#### P01-T04 — Write architecture and governance documents

`DOC` · Size M · Wave P01.W2 · Approval: no

- **Objective:** Create the four docs the guide requires.
- **Depends on:** P01-T02
- **Parallel with:** P01-T03, P01-T05, P01-T06
- **Unblocks:** P01-GATE
- **Deliverables:** docs/architecture.md, docs/security.md, docs/api-conventions.md, docs/ai-governance.md.
- **Acceptance criteria:**
  - Each document covers the guide section it derives from and links to the ADRs.
  - AI governance states the allow-list, audit and no-SQL rules.
- **Verification:** Manual review against implementation guide sections 4, 8, 9, 12.
- **Subtasks:** `P01-T04.1` architecture.md (modules, data flow, boundaries) · `P01-T04.2` security.md (controls, secrets, threat-model stub) · `P01-T04.3` api-conventions.md (versioning, errors, pagination, money as strings, idempotency) · `P01-T04.4` ai-governance.md (tool contract, evidence rules)

#### P01-T05 — Docker Compose development stack

`INF` · Size M · Wave P01.W2 · Approval: no

- **Objective:** Start PostgreSQL, Redis, RabbitMQ and Keycloak locally with one command.
- **Depends on:** P01-T01, P01-T02
- **Parallel with:** P01-T03, P01-T04, P01-T06
- **Unblocks:** P01-T07, P01-GATE, P04-T01, P08-T04
- **Deliverables:** docker-compose.yml, .env.example, Makefile targets (up/down/logs/reset), infra/docker/*.
- **Acceptance criteria:**
  - `docker compose up -d` brings all services to healthy.
  - No secret values are committed; .env is git-ignored.
- **Verification:** `docker compose up -d && docker compose ps` (all healthy); `gitleaks detect`
- **Subtasks:** `P01-T05.1` Compose file with healthchecks and named volumes · `P01-T05.2` .env.example with placeholders only · `P01-T05.3` Makefile helpers · `P01-T05.4` Document ports and reset procedure

#### P01-T06 — Flutter app scaffold and tooling

`MOB` · Size M · Wave P01.W2 · Approval: no · Ref: UI plan Step 1

- **Objective:** Create the Android/iOS app with the agreed packages, lints, localisation and test harness.
- **Depends on:** P01-T01, P01-T02
- **Parallel with:** P01-T03, P01-T04, P01-T05
- **Unblocks:** P01-T10, P01-GATE, P02-T01, P02-T03, P04-T06
- **Deliverables:** mobile/wealthsphere_app with Riverpod 3, GoRouter, Freezed/json_serializable, decimal, intl, fl_chart, shared_preferences, gen-l10n, pump_app helper, golden tag.
- **Acceptance criteria:**
  - `flutter analyze` clean; `flutter test` passes.
  - App launches on the Android emulator.
  - Dio, secure storage and local_auth are NOT yet added (D9).
- **Verification:** CK-M; `flutter run -d <emulator>`
- **Subtasks:** `P01-T06.1` flutter create with org id from DEC-01 · `P01-T06.2` Add dependencies via `flutter pub add` · `P01-T06.3` analysis_options.yaml strict lints · `P01-T06.4` l10n.yaml and app_en.arb · `P01-T06.5` test/helpers/pump_app.dart and dart_test.yaml golden tag

#### P01-T07 — FastAPI backend skeleton

`BE` · Size M · Wave P01.W3 · Approval: no

- **Objective:** Create the modular-monolith backend with health endpoints, configuration, logging and test tooling.
- **Depends on:** P01-T03, P01-T05
- **Parallel with:** P01-T10, P01-T16
- **Unblocks:** P01-T08, P01-T09, P01-T12, P01-T14, P01-GATE, P06-T01, P08-T04, P14-T04
- **Deliverables:** backend/ with app factory, /health/live and /health/ready, pydantic-settings config, structured JSON logging, correlation IDs, RFC 7807 error model, ruff, mypy, pytest.
- **Acceptance criteria:**
  - Health endpoints return 200; readiness reflects DB/Redis state.
  - Correlation ID is accepted, generated and echoed.
  - CK-B passes.
- **Verification:** CK-B; `curl localhost:8000/health/ready`
- **Subtasks:** `P01-T07.1` Project layout per ADR-0004 · `P01-T07.2` Config via environment (no secrets in code) · `P01-T07.3` Logging and correlation-ID middleware · `P01-T07.4` Error model · `P01-T07.5` Test setup incl. async client

#### P01-T08 — SQLAlchemy 2 and Alembic baseline

`DB` · Size M · Wave P01.W4 · Approval: no

- **Objective:** Database session management and the migration pipeline.
- **Depends on:** P01-T07
- **Parallel with:** P01-T09
- **Unblocks:** P01-GATE, P04-T02
- **Deliverables:** backend/app/db, alembic.ini, baseline revision, test database fixtures.
- **Acceptance criteria:**
  - `alembic upgrade head` and `downgrade base` both succeed on an empty database.
  - Single Alembic head is enforced by a test.
- **Verification:** CK-DB
- **Subtasks:** `P01-T08.1` Async engine/session factory · `P01-T08.2` Declarative base with naming conventions and UUID/NUMERIC types · `P01-T08.3` Baseline migration · `P01-T08.4` Test DB fixture and single-head test

#### P01-T09 — CI pipeline: backend

`INF` · Size S · Wave P01.W4 · Approval: no

- **Objective:** Run backend quality gates on every push/PR.
- **Depends on:** P01-T07
- **Parallel with:** P01-T08
- **Unblocks:** P01-T11, P01-T13, P01-T14, P01-T15, P01-GATE
- **Deliverables:** .github/workflows/backend.yml (ruff, mypy, pytest with Postgres/Redis services).
- **Acceptance criteria:**
  - Workflow green on main.
  - Path filters limit it to backend/** changes.
- **Verification:** Push a branch; confirm the workflow run URL in evidence.
- **Subtasks:** `P01-T09.1` Workflow with service containers · `P01-T09.2` Caching · `P01-T09.3` Required-check documentation

#### P01-T10 — CI pipeline: mobile

`INF` · Size S · Wave P01.W3 · Approval: no · Ref: UI plan Step 1

- **Objective:** Run Flutter gates on Linux and an iOS compile on macOS.
- **Depends on:** P01-T06
- **Parallel with:** P01-T07, P01-T16
- **Unblocks:** P01-T11, P01-T13, P01-T15, P01-GATE, P02-T01
- **Deliverables:** .github/workflows/mobile.yml (format, analyze, test incl. goldens on ubuntu; `flutter build ios --no-codesign` on macos).
- **Acceptance criteria:**
  - Both jobs green on main.
  - Goldens run only on the ubuntu job.
- **Verification:** Push a branch; record run URLs.
- **Subtasks:** `P01-T10.1` Ubuntu job · `P01-T10.2` macOS iOS build job · `P01-T10.3` Artifact upload of failed golden diffs

#### P01-T11 — Security and supply-chain baseline in CI

`SEC` · Size M · Wave P01.W5 · Approval: no

- **Objective:** Automated secret scanning, dependency audit, SAST, container scan and SBOM.
- **Depends on:** P01-T09, P01-T10
- **Parallel with:** P01-T12, P01-T13, P01-T14
- **Unblocks:** P01-T15, P01-GATE, P14-T04
- **Deliverables:** gitleaks, pip-audit, bandit/semgrep, Trivy, Syft SBOM jobs; Dependabot config; SECURITY.md.
- **Acceptance criteria:**
  - A seeded dummy secret on a test branch is detected and fails CI.
  - SBOM artifact is produced.
  - High/critical findings fail the build.
- **Verification:** CK-S
- **Subtasks:** `P01-T11.1` Secret scanning · `P01-T11.2` Python and Dart dependency audit · `P01-T11.3` SAST · `P01-T11.4` Container image scan · `P01-T11.5` SBOM and Dependabot

#### P01-T12 — Observability baseline

`BE` · Size M · Wave P01.W5 · Approval: no

- **Objective:** Telemetry hooks and a log schema with redaction.
- **Depends on:** P01-T07
- **Parallel with:** P01-T11, P01-T13, P01-T14
- **Unblocks:** P01-GATE, P14-T09
- **Deliverables:** OpenTelemetry tracing/metrics wiring, /metrics endpoint (internal), log redaction filter, docs/observability.md.
- **Acceptance criteria:**
  - Traces and metrics appear in the local collector.
  - Tests prove tokens, passwords and amounts are redacted from logs.
- **Verification:** CK-B; local collector shows spans.
- **Subtasks:** `P01-T12.1` OTel instrumentation · `P01-T12.2` Prometheus metrics · `P01-T12.3` Redaction filter and tests · `P01-T12.4` Document log schema

#### P01-T13 — Developer standards and workflow

`DOC` · Size S · Wave P01.W5 · Approval: no

- **Objective:** Make the Definition of Done enforceable.
- **Depends on:** P01-T09, P01-T10
- **Parallel with:** P01-T11, P01-T12, P01-T14
- **Unblocks:** P01-T15, P01-GATE
- **Deliverables:** CONTRIBUTING.md, PR template with DoD checklist, pre-commit config, commit conventions, branch strategy.
- **Acceptance criteria:**
  - Pre-commit runs format/lint hooks locally.
  - PR template lists CLAUDE.md Definition of Done.
- **Verification:** `pre-commit run --all-files`
- **Subtasks:** `P01-T13.1` CONTRIBUTING and PR template · `P01-T13.2` pre-commit hooks · `P01-T13.3` Branch/commit conventions

#### P01-T14 — OpenAPI export and contract-check tooling

`BE` · Size S · Wave P01.W5 · Approval: no

- **Objective:** Make API contract drift visible in CI.
- **Depends on:** P01-T07, P01-T09
- **Parallel with:** P01-T11, P01-T12, P01-T13
- **Unblocks:** P01-GATE
- **Deliverables:** scripts/export_openapi.py, committed openapi.json, Spectral lint, CI diff check.
- **Acceptance criteria:**
  - CI fails when the committed spec differs from the generated one.
  - Spectral lint passes.
- **Verification:** CK-API
- **Subtasks:** `P01-T14.1` Export script · `P01-T14.2` Spectral ruleset · `P01-T14.3` CI step

#### P01-T15 — Quality-gate CI integration and merge protection

`INF` · Size M · Wave P01.W6 · Approval: no

- **Objective:** Block merges on failed mandatory automated checks and make gate results visible (spec 8.4).
- **Depends on:** P01-T09, P01-T10, P01-T11, P01-T13
- **Parallel with:** — (sequential)
- **Unblocks:** P01-GATE
- **Deliverables:** Branch protection with required status checks and review rule, CODEOWNERS, coverage reporting, a CI job that runs `track.py validate` and `track.py qg require` for release workflows, ADR-0008 quality-gate policy.
- **Acceptance criteria:**
  - A PR with a failing mandatory check cannot be merged (demonstrated on a test PR).
  - Backend, mobile, security and tracker checks are required.
  - Coverage is reported per backend module.
- **Verification:** Test PR evidence; CK-TRK
- **Quality gates required before completion:** QG-02.3, QG-02.5, QG-03.6
- **Subtasks:** `P01-T15.1` Required checks and branch protection · `P01-T15.2` CODEOWNERS and review rule · `P01-T15.3` Coverage report · `P01-T15.4` Tracker validation job · `P01-T15.5` ADR-0008

#### P01-T16 — Define supported platforms and measurable quality targets

`DOC` · Size M · Wave P01.W3 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Fix the measurable thresholds that QG-04, QG-05 and QG-09 refer to (DEC-15, DEC-16, DEC-17).
- **Depends on:** P01-T03
- **Parallel with:** P01-T07, P01-T10
- **Unblocks:** P01-GATE
- **Deliverables:** docs/quality-targets.md: minimum Android API level and iOS versions/devices, app start-up time, memory and crash-rate targets, API p95/p99 SLOs, database query thresholds, coverage policy, AI evaluation approach.
- **Acceptance criteria:**
  - Every 'approved target' named in QUALITY_GATES.md maps to a number or a documented method.
  - User approves the targets.
- **Verification:** User approval.
- **Quality gates required before completion:** QG-04.3, QG-05.2
- **Subtasks:** `P01-T16.1` Platform support matrix · `P01-T16.2` Mobile performance targets · `P01-T16.3` API/database SLOs · `P01-T16.4` AI evaluation datasets and thresholds approach

#### P01-GATE — Phase P01 exit gate

`GATE` · Size S · Wave P01.W7 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Confirm the foundation meets its exit criteria.
- **Depends on:** P01-T01, P01-T02, P01-T03, P01-T04, P01-T05, P01-T06, P01-T07, P01-T08, P01-T09, P01-T10, P01-T11, P01-T12, P01-T13, P01-T14, P01-T15, P01-T16
- **Parallel with:** — (sequential)
- **Unblocks:** P02-T01, P02-T03, P04-T01, P06-T01, P14-T01, P14-T04
- **Deliverables:** Gate summary in EXECUTION_LOG.md.
- **Acceptance criteria:**
  - All P01 tasks COMPLETED with evidence.
  - Backend and mobile CI green on main.
  - User approval recorded.
- **Verification:** CK-B, CK-M, CK-S, CK-DB all green on main.
- **Quality gates required before completion:** QG-01.1, QG-01.2, QG-02.1, QG-02.2, QG-02.3, QG-02.4, QG-02.5, QG-02.6, QG-03.1, QG-03.6, QG-04.1, QG-04.2, QG-04.3, QG-05.1, QG-05.2, QG-08.3, QG-08.6, QG-10.1, QG-10.3
- **Subtasks:** `P01-GATE.1` Run all quality gates · `P01-GATE.2` Present summary · `P01-GATE.3` Record user approval

### P02 — Flutter Design System (UX Gate 1)

- **Goal:** Semantic tokens, light/dark themes, formatting primitives, the shared component library, charts and the navigation shell, reviewed in a gallery before any screen is built.
- **Entry criteria:** P01-T06 and P01-T10 complete; DEC-13 (chart library) confirmed.
- **Exit criteria:** Gallery reviewed against the concept board in both themes at 2.0 text scale; all component tests and goldens green.
- **Prerequisite phases:** P01 (P01-T06, P01-T10) · **Lane:** MOBILE
- **Entry gates:** prerequisite phase gates completed (P01); cumulative quality criteria QG-01.1–2; QG-02.1–6; QG-03.1,6; QG-04.1–3; QG-05.1–2; QG-08.3,6; QG-10.1,3; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** QG-01.5 (required by `P02-GATE`) plus user review.
- **Release gates:** —

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P02.W1 | P02-T01, P02-T03 | Parallel-safe | Phase approved and cross-phase prerequisites complete | T01 writes tokens/; T03 writes formatting/. Disjoint paths. |
| P02.W2 | P02-T02 | Single task | All dependencies from earlier waves of P02 complete | — |
| P02.W3 | P02-T04, P02-T07 | Parallel-safe | All dependencies from earlier waves of P02 complete | T04 writes components/status; T07 writes app/ and router. ARB files: append-only, feature-prefixed keys. |
| P02.W4 | P02-T05, P02-T06 | Parallel-safe | All dependencies from earlier waves of P02 complete | T05 writes components/; T06 writes charts/. Disjoint paths. |
| P02.W5 | P02-T08 | Single task | All dependencies from earlier waves of P02 complete | — |
| P02.W6 | P02-GATE | Single task | All dependencies from earlier waves of P02 complete | — |

#### P02-T01 — Design tokens with contrast and guard tests

`MOB` · Size M · Wave P02.W1 · Approval: no · Ref: UI plan Step 2

- **Objective:** Single source of truth for colour, spacing, radii, motion and breakpoints, with WCAG-safe semantic roles (D5).
- **Depends on:** P01-T06, P01-T10, P01-GATE
- **Parallel with:** P02-T03
- **Unblocks:** P02-T02, P02-GATE
- **Deliverables:** tokens/ (brand_palette, WealthColors ThemeExtension light/dark, spacing, radii, elevation, motion, breakpoints), contrast test, hard-coded-style guard test.
- **Acceptance criteria:**
  - Contrast >=4.5:1 for all text roles and >=3:1 for icons/chart strokes in both themes.
  - Guard test fails on Color(0x outside tokens/ and on left/right-specific insets/alignment.
- **Verification:** CK-M; `flutter test test/shared/design_system/tokens`
- **Subtasks:** `P02-T01.1` Brand palette incl. derived text-safe shades · `P02-T01.2` WealthColors light/dark · `P02-T01.3` Spacing/radii/motion/breakpoints · `P02-T01.4` Contrast test · `P02-T01.5` Guard test

#### P02-T02 — Themes, typography and theme-mode persistence

`MOB` · Size M · Wave P02.W2 · Approval: no · Ref: UI plan Step 3

- **Objective:** Complete Material 3 light/dark themes that feel native on Android and iOS.
- **Depends on:** P02-T01
- **Parallel with:** — (sequential)
- **Unblocks:** P02-T04, P02-T07, P02-GATE
- **Deliverables:** AppTheme.light/dark, component themes, typography scale with tabular figures, ThemeModeController with PreferencesStore.
- **Acceptance criteria:**
  - Runtime switch between system/light/dark persists across restarts.
  - All interactive controls meet 48dp minimum.
- **Verification:** CK-M
- **Subtasks:** `P02-T02.1` ThemeData builders · `P02-T02.2` Component themes · `P02-T02.3` Typography and tabular figures · `P02-T02.4` ThemeModeController and persistence · `P02-T02.5` Deterministic golden font

#### P02-T03 — Money model and formatting primitives

`MOB` · Size M · Wave P02.W1 · Approval: no · Ref: UI plan Step 4

- **Objective:** Decimal-based Money and locale-aware formatters with no binary floating point (D4, ADR-0003/0006).
- **Depends on:** P01-T06, P01-T03, P01-GATE
- **Parallel with:** P02-T01
- **Unblocks:** P02-T04, P02-GATE
- **Deliverables:** formatting/ (Money, MoneyFormatter incl. compact mode, PercentFormatter, date labels).
- **Acceptance criteria:**
  - Edge cases pass: values above 2^53, negatives, zero, .005 rounding, KES/AED/USD, compact thresholds.
  - No `double` conversion in formatting code.
- **Verification:** CK-M; `flutter test test/shared/design_system/formatting`
- **Subtasks:** `P02-T03.1` Money value object and JSON from string · `P02-T03.2` MoneyFormatter · `P02-T03.3` PercentFormatter and date labels · `P02-T03.4` Edge-case unit tests

#### P02-T04 — Status and state widgets

`MOB` · Size M · Wave P02.W3 · Approval: no · Ref: UI plan Step 4

- **Objective:** Reusable trust-labelling and async-state components.
- **Depends on:** P02-T02, P02-T03
- **Parallel with:** P02-T07
- **Unblocks:** P02-T05, P02-T06, P02-GATE
- **Deliverables:** CurrencyAmount, ChangeIndicator, RiskLabel, DisclosurePanel, DemoBadge/Banner, DataAsOfLabel, Stale/Offline banners, SkeletonLoader, EmptyState, ErrorState, AsyncValueView.
- **Acceptance criteria:**
  - No component overflows at 2.0 text scale, in RTL or in dark mode.
  - Gains/losses never rely on colour alone; semantics labels asserted.
- **Verification:** CK-M
- **Subtasks:** `P02-T04.1` Amount and change widgets · `P02-T04.2` Risk/Disclosure/Demo/DataAsOf · `P02-T04.3` Banners · `P02-T04.4` Skeleton/Empty/Error · `P02-T04.5` AsyncValueView · `P02-T04.6` Widget tests in light/dark/2.0x/RTL

#### P02-T05 — Composite components

`MOB` · Size L · Wave P02.W4 · Approval: no · Ref: UI plan Step 5

- **Objective:** Cards, selectors, rows and AI input used by the priority screens.
- **Depends on:** P02-T04
- **Parallel with:** P02-T06
- **Unblocks:** P02-T08, P02-GATE
- **Deliverables:** WealthSummaryCard, MetricCard, PeriodSelector, PortfolioSwitcher, InvestmentRow, ScenarioCard, EvidenceSourceChip, AIChatComposer.
- **Acceptance criteria:**
  - Each takes plain view-models and reads no provider.
  - Selection state is announced to screen readers and is not colour-only.
- **Verification:** CK-M
- **Subtasks:** `P02-T05.1` Summary and metric cards · `P02-T05.2` PeriodSelector and PortfolioSwitcher · `P02-T05.3` InvestmentRow and ScenarioCard · `P02-T05.4` EvidenceSourceChip · `P02-T05.5` AIChatComposer · `P02-T05.6` Interaction and semantics tests

#### P02-T06 — Accessible charts

`MOB` · Size L · Wave P02.W4 · Approval: no · Ref: UI plan Step 6

- **Objective:** Currency-aware, accessible charts on fl_chart.
- **Depends on:** P02-T04
- **Parallel with:** P02-T05
- **Unblocks:** P02-T08, P02-GATE
- **Deliverables:** charts/ (ChartSeries, ChartSemantics, PerformanceLineChart, AllocationDonutChart + legend, ForecastComparisonChart).
- **Acceptance criteria:**
  - Every chart exposes a text summary and a 'view as table' alternative.
  - Doubles appear only inside chart widgets.
  - Goldens exist for light and dark.
- **Verification:** CK-M, CK-G
- **Subtasks:** `P02-T06.1` Chart data model · `P02-T06.2` ChartSemantics · `P02-T06.3` Line chart · `P02-T06.4` Donut + legend · `P02-T06.5` Forecast comparison chart · `P02-T06.6` Goldens

#### P02-T07 — Navigation shell and WealthBottomNav

`MOB` · Size M · Wave P02.W3 · Approval: no · Ref: UI plan Step 7

- **Objective:** Five-tab shell with stable tab state and correct back behaviour (ADR-0002).
- **Depends on:** P02-T02
- **Parallel with:** P02-T04
- **Unblocks:** P02-T08, P02-GATE
- **Deliverables:** GoRouter StatefulShellRoute (Home, Portfolio, AI Wealth, Goals, More), AppRoutes, WealthBottomNav, per-feature route registration, contextual /ai?scope= parsing.
- **Acceptance criteria:**
  - Tab stacks persist; re-tap pops to root; Android back and iOS swipe-back behave correctly.
  - Route paths are not hard-coded in widgets.
- **Verification:** CK-M; manual back-navigation check on emulator
- **Subtasks:** `P02-T07.1` Router and route names · `P02-T07.2` WealthBottomNav · `P02-T07.3` Per-feature route registry contract · `P02-T07.4` Scope parsing · `P02-T07.5` Navigation tests

#### P02-T08 — Component gallery, goldens and design-system documentation

`MOB` · Size M · Wave P02.W5 · Approval: no · Ref: UI plan Step 8

- **Objective:** Make the design system reviewable.
- **Depends on:** P02-T05, P02-T06, P02-T07
- **Parallel with:** — (sequential)
- **Unblocks:** P02-GATE
- **Deliverables:** Debug-only /_gallery (theme, text-scale, RTL toggles), goldens at 1.0x and 2.0x, docs/design/design-system.md.
- **Acceptance criteria:**
  - Gallery is absent from release builds.
  - All components show loading/empty/error/data states.
- **Verification:** CK-M, CK-G; `flutter build apk --release` and confirm gallery route absent
- **Subtasks:** `P02-T08.1` Gallery screen · `P02-T08.2` Goldens · `P02-T08.3` design-system.md

#### P02-GATE — UX Gate 1 review

`GATE` · Size S · Wave P02.W6 · Approval: **USER REVIEW REQUIRED**

- **Objective:** User reviews the design system against the concept board.
- **Depends on:** P02-T01, P02-T02, P02-T03, P02-T04, P02-T05, P02-T06, P02-T07, P02-T08
- **Parallel with:** — (sequential)
- **Unblocks:** P03-T01, P04-T08
- **Deliverables:** Written approval or list of visual fixes.
- **Acceptance criteria:**
  - User approved visual language in both themes at 2.0 text scale.
  - CI green.
- **Verification:** User review of the gallery on device; CK-M, CK-G.
- **Quality gates required before completion:** QG-01.5
- **Subtasks:** `P02-GATE.1` Run gates · `P02-GATE.2` Demo gallery · `P02-GATE.3` Record approval

### P03 — Priority Screens with DEMO Data (UX Gate 2)

- **Goal:** High-fidelity Home, Portfolio Overview, Compounding Calculator, Wealth Forecast and AI Wealth Copilot on typed demo fixtures clearly labelled DEMO.
- **Entry criteria:** P02-GATE complete.
- **Exit criteria:** Five screens and five journeys pass on emulator with accessibility sweep clean; user approves gate 2.
- **Prerequisite phases:** P02 · **Lane:** MOBILE
- **Entry gates:** prerequisite phase gates completed (P02); cumulative quality criteria QG-01.1,2,5; QG-02.1–6; QG-03.1,6; QG-04.1–3; QG-05.1–2; QG-08.3,6; QG-10.1,3; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** QG-04.4; QG-05.3 (required by `P03-GATE`) plus user review.
- **Release gates:** —

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P03.W1 | P03-T01 | Single task | Phase approved and cross-phase prerequisites complete | — |
| P03.W2 | P03-T02, P03-T03, P03-T04, P03-T06 | Parallel-safe | All dependencies from earlier waves of P03 complete | T02/T03/T04/T06 each own a feature folder. Shared files (router registry, ARB, provider overrides) are append-only: each task adds its own route file and namespaced l10n keys; resolve merges at integration. |
| P03.W3 | P03-T05 | Single task | All dependencies from earlier waves of P03 complete | — |
| P03.W4 | P03-T07 | Single task | All dependencies from earlier waves of P03 complete | — |
| P03.W5 | P03-GATE | Single task | All dependencies from earlier waves of P03 complete | — |

#### P03-T01 — Demo data layer

`MOB` · Size L · Wave P03.W1 · Approval: no · Ref: UI plan Step 9

- **Objective:** Typed models, repository interfaces and DEMO fixtures mirroring the planned API.
- **Depends on:** P02-GATE
- **Parallel with:** — (sequential)
- **Unblocks:** P03-T02, P03-T03, P03-T04, P03-T06, P03-GATE, P05-T10
- **Deliverables:** Freezed DTOs (money as strings), repository interfaces, Demo* repositories with latency and failure injection, assets/demo/*.json (each with demo:true), dataSourceModeProvider.
- **Acceptance criteria:**
  - Every fixture parses and round-trips Decimal precision.
  - Failure injection works in tests.
- **Verification:** CK-M
- **Subtasks:** `P03-T01.1` Domain/DTO models · `P03-T01.2` Repository interfaces · `P03-T01.3` Demo implementations · `P03-T01.4` Multi-currency fixtures · `P03-T01.5` Scripted copilot fixtures · `P03-T01.6` Tests

#### P03-T02 — Home Dashboard (screen 3)

`MOB` · Size L · Wave P03.W2 · Approval: no · Ref: UI plan Step 10

- **Objective:** Total wealth, period chart, metric cards, AI insight, reorderable widgets.
- **Depends on:** P03-T01
- **Parallel with:** P03-T03, P03-T04, P03-T06
- **Unblocks:** P03-T07, P03-GATE
- **Deliverables:** features/dashboard/presentation + persistence of layout preferences.
- **Acceptance criteria:**
  - Layout customisation persists across restart and has non-drag reorder actions.
  - One failed section does not blank the screen.
- **Verification:** CK-M
- **Subtasks:** `P03-T02.1` Summary card and chart · `P03-T02.2` Metric cards · `P03-T02.3` Insight card with sources · `P03-T02.4` Customise mode · `P03-T02.5` Pull-to-refresh and states · `P03-T02.6` Tests

#### P03-T03 — Portfolio Overview (screen 4)

`MOB` · Size L · Wave P03.W2 · Approval: no · Ref: UI plan Step 11

- **Objective:** Portfolio switcher, value/P-L, line chart, allocation donut, metrics, holdings preview.
- **Depends on:** P03-T01
- **Parallel with:** P03-T02, P03-T04, P03-T06
- **Unblocks:** P03-T07, P03-GATE
- **Deliverables:** features/portfolios/presentation (overview).
- **Acceptance criteria:**
  - Switching portfolios (incl. consolidated) refreshes every section.
  - Empty and error states exist.
- **Verification:** CK-M
- **Subtasks:** `P03-T03.1` Switcher and header · `P03-T03.2` Chart and donut · `P03-T03.3` Metrics grid with definitions · `P03-T03.4` Holdings preview · `P03-T03.5` Contextual AI link · `P03-T03.6` Tests

#### P03-T04 — Compounding Calculator (screen 9)

`MOB` · Size L · Wave P03.W2 · Approval: no · Ref: UI plan Step 12

- **Objective:** Inputs, advanced options, validation and Calculate flow (DEC-03: canned results until P09-T03).
- **Depends on:** P03-T01
- **Parallel with:** P03-T02, P03-T03, P03-T06
- **Unblocks:** P03-T05, P03-GATE, P07-T07
- **Deliverables:** features/calculator/presentation (inputs).
- **Acceptance criteria:**
  - Invalid input cannot be submitted; validation limits live in one definition.
  - No compounding arithmetic exists in Dart.
- **Verification:** CK-M
- **Subtasks:** `P03-T04.1` Currency/percent inputs with locale decimals · `P03-T04.2` Advanced options · `P03-T04.3` ForecastInputLimits validation · `P03-T04.4` Calculate to ForecastRepository · `P03-T04.5` Keyboard handling · `P03-T04.6` Tests

#### P03-T05 — Wealth Forecast (screen 10)

`MOB` · Size L · Wave P03.W3 · Approval: no · Ref: UI plan Step 13

- **Objective:** Scenario cards, comparison chart, contributions vs growth, nominal/real toggle, assumptions disclosure.
- **Depends on:** P03-T04
- **Parallel with:** — (sequential)
- **Unblocks:** P03-T07, P03-GATE
- **Deliverables:** features/calculator/presentation/forecast.
- **Acceptance criteria:**
  - Every displayed number traces to a field of the response.
  - Assumptions and 'not guaranteed' disclosure are prominent.
- **Verification:** CK-M
- **Subtasks:** `P03-T05.1` Scenario cards and selection · `P03-T05.2` Comparison chart · `P03-T05.3` Contributions vs growth · `P03-T05.4` Nominal/real toggle · `P03-T05.5` Assumptions panel · `P03-T05.6` Tests

#### P03-T06 — AI Wealth Copilot (screen 6)

`MOB` · Size L · Wave P03.W2 · Approval: no · Ref: UI plan Step 14

- **Objective:** Conversation UI with scope chip, four-section answers, sources, streaming and refusal/retry (demo scripts).
- **Depends on:** P03-T01
- **Parallel with:** P03-T02, P03-T03, P03-T04
- **Unblocks:** P03-T07, P03-GATE, P10-T10
- **Deliverables:** features/ai_wealth/presentation.
- **Acceptance criteria:**
  - Scripted conversations incl. refusal and failure/retry play correctly.
  - No advice text is hard-coded in Dart; DEMO notice visible.
- **Verification:** CK-M
- **Subtasks:** `P03-T06.1` Empty state and suggestions · `P03-T06.2` Scope chip · `P03-T06.3` Four-section answer renderer · `P03-T06.4` Streaming and stop · `P03-T06.5` Refusal/failure/offline states · `P03-T06.6` Tests

#### P03-T07 — Journeys, accessibility sweep and device QA

`QA` · Size L · Wave P03.W4 · Approval: no · Ref: UI plan Step 15

- **Objective:** Prove the five screens as journeys.
- **Depends on:** P03-T02, P03-T03, P03-T05, P03-T06
- **Parallel with:** — (sequential)
- **Unblocks:** P03-GATE
- **Deliverables:** integration_test journeys 1-5, accessibility guideline tests, docs/design/qa-gate2.md.
- **Acceptance criteria:**
  - All five journeys pass on the emulator.
  - Tap-target, label and contrast guidelines pass in light/dark, 2.0x and RTL.
- **Verification:** CK-M, CK-I
- **Subtasks:** `P03-T07.1` Write journeys · `P03-T07.2` Accessibility sweep · `P03-T07.3` Manual QA checklist on devices

#### P03-GATE — UX Gate 2 review

`GATE` · Size S · Wave P03.W5 · Approval: **USER REVIEW REQUIRED**

- **Objective:** User reviews the five screens against the concept board on device.
- **Depends on:** P03-T01, P03-T02, P03-T03, P03-T04, P03-T05, P03-T06, P03-T07
- **Parallel with:** — (sequential)
- **Unblocks:** P07-T01, P09-T01
- **Deliverables:** Written approval or fix list.
- **Acceptance criteria:**
  - User approval recorded.
  - CI green on both jobs.
- **Verification:** User review on device; CK-M, CK-G, CK-I.
- **Quality gates required before completion:** QG-04.4, QG-05.3
- **Subtasks:** `P03-GATE.1` Run gates · `P03-GATE.2` Demo on device · `P03-GATE.3` Record approval

### P04 — Identity & Security Foundation

- **Goal:** Authenticated, authorised, audited and rate-limited platform with OIDC+PKCE mobile sign-in, MFA, biometric lock and the first auth screens.
- **Entry criteria:** P01-GATE complete; Keycloak available in the local stack.
- **Exit criteria:** No protected endpoint is reachable without a valid token; ownership/IDOR harness exists; mobile can sign in, refresh and lock.
- **Prerequisite phases:** P01 · **Lane:** BACKEND
- **Entry gates:** prerequisite phase gates completed (P01); cumulative quality criteria QG-01.1–2; QG-02.1–6; QG-03.1,6; QG-04.1–3; QG-05.1–2; QG-08.3,6; QG-10.1,3; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** QG-04.5; QG-05.4; QG-08.1 (required by `P04-GATE`) plus user review.
- **Release gates:** —

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P04.W1 | P04-T01 | Single task | Phase approved and cross-phase prerequisites complete | — |
| P04.W2 | P04-T02 | Single task | All dependencies from earlier waves of P04 complete | — |
| P04.W3 | P04-T03, P04-T04, P04-T05, P04-T06 | Parallel-safe | All dependencies from earlier waves of P04 complete | T03 writes authz/; T04 writes audit/; T05 writes middleware; T06 writes mobile/core. Disjoint paths. Only T02 adds a migration in P04-W2; T04 adds the audit migration in W3 (single owner per wave). |
| P04.W4 | P04-T07, P04-T08 | Parallel-safe | All dependencies from earlier waves of P04 complete | — |
| P04.W5 | P04-T09 | Single task | All dependencies from earlier waves of P04 complete | — |
| P04.W6 | P04-GATE | Single task | All dependencies from earlier waves of P04 complete | — |

#### P04-T01 — Keycloak realm and client configuration

`SEC` · Size M · Wave P04.W1 · Approval: no

- **Objective:** Dev realm with PKCE public mobile client, MFA (TOTP), email verification, password policy and test users.
- **Depends on:** P01-T05, P01-GATE
- **Parallel with:** — (sequential)
- **Unblocks:** P04-T02, P04-T06, P04-GATE, P14-T07
- **Deliverables:** infra/keycloak/realm-export.json (no secrets), setup notes.
- **Acceptance criteria:**
  - Authorization Code + PKCE succeeds; implicit/password grants disabled.
  - MFA enrolment works for a test user.
- **Verification:** Manual flow via curl/browser; `docker compose up` imports the realm.
- **Subtasks:** `P04-T01.1` Realm and roles · `P04-T01.2` Mobile public client (PKCE) · `P04-T01.3` MFA/email verification/policies · `P04-T01.4` Test users

#### P04-T02 — Backend authentication and user profile

`BE` · Size L · Wave P04.W2 · Approval: no

- **Objective:** Validate JWTs (JWKS), create the current-user dependency and the user/profile model.
- **Depends on:** P04-T01, P01-T08
- **Parallel with:** — (sequential)
- **Unblocks:** P04-T03, P04-T04, P04-T05, P04-T06, P04-GATE, P05-T01, P06-T02
- **Deliverables:** Auth dependency, /api/v1/me, PATCH /api/v1/me/preferences, users/user_profiles/risk_profiles tables and migration.
- **Acceptance criteria:**
  - Missing, expired, wrong-audience or tampered tokens return 401.
  - First login provisions the user idempotently.
- **Verification:** CK-B, CK-DB
- **Subtasks:** `P04-T02.1` JWKS validation with caching · `P04-T02.2` User provisioning · `P04-T02.3` Profile and preferences endpoints · `P04-T02.4` Migration · `P04-T02.5` Tests

#### P04-T03 — Authorization framework and IDOR test harness

`SEC` · Size M · Wave P04.W3 · Approval: no

- **Objective:** Reusable ownership checks and a cross-user test fixture used by every later module.
- **Depends on:** P04-T02
- **Parallel with:** P04-T04, P04-T05, P04-T06
- **Unblocks:** P04-T09, P04-GATE, P05-T03, P10-T02
- **Deliverables:** authz module, policy helpers, 404-vs-403 policy ADR, pytest fixtures with two users.
- **Acceptance criteria:**
  - Example resource proves user B cannot read/modify user A's data.
  - Harness is documented for reuse.
- **Verification:** CK-B
- **Subtasks:** `P04-T03.1` Ownership dependency · `P04-T03.2` Two-user fixtures · `P04-T03.3` Policy ADR · `P04-T03.4` Example IDOR tests

#### P04-T04 — Audit event infrastructure

`BE` · Size M · Wave P04.W3 · Approval: no

- **Objective:** Append-only audit events for financial changes and AI/tool activity.
- **Depends on:** P04-T02
- **Parallel with:** P04-T03, P04-T05, P04-T06
- **Unblocks:** P04-T09, P04-GATE, P05-T04, P10-T02
- **Deliverables:** audit_events table/migration, writer service, redaction, correlation ID linkage.
- **Acceptance criteria:**
  - Events are append-only (no update/delete path).
  - Sensitive fields are redacted.
- **Verification:** CK-B, CK-DB
- **Subtasks:** `P04-T04.1` Schema and migration · `P04-T04.2` Writer service · `P04-T04.3` Redaction · `P04-T04.4` Tests

#### P04-T05 — API protection

`SEC` · Size M · Wave P04.W3 · Approval: no

- **Objective:** Rate limiting, brute-force controls, input limits, CORS and security headers.
- **Depends on:** P04-T02
- **Parallel with:** P04-T03, P04-T04, P04-T06
- **Unblocks:** P04-T09, P04-GATE
- **Deliverables:** Redis-backed rate limiter, Keycloak brute-force settings, request size limits, headers middleware.
- **Acceptance criteria:**
  - Exceeding limits returns 429 with Retry-After.
  - Auth endpoints are stricter than general ones.
- **Verification:** CK-B; limiter tests
- **Subtasks:** `P04-T05.1` Rate limiter · `P04-T05.2` Keycloak brute-force · `P04-T05.3` Limits and headers · `P04-T05.4` Tests

#### P04-T06 — Mobile networking and authentication core

`MOB` · Size L · Wave P04.W3 · Approval: no

- **Objective:** Dio client, OIDC Authorization Code + PKCE, secure token storage, refresh rotation and logout.
- **Depends on:** P04-T01, P04-T02, P01-T06
- **Parallel with:** P04-T03, P04-T04, P04-T05
- **Unblocks:** P04-T07, P04-T08, P04-GATE, P09-T01, P09-T08
- **Deliverables:** core/network, core/auth, flutter_secure_storage, flutter_appauth (or equivalent), auth state provider.
- **Acceptance criteria:**
  - Tokens stored only in secure storage; never logged.
  - Expired access token refreshes transparently; refresh failure signs out.
- **Verification:** CK-M; emulator sign-in against the local stack
- **Subtasks:** `P04-T06.1` Add Dio/secure storage/appauth · `P04-T06.2` PKCE flow · `P04-T06.3` Token storage and refresh interceptor · `P04-T06.4` Logout · `P04-T06.5` Tests with fakes

#### P04-T07 — Biometric app lock and session policy

`MOB` · Size M · Wave P04.W4 · Approval: no

- **Objective:** Local authentication and automatic lock.
- **Depends on:** P04-T06
- **Parallel with:** P04-T08
- **Unblocks:** P04-T09, P04-GATE
- **Deliverables:** local_auth integration, lock on background/timeout, fallback rules, app-switcher privacy.
- **Acceptance criteria:**
  - App locks after the configured timeout and on resume.
  - Biometric failure falls back safely without bypassing auth.
- **Verification:** CK-M; device test with biometrics
- **Subtasks:** `P04-T07.1` local_auth integration · `P04-T07.2` Lock policy · `P04-T07.3` Privacy screen · `P04-T07.4` Tests

#### P04-T08 — Auth screens: Welcome/Onboarding and Sign In/Up

`MOB` · Size L · Wave P04.W4 · Approval: no

- **Objective:** Screens 1 and 2 including MFA, reset, validation and biometric entry.
- **Depends on:** P04-T06, P02-GATE
- **Parallel with:** P04-T07
- **Unblocks:** P04-GATE
- **Deliverables:** features/auth/presentation.
- **Acceptance criteria:**
  - Carousel has accessible skip; errors are understandable and non-leaking.
  - Widget tests cover validation and error states.
- **Verification:** CK-M, CK-G
- **Subtasks:** `P04-T08.1` Welcome/onboarding carousel · `P04-T08.2` Sign in/up and MFA flow · `P04-T08.3` Password reset entry · `P04-T08.4` Biometric prompt · `P04-T08.5` Tests

#### P04-T09 — Security test suite v1 and threat model

`SEC` · Size M · Wave P04.W5 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Automated and documented security baseline.
- **Depends on:** P04-T03, P04-T04, P04-T05, P04-T07
- **Parallel with:** — (sequential)
- **Unblocks:** P04-GATE, P10-T01
- **Deliverables:** IDOR/token-tamper/expiry/rate-limit tests in CI, docs/threat-model.md.
- **Acceptance criteria:**
  - All security tests run in CI.
  - Threat model covers mobile, API, identity and (planned) AI surfaces.
- **Verification:** CK-B, CK-S
- **Subtasks:** `P04-T09.1` Automated tests in CI · `P04-T09.2` Threat model · `P04-T09.3` Findings register

#### P04-GATE — Phase P04 exit gate

`GATE` · Size S · Wave P04.W6 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Confirm authentication and authorisation foundations.
- **Depends on:** P04-T01, P04-T02, P04-T03, P04-T04, P04-T05, P04-T06, P04-T07, P04-T08, P04-T09
- **Parallel with:** — (sequential)
- **Unblocks:** P05-T01, P09-T01, P10-T01
- **Deliverables:** Gate summary.
- **Acceptance criteria:**
  - All P04 tasks complete; user approval recorded.
- **Verification:** CK-B, CK-M, CK-S.
- **Quality gates required before completion:** QG-04.5, QG-05.4, QG-08.1
- **Subtasks:** `P04-GATE.1` Run gates · `P04-GATE.2` Present summary · `P04-GATE.3` Record approval

### P05 — Portfolio Core: Database & Backend

- **Goal:** Authoritative portfolio, asset, transaction, holding, valuation and multi-currency services with ownership enforcement.
- **Entry criteria:** P04-T02 and P04-T03 complete.
- **Exit criteria:** Portfolio summary endpoint is correct, tested and IDOR-safe; OpenAPI contract reconciled with mobile DTOs.
- **Prerequisite phases:** P04 · **Lane:** BACKEND
- **Entry gates:** prerequisite phase gates completed (P04); cumulative quality criteria QG-01.1–2; QG-02.1–6; QG-03.1,6; QG-04.1,2,3,5; QG-05.1,2,4; QG-08.1,3,6; QG-10.1,3; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** QG-01.3; QG-03.2; QG-06.2,5 (required by `P05-GATE`) plus user review.
- **Release gates:** —

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P05.W1 | P05-T01 | Single task | Phase approved and cross-phase prerequisites complete | — |
| P05.W2 | P05-T02, P05-T03, P05-T06 | Parallel-safe | All dependencies from earlier waves of P05 complete | T02, T03, T06 write separate modules. P05-T01 owns all P05 schema; later tasks add migrations only if unavoidable (single owner per wave). |
| P05.W3 | P05-T04 | Single task | All dependencies from earlier waves of P05 complete | — |
| P05.W4 | P05-T05, P05-T07 | Parallel-safe | All dependencies from earlier waves of P05 complete | T05 and T07 write separate modules. |
| P05.W5 | P05-T08 | Single task | All dependencies from earlier waves of P05 complete | — |
| P05.W6 | P05-T09, P05-T10 | Parallel-safe | All dependencies from earlier waves of P05 complete | — |
| P05.W7 | P05-GATE | Single task | All dependencies from earlier waves of P05 complete | — |

#### P05-T01 — Core schema and migrations

`DB` · Size L · Wave P05.W1 · Approval: **USER REVIEW REQUIRED**

- **Objective:** portfolios, portfolio_members, assets, asset_metadata, holdings, transactions, valuations, fx_rates with UUIDs, NUMERIC money, constraints and indexes.
- **Depends on:** P04-T02, P04-GATE
- **Parallel with:** — (sequential)
- **Unblocks:** P05-T02, P05-T03, P05-T06, P05-GATE, P08-T01, P08-T02
- **Deliverables:** SQLAlchemy models and Alembic revisions.
- **Acceptance criteria:**
  - All money/quantity columns are NUMERIC; every table has UUID PK and timestamps.
  - Upgrade/downgrade round-trips; single head.
- **Verification:** CK-DB, CK-B
- **Subtasks:** `P05-T01.1` Portfolio and member tables · `P05-T01.2` Asset and metadata tables · `P05-T01.3` Transactions/holdings/valuations · `P05-T01.4` FX table · `P05-T01.5` Constraints and indexes · `P05-T01.6` Schema tests

#### P05-T02 — Asset model and search API

`BE` · Size M · Wave P05.W2 · Approval: no

- **Objective:** Extensible asset classes with type-specific metadata and search.
- **Depends on:** P05-T01
- **Parallel with:** P05-T03, P05-T06
- **Unblocks:** P05-T04, P05-GATE
- **Deliverables:** Asset service, GET /assets/search, GET /assets/{id}, seed of asset classes (16 initial types).
- **Acceptance criteria:**
  - New asset class can be added without a schema redesign.
  - Request/response schemas are typed in OpenAPI.
- **Verification:** CK-B, CK-API
- **Subtasks:** `P05-T02.1` Service and repository · `P05-T02.2` Endpoints · `P05-T02.3` Seed data · `P05-T02.4` Tests

#### P05-T03 — Portfolio CRUD API

`BE` · Size M · Wave P05.W2 · Approval: no

- **Objective:** Create, list, read, update and archive portfolios with base currency and type.
- **Depends on:** P05-T01, P04-T03
- **Parallel with:** P05-T02, P05-T06
- **Unblocks:** P05-T04, P05-GATE
- **Deliverables:** Portfolio service and /api/v1/portfolios endpoints.
- **Acceptance criteria:**
  - Every endpoint enforces ownership; cross-user access is rejected.
  - Audit events written for create/update.
- **Verification:** CK-B, CK-API
- **Subtasks:** `P05-T03.1` Service and endpoints · `P05-T03.2` Ownership and audit · `P05-T03.3` Tests

#### P05-T04 — Transaction ledger API

`BE` · Size L · Wave P05.W3 · Approval: no

- **Objective:** Record all 14 transaction types append-only with corrections via reversing entries.
- **Depends on:** P05-T02, P05-T03, P04-T04
- **Parallel with:** — (sequential)
- **Unblocks:** P05-T05, P05-T07, P05-GATE, P06-T05
- **Deliverables:** POST/GET /portfolios/{id}/transactions, idempotency keys, reversal/adjustment endpoint.
- **Acceptance criteria:**
  - No update/delete of posted transactions; corrections create linked entries.
  - Duplicate idempotency key does not double-post.
  - Audit event per posting.
- **Verification:** CK-B, CK-DB
- **Subtasks:** `P05-T04.1` Ledger model and validation per type · `P05-T04.2` Idempotency · `P05-T04.3` Correction flow · `P05-T04.4` Audit · `P05-T04.5` Tests

#### P05-T05 — Holdings calculation service

`BE` · Size L · Wave P05.W4 · Approval: no

- **Objective:** Derive quantity, cost basis and realised/unrealised basis from the ledger.
- **Depends on:** P05-T04
- **Parallel with:** P05-T07
- **Unblocks:** P05-T08, P05-GATE, P06-T03, P06-T04
- **Deliverables:** Holdings service with documented cost-basis method and golden tests.
- **Acceptance criteria:**
  - Golden vectors for buys, partial sells, fees, splits-as-adjustments pass.
  - Decimal arithmetic only; rounding per ADR-0006.
- **Verification:** CK-B
- **Subtasks:** `P05-T05.1` Cost-basis method ADR · `P05-T05.2` Implementation · `P05-T05.3` Golden and property tests

#### P05-T06 — Multi-currency and FX conversion

`BE` · Size M · Wave P05.W2 · Approval: no

- **Objective:** Store transaction currency and FX, convert to base currency with timestamped rates.
- **Depends on:** P05-T01
- **Parallel with:** P05-T02, P05-T03
- **Unblocks:** P05-T08, P05-GATE, P06-T03, P06-T04
- **Deliverables:** FX service, rate-selection rules (historical vs latest), conversion tests.
- **Acceptance criteria:**
  - Original transaction currency and rate are preserved.
  - Conversion rounding is explicit and tested.
- **Verification:** CK-B
- **Subtasks:** `P05-T06.1` FX service · `P05-T06.2` Rate selection rules · `P05-T06.3` Rounding tests

#### P05-T07 — Manual valuations API

`BE` · Size M · Wave P05.W4 · Approval: no

- **Objective:** Valuations for non-market assets (property, private business, pension).
- **Depends on:** P05-T04
- **Parallel with:** P05-T05
- **Unblocks:** P05-T08, P05-GATE
- **Deliverables:** Valuation endpoints and service with as-of dates and source labels.
- **Acceptance criteria:**
  - Latest-as-of valuation is selected deterministically.
  - Valuation changes are audited.
- **Verification:** CK-B
- **Subtasks:** `P05-T07.1` Endpoints · `P05-T07.2` Selection logic · `P05-T07.3` Audit · `P05-T07.4` Tests

#### P05-T08 — Portfolio summary and consolidation endpoints

`BE` · Size L · Wave P05.W5 · Approval: no

- **Objective:** Server-authoritative totals, per-portfolio and consolidated, with data_as_of.
- **Depends on:** P05-T05, P05-T06, P05-T07
- **Parallel with:** — (sequential)
- **Unblocks:** P05-T09, P05-T10, P05-GATE, P06-T06, P06-T07, P08-T06, P09-T04
- **Deliverables:** GET /portfolios/{id}/summary and a consolidated summary endpoint.
- **Acceptance criteria:**
  - Totals reconcile with independently computed fixtures.
  - Response includes freshness metadata and currency breakdown.
- **Verification:** CK-B, CK-API
- **Subtasks:** `P05-T08.1` Service · `P05-T08.2` Endpoints · `P05-T08.3` Reconciliation tests

#### P05-T09 — Authorisation and integrity test suite

`SEC` · Size M · Wave P05.W6 · Approval: no

- **Objective:** Prove isolation and ledger integrity.
- **Depends on:** P05-T08
- **Parallel with:** P05-T10
- **Unblocks:** P05-GATE
- **Deliverables:** IDOR tests for every portfolio endpoint, ledger invariants, property-based tests.
- **Acceptance criteria:**
  - Every endpoint has a cross-user denial test.
  - Ledger invariants hold under random sequences.
- **Verification:** CK-B, CK-S
- **Subtasks:** `P05-T09.1` IDOR sweep · `P05-T09.2` Invariants · `P05-T09.3` Property tests

#### P05-T10 — OpenAPI contract and Dart DTO reconciliation

`BE` · Size M · Wave P05.W6 · Approval: no

- **Objective:** Align generated OpenAPI with the mobile Freezed DTOs created in P03-T01.
- **Depends on:** P05-T08, P03-T01
- **Parallel with:** P05-T09
- **Unblocks:** P05-GATE, P09-T01
- **Deliverables:** Published openapi.json, mapping document, decision on client generation.
- **Acceptance criteria:**
  - Differences between demo DTOs and API schemas are listed and resolved.
  - CI contract check passes.
- **Verification:** CK-API
- **Subtasks:** `P05-T10.1` Export spec · `P05-T10.2` Diff against DTOs · `P05-T10.3` Decide generation approach · `P05-T10.4` Update DTO plan

#### P05-GATE — Phase P05 exit gate

`GATE` · Size S · Wave P05.W7 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Confirm the portfolio core.
- **Depends on:** P05-T01, P05-T02, P05-T03, P05-T04, P05-T05, P05-T06, P05-T07, P05-T08, P05-T09, P05-T10
- **Parallel with:** — (sequential)
- **Unblocks:** P06-T03, P06-T04, P06-T05, P08-T01, P08-T02, P08-T04, P09-T01, P10-T01
- **Deliverables:** Gate summary.
- **Acceptance criteria:**
  - All tasks complete; user approval recorded.
- **Verification:** CK-B, CK-DB, CK-API, CK-S.
- **Quality gates required before completion:** QG-01.3, QG-03.2, QG-06.2, QG-06.5
- **Subtasks:** `P05-GATE.1` Run gates · `P05-GATE.2` Present summary · `P05-GATE.3` Record approval

### P06 — Analytics, Forecasting & Wealth Planning (Backend)

- **Goal:** Deterministic, tested financial engines: compound forecast, performance, allocation, income, goals, net worth and risk metrics.
- **Entry criteria:** P06 approved; P05 tasks as listed in each task's dependencies.
- **Exit criteria:** Independent recomputation confirms every formula; analytics APIs are authorised and cached.
- **Prerequisite phases:** P05 (P06-T01/T02 may start after P01-T07 once P06 is approved) · **Lane:** BACKEND
- **Entry gates:** prerequisite phase gates completed (P05); cumulative quality criteria QG-01.1–3; QG-02.1–6; QG-03.1,2,6; QG-04.1,2,3,5; QG-05.1,2,4; QG-06.2,5; QG-08.1,3,6; QG-10.1,3; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** QG-03.4–5; QG-06.1,3,4,6 (required by `P06-GATE`) plus user review.
- **Release gates:** —

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P06.W1 | P06-T01, P06-T03, P06-T04, P06-T05 | Parallel-safe | Phase approved and cross-phase prerequisites complete | T01 is pure code (no DB). T05 is the only migration in W1. T03/T04 are read-only analytics. |
| P06.W2 | P06-T02, P06-T06, P06-T08 | Parallel-safe | All dependencies from earlier waves of P06 complete | — |
| P06.W3 | P06-T07 | Single task | All dependencies from earlier waves of P06 complete | — |
| P06.W4 | P06-T09 | Single task | All dependencies from earlier waves of P06 complete | — |
| P06.W5 | P06-T10 | Single task | All dependencies from earlier waves of P06 complete | — |
| P06.W6 | P06-GATE | Single task | All dependencies from earlier waves of P06 complete | — |

#### P06-T01 — Compound forecast engine

`BE` · Size L · Wave P06.W1 · Approval: no

- **Objective:** Lump sum, recurring contributions (monthly/quarterly/annual), escalation, inflation, fees, scenarios, yearly series and required-contribution solver.
- **Depends on:** P01-T07, P01-T03, P01-GATE
- **Parallel with:** P06-T03, P06-T04, P06-T05
- **Unblocks:** P06-T02, P06-T06, P06-GATE
- **Deliverables:** Pure Python module with documented formulas and rounding.
- **Acceptance criteria:**
  - Golden tests: zero rate, negative rate, 50-year horizon, escalation, fees, inflation.
  - Property tests: monotonicity and contribution/growth decomposition.
  - No LLM or float money.
- **Verification:** CK-B; `pytest backend/tests/forecasting`
- **Subtasks:** `P06-T01.1` Formula doc · `P06-T01.2` Implementation · `P06-T01.3` Solver · `P06-T01.4` Golden tests · `P06-T01.5` Property tests

#### P06-T02 — Forecast API

`BE` · Size M · Wave P06.W2 · Approval: no

- **Objective:** Expose compound, scenario and goal forecasts with the same input limits as the mobile validation.
- **Depends on:** P06-T01, P04-T02
- **Parallel with:** P06-T06, P06-T08
- **Unblocks:** P06-T10, P06-GATE, P09-T03, P10-T04, P12-T07
- **Deliverables:** POST /forecasts/compound, /forecasts/scenarios, /forecasts/goal.
- **Acceptance criteria:**
  - Schemas validate limits and return nominal and real series.
  - Auth required; responses carry assumption echo.
- **Verification:** CK-B, CK-API
- **Subtasks:** `P06-T02.1` Schemas · `P06-T02.2` Endpoints · `P06-T02.3` Limits shared with mobile · `P06-T02.4` Tests

#### P06-T03 — Performance engine

`BE` · Size L · Wave P06.W1 · Approval: no

- **Objective:** Realised/unrealised P&L, return, CAGR, XIRR and time-weighted return.
- **Depends on:** P05-T05, P05-T06, P05-GATE
- **Parallel with:** P06-T01, P06-T04, P06-T05
- **Unblocks:** P06-T08, P06-T09, P06-GATE
- **Deliverables:** Performance service with golden vectors cross-checked against spreadsheet results.
- **Acceptance criteria:**
  - XIRR converges or fails explicitly; edge cases (single flow, zero) defined.
  - TWR handles external flows.
- **Verification:** CK-B
- **Subtasks:** `P06-T03.1` Return and CAGR · `P06-T03.2` XIRR · `P06-T03.3` TWR · `P06-T03.4` Golden and property tests

#### P06-T04 — Allocation and concentration analytics

`BE` · Size M · Wave P06.W1 · Approval: no

- **Objective:** Allocation by class, country, sector and currency; concentration measures.
- **Depends on:** P05-T05, P05-T06, P05-GATE
- **Parallel with:** P06-T01, P06-T03, P06-T05
- **Unblocks:** P06-T09, P06-GATE
- **Deliverables:** Allocation service with documented concentration metric (HHI, top-N).
- **Acceptance criteria:**
  - Weights sum to 100% within the documented rounding rule.
  - Sector/country sourced from asset metadata.
- **Verification:** CK-B
- **Subtasks:** `P06-T04.1` Allocation · `P06-T04.2` Concentration · `P06-T04.3` Tests

#### P06-T05 — Income and passive-income module

`BE` · Size M · Wave P06.W1 · Approval: no

- **Objective:** Dividends, interest, coupons, rent and distributions.
- **Depends on:** P05-T04, P05-GATE
- **Parallel with:** P06-T01, P06-T03, P06-T04
- **Unblocks:** P06-T09, P06-GATE
- **Deliverables:** income_events model/migration, service, summary by period/asset, yield.
- **Acceptance criteria:**
  - Monthly/annual totals and yield reconcile with fixtures.
  - Income is linked to ledger transactions.
- **Verification:** CK-B, CK-DB
- **Subtasks:** `P06-T05.1` Schema/migration · `P06-T05.2` Service · `P06-T05.3` Yield · `P06-T05.4` Tests

#### P06-T06 — Goals module

`BE` · Size L · Wave P06.W2 · Approval: no

- **Objective:** Goals with progress, gap, required contribution and on-track status under explicit assumptions.
- **Depends on:** P06-T01, P05-T08
- **Parallel with:** P06-T02, P06-T08
- **Unblocks:** P06-T07, P06-GATE
- **Deliverables:** goals/goal_scenarios schema, API, progress calculation using the forecast engine.
- **Acceptance criteria:**
  - Status is derived only from stated assumptions and is never presented as certain.
  - Ownership enforced.
- **Verification:** CK-B, CK-DB, CK-API
- **Subtasks:** `P06-T06.1` Schema/migration · `P06-T06.2` Service · `P06-T06.3` Endpoints · `P06-T06.4` Tests

#### P06-T07 — Net worth and liabilities

`BE` · Size M · Wave P06.W3 · Approval: no

- **Objective:** Assets minus liabilities including property and loans (sequenced after T06 to avoid concurrent Alembic revisions).
- **Depends on:** P06-T06, P05-T08
- **Parallel with:** — (sequential)
- **Unblocks:** P06-T09, P06-GATE
- **Deliverables:** liabilities schema, API, GET /net-worth.
- **Acceptance criteria:**
  - Net worth = total assets - total liabilities in base currency with FX provenance.
- **Verification:** CK-B, CK-DB
- **Subtasks:** `P06-T07.1` Schema/migration · `P06-T07.2` Service · `P06-T07.3` Endpoint · `P06-T07.4` Tests

#### P06-T08 — Risk metrics and historical series

`BE` · Size M · Wave P06.W2 · Approval: no

- **Objective:** Volatility, maximum drawdown and historical portfolio value.
- **Depends on:** P06-T03
- **Parallel with:** P06-T02, P06-T06
- **Unblocks:** P06-T09, P06-GATE
- **Deliverables:** Risk service and series builder.
- **Acceptance criteria:**
  - Methodology documented; insufficient data returns an explicit state.
- **Verification:** CK-B
- **Subtasks:** `P06-T08.1` Series builder · `P06-T08.2` Volatility · `P06-T08.3` Drawdown · `P06-T08.4` Tests

#### P06-T09 — Analytics API and caching

`BE` · Size L · Wave P06.W4 · Approval: no

- **Objective:** Expose performance, allocation, income, net-worth and dashboard aggregates with Redis caching.
- **Depends on:** P06-T03, P06-T04, P06-T05, P06-T07, P06-T08
- **Parallel with:** — (sequential)
- **Unblocks:** P06-T10, P06-GATE, P09-T02, P09-T05, P10-T03, P12-T01
- **Deliverables:** Endpoints per guide section 8, cache invalidation on ledger changes.
- **Acceptance criteria:**
  - Cache never serves another user's data; invalidated on ledger changes.
  - Schemas in OpenAPI.
- **Verification:** CK-B, CK-API, CK-S
- **Subtasks:** `P06-T09.1` Endpoints · `P06-T09.2` Cache keys and invalidation · `P06-T09.3` Authorisation tests

#### P06-T10 — Financial correctness review

`QA` · Size M · Wave P06.W5 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Independent recomputation of every formula.
- **Depends on:** P06-T09, P06-T02
- **Parallel with:** — (sequential)
- **Unblocks:** P06-GATE
- **Deliverables:** docs/financial-methods.md and cross-check workbook/test vectors.
- **Acceptance criteria:**
  - Each formula has a documented derivation and an independent check.
  - User reviews methods and rounding.
- **Verification:** CK-B; review document
- **Subtasks:** `P06-T10.1` Document formulas · `P06-T10.2` Independent vectors · `P06-T10.3` User review

#### P06-GATE — Phase P06 exit gate

`GATE` · Size S · Wave P06.W6 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Confirm financial engines.
- **Depends on:** P06-T01, P06-T02, P06-T03, P06-T04, P06-T05, P06-T06, P06-T07, P06-T08, P06-T09, P06-T10
- **Parallel with:** — (sequential)
- **Unblocks:** P09-T01, P10-T01
- **Deliverables:** Gate summary.
- **Acceptance criteria:**
  - All tasks complete; user approval recorded.
- **Verification:** CK-B, CK-DB, CK-API, CK-S.
- **Quality gates required before completion:** QG-03.4, QG-03.5, QG-06.1, QG-06.3, QG-06.4, QG-06.6
- **Subtasks:** `P06-GATE.1` Run gates · `P06-GATE.2` Present summary · `P06-GATE.3` Record approval

### P07 — Remaining Screens with DEMO Data (UX Gate 3)

- **Goal:** The remaining eight screens and deferred components, using demo fixtures.
- **Entry criteria:** P03-GATE complete.
- **Exit criteria:** All 13 screens exist with loading/empty/error states and journeys; user approves gate 3.
- **Prerequisite phases:** P03 · **Lane:** MOBILE
- **Entry gates:** prerequisite phase gates completed (P03); cumulative quality criteria QG-01.1,2,5; QG-02.1–6; QG-03.1,6; QG-04.1–4; QG-05.1–3; QG-08.3,6; QG-10.1,3; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** none (required by `P07-GATE`) plus user review.
- **Release gates:** —

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P07.W1 | P07-T01 | Single task | Phase approved and cross-phase prerequisites complete | — |
| P07.W2 | P07-T02, P07-T03, P07-T05, P07-T06, P07-T08 | Parallel-safe | All dependencies from earlier waves of P07 complete | Each screen owns its feature folder; shared registries are append-only. |
| P07.W3 | P07-T04, P07-T07 | Parallel-safe | All dependencies from earlier waves of P07 complete | — |
| P07.W4 | P07-T09 | Single task | All dependencies from earlier waves of P07 complete | — |
| P07.W5 | P07-GATE | Single task | All dependencies from earlier waves of P07 complete | — |

#### P07-T01 — Deferred shared components

`MOB` · Size M · Wave P07.W1 · Approval: no

- **Objective:** TransactionTile, GoalProgressCard, PortfolioHealthCard, OpportunityCard.
- **Depends on:** P03-GATE
- **Parallel with:** — (sequential)
- **Unblocks:** P07-T02, P07-T03, P07-T05, P07-T06, P07-T07, P07-T08, P07-GATE
- **Deliverables:** Components with tests and gallery entries.
- **Acceptance criteria:**
  - Opportunity cards show risk, evidence, data-as-of and score explanation slots.
  - Progress rings have numeric labels and text status.
- **Verification:** CK-M, CK-G
- **Subtasks:** `P07-T01.1` Four components · `P07-T01.2` Gallery entries · `P07-T01.3` Tests and goldens

#### P07-T02 — Investments / Holdings (screen 5)

`MOB` · Size M · Wave P07.W2 · Approval: no

- **Objective:** Search, asset-class chips, sortable holdings with native and converted values.
- **Depends on:** P07-T01
- **Parallel with:** P07-T03, P07-T05, P07-T06, P07-T08
- **Unblocks:** P07-T04, P07-T09, P07-GATE
- **Deliverables:** features/portfolios/holdings.
- **Acceptance criteria:**
  - Sorting/filtering are announced to screen readers.
  - Native and converted amounts shown.
- **Verification:** CK-M
- **Subtasks:** `P07-T02.1` Screen · `P07-T02.2` Search/filter/sort · `P07-T02.3` Tests

#### P07-T03 — Transactions (screen 8) and add-transaction flow

`MOB` · Size L · Wave P07.W2 · Approval: no

- **Objective:** Filter chips, grouped activity, add flow, confirmation and correction audit trail UI.
- **Depends on:** P07-T01
- **Parallel with:** P07-T02, P07-T05, P07-T06, P07-T08
- **Unblocks:** P07-T09, P07-GATE
- **Deliverables:** features/transactions.
- **Acceptance criteria:**
  - Corrections appear as linked entries, not edits.
  - Validation errors are inline and human-readable.
- **Verification:** CK-M
- **Subtasks:** `P07-T03.1` List and filters · `P07-T03.2` Add flow · `P07-T03.3` Confirmation · `P07-T03.4` Correction view · `P07-T03.5` Tests

#### P07-T04 — Investment Details (screen 7)

`MOB` · Size M · Wave P07.W3 · Approval: no

- **Objective:** Latest value, chart, fundamentals, income, holdings, transactions, research, watchlist action.
- **Depends on:** P07-T02
- **Parallel with:** P07-T07
- **Unblocks:** P07-T09, P07-GATE
- **Deliverables:** features/investments/detail.
- **Acceptance criteria:**
  - No Buy/Sell execution affordance (D6).
  - Sources and as-of times shown.
- **Verification:** CK-M
- **Subtasks:** `P07-T04.1` Header and chart · `P07-T04.2` Tabs · `P07-T04.3` Watchlist action · `P07-T04.4` Tests

#### P07-T05 — Financial Goals (screen 11)

`MOB` · Size L · Wave P07.W2 · Approval: no

- **Objective:** Goal cards, progress rings, on-track status, add/edit goal, required contribution.
- **Depends on:** P07-T01
- **Parallel with:** P07-T02, P07-T03, P07-T06, P07-T08
- **Unblocks:** P07-T09, P07-GATE
- **Deliverables:** features/goals.
- **Acceptance criteria:**
  - Status labelled as assumption-based.
  - Add/edit validation is covered by tests.
- **Verification:** CK-M
- **Subtasks:** `P07-T05.1` Goal list · `P07-T05.2` Add/edit · `P07-T05.3` Required contribution display · `P07-T05.4` Tests

#### P07-T06 — Portfolio Doctor (screen 12)

`MOB` · Size M · Wave P07.W2 · Approval: no

- **Objective:** Health overview and findings with severity, explanation and scenario actions (DEMO).
- **Depends on:** P07-T01
- **Parallel with:** P07-T02, P07-T03, P07-T05, P07-T08
- **Unblocks:** P07-T09, P07-GATE, P12-T09
- **Deliverables:** features/ai_wealth/doctor.
- **Acceptance criteria:**
  - Findings carry severity text, not colour only.
  - No automatic trade actions.
- **Verification:** CK-M
- **Subtasks:** `P07-T06.1` Overview · `P07-T06.2` Findings tabs · `P07-T06.3` Scenario actions · `P07-T06.4` Tests

#### P07-T07 — AI Investment Opportunities (screen 13)

`MOB` · Size L · Wave P07.W3 · Approval: no

- **Objective:** Category chips, candidate cards, evidence, risk, data-as-of, Compare/Research/Simulate (DEMO).
- **Depends on:** P07-T01, P03-T04
- **Parallel with:** P07-T04
- **Unblocks:** P07-T09, P07-GATE, P12-T09
- **Deliverables:** features/ai_wealth/opportunities.
- **Acceptance criteria:**
  - Simulate pre-fills the calculator with marked assumptions.
  - DEMO opportunities never imply live data.
- **Verification:** CK-M
- **Subtasks:** `P07-T07.1` List and chips · `P07-T07.2` Research sheet · `P07-T07.3` Compare view · `P07-T07.4` Simulate hand-off · `P07-T07.5` Tests

#### P07-T08 — More hub, Net Worth, Income and Settings

`MOB` · Size M · Wave P07.W2 · Approval: no

- **Objective:** More tab content: net worth, income, settings (theme), placeholders for reports/alerts/documents.
- **Depends on:** P07-T01
- **Parallel with:** P07-T02, P07-T03, P07-T05, P07-T06
- **Unblocks:** P07-T09, P07-GATE
- **Deliverables:** features/more.
- **Acceptance criteria:**
  - Unavailable items are labelled 'Coming soon'.
- **Verification:** CK-M
- **Subtasks:** `P07-T08.1` More list · `P07-T08.2` Net worth and income views · `P07-T08.3` Settings · `P07-T08.4` Tests

#### P07-T09 — Journeys and accessibility sweep (gate 3)

`QA` · Size M · Wave P07.W4 · Approval: no

- **Objective:** Extend journeys and accessibility checks to all 13 screens.
- **Depends on:** P07-T02, P07-T03, P07-T04, P07-T05, P07-T06, P07-T07, P07-T08
- **Parallel with:** — (sequential)
- **Unblocks:** P07-GATE
- **Deliverables:** Additional integration tests and updated QA checklist.
- **Acceptance criteria:**
  - All journeys pass; guideline tests clean.
- **Verification:** CK-M, CK-G, CK-I
- **Subtasks:** `P07-T09.1` Journeys · `P07-T09.2` Accessibility sweep · `P07-T09.3` QA checklist

#### P07-GATE — UX Gate 3 review

`GATE` · Size S · Wave P07.W5 · Approval: **USER REVIEW REQUIRED**

- **Objective:** User reviews all 13 screens.
- **Depends on:** P07-T01, P07-T02, P07-T03, P07-T04, P07-T05, P07-T06, P07-T07, P07-T08, P07-T09
- **Parallel with:** — (sequential)
- **Unblocks:** P09-T01
- **Deliverables:** Gate summary.
- **Acceptance criteria:**
  - User approval recorded.
- **Verification:** CK-M, CK-G, CK-I.
- **Subtasks:** `P07-GATE.1` Run gates · `P07-GATE.2` Demo · `P07-GATE.3` Record approval

### P08 — Market Data & Research Integration (Backend)

- **Goal:** Provider-abstracted prices, FX, history and research with provenance, freshness, caching, workers, watchlists and alerts.
- **Entry criteria:** P05 complete; DEC-04 (providers/licensing) decided in P08-T01.
- **Exit criteria:** Valuations use timestamped market data with freshness flags; provider outages degrade gracefully.
- **Prerequisite phases:** P05 · **Lane:** BACKEND
- **Entry gates:** prerequisite phase gates completed (P05); cumulative quality criteria QG-01.1–3; QG-02.1–6; QG-03.1,2,6; QG-04.1,2,3,5; QG-05.1,2,4; QG-06.2,5; QG-08.1,3,6; QG-10.1,3; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** QG-06.7; QG-09.5; QG-11.4 (required by `P08-GATE`) plus user review.
- **Release gates:** —

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P08.W1 | P08-T01, P08-T02, P08-T04 | Parallel-safe | Phase approved and cross-phase prerequisites complete | T01 is a decision doc; T02 interface+fake provider; T04 worker infrastructure. Disjoint paths. |
| P08.W2 | P08-T03 | Single task | All dependencies from earlier waves of P08 complete | — |
| P08.W3 | P08-T05 | Single task | All dependencies from earlier waves of P08 complete | — |
| P08.W4 | P08-T06, P08-T07 | Parallel-safe | All dependencies from earlier waves of P08 complete | — |
| P08.W5 | P08-T08, P08-T09 | Parallel-safe | All dependencies from earlier waves of P08 complete | — |
| P08.W6 | P08-GATE | Single task | All dependencies from earlier waves of P08 complete | — |

#### P08-T01 — Provider selection and licensing decision

`DOC` · Size S · Wave P08.W1 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Evaluate providers for equities/ETFs, crypto, FX, bonds, macro and research; confirm licence terms and cost.
- **Depends on:** P05-T01, P05-GATE
- **Parallel with:** P08-T02, P08-T04
- **Unblocks:** P08-T03, P08-GATE
- **Deliverables:** ADR and comparison matrix.
- **Acceptance criteria:**
  - Licence permits the intended in-app display and storage.
  - User selects providers (DEC-04).
- **Verification:** User approval of ADR.
- **Subtasks:** `P08-T01.1` Requirements matrix · `P08-T01.2` Candidate evaluation · `P08-T01.3` ADR

#### P08-T02 — Provider abstraction layer

`BE` · Size L · Wave P08.W1 · Approval: no

- **Objective:** Interfaces, retry/circuit-breaker policy, provenance model and a deterministic fake provider.
- **Depends on:** P05-T01, P05-GATE
- **Parallel with:** P08-T01, P08-T04
- **Unblocks:** P08-T03, P08-GATE
- **Deliverables:** market_data module with fake provider and contract-test base.
- **Acceptance criteria:**
  - All consumers use the interface only.
  - Fake provider supports staleness/outage simulation.
- **Verification:** CK-B
- **Subtasks:** `P08-T02.1` Interfaces · `P08-T02.2` Resilience policy · `P08-T02.3` Provenance model · `P08-T02.4` Fake provider

#### P08-T03 — Provider adapters and contract tests

`BE` · Size L · Wave P08.W2 · Approval: no

- **Objective:** Implement the selected adapters with recorded-fixture contract tests.
- **Depends on:** P08-T01, P08-T02
- **Parallel with:** — (sequential)
- **Unblocks:** P08-T05, P08-T09, P08-GATE
- **Deliverables:** Adapters, secrets via environment/secret manager, rate-limit handling.
- **Acceptance criteria:**
  - API keys are not in source or logs.
  - Contract tests pass offline using recorded fixtures.
- **Verification:** CK-B, CK-S
- **Subtasks:** `P08-T03.1` Adapters · `P08-T03.2` Fixtures · `P08-T03.3` Rate limiting · `P08-T03.4` Secrets handling

#### P08-T04 — Async job infrastructure

`BE` · Size M · Wave P08.W1 · Approval: no

- **Objective:** Celery workers on RabbitMQ with schedules, idempotent jobs, dead-letter and Redis cache.
- **Depends on:** P01-T05, P01-T07, P05-GATE
- **Parallel with:** P08-T01, P08-T02
- **Unblocks:** P08-T05, P08-GATE
- **Deliverables:** worker module, beat schedule, job base class, docs.
- **Acceptance criteria:**
  - Re-running a job does not duplicate data.
  - Failed jobs land in a dead-letter queue and are visible.
- **Verification:** CK-B; local worker run
- **Subtasks:** `P08-T04.1` Worker setup · `P08-T04.2` Idempotency helper · `P08-T04.3` Dead-letter · `P08-T04.4` Tests

#### P08-T05 — Price and FX ingestion

`BE` · Size L · Wave P08.W3 · Approval: no

- **Objective:** Populate market_prices and fx_rates incl. historical backfill with freshness metadata.
- **Depends on:** P08-T03, P08-T04
- **Parallel with:** — (sequential)
- **Unblocks:** P08-T06, P08-T07, P08-T08, P08-GATE
- **Deliverables:** Ingestion jobs, migrations if needed, staleness flags.
- **Acceptance criteria:**
  - Every stored price has provider, as-of and ingestion timestamps.
  - Backfill is idempotent.
- **Verification:** CK-B, CK-DB
- **Subtasks:** `P08-T05.1` market_prices schema · `P08-T05.2` Ingestion jobs · `P08-T05.3` Backfill · `P08-T05.4` Tests

#### P08-T06 — Automatic valuation integration

`BE` · Size M · Wave P08.W4 · Approval: no

- **Objective:** Value holdings from latest prices with fallback to manual valuations and stale flags.
- **Depends on:** P08-T05, P05-T08
- **Parallel with:** P08-T07
- **Unblocks:** P08-T08, P08-GATE, P09-T07, P12-T02, P12-T03
- **Deliverables:** Valuation service updates and summary API freshness fields.
- **Acceptance criteria:**
  - Summary shows data_as_of and stale indicator per holding.
- **Verification:** CK-B
- **Subtasks:** `P08-T06.1` Service update · `P08-T06.2` Fallback rules · `P08-T06.3` API fields · `P08-T06.4` Tests

#### P08-T07 — Watchlists and alerts backend

`BE` · Size L · Wave P08.W4 · Approval: no

- **Objective:** Watchlists, target-price and allocation alerts, evaluation job.
- **Depends on:** P08-T05
- **Parallel with:** P08-T06
- **Unblocks:** P08-GATE, P09-T07
- **Deliverables:** Schema/migration, endpoints, alert evaluation worker.
- **Acceptance criteria:**
  - Alerts are evaluated idempotently and respect preferences.
  - Ownership enforced.
- **Verification:** CK-B, CK-DB, CK-API
- **Subtasks:** `P08-T07.1` Schema · `P08-T07.2` Endpoints · `P08-T07.3` Evaluator · `P08-T07.4` Tests

#### P08-T08 — Failover, caching and degradation tests

`QA` · Size M · Wave P08.W5 · Approval: no

- **Objective:** Prove behaviour under outage, stale data and rate limits.
- **Depends on:** P08-T05, P08-T06
- **Parallel with:** P08-T09
- **Unblocks:** P08-GATE
- **Deliverables:** Chaos-style tests with the fake provider.
- **Acceptance criteria:**
  - Outage yields stale-flagged values, not errors or silent wrong data.
- **Verification:** CK-B
- **Subtasks:** `P08-T08.1` Outage tests · `P08-T08.2` Stale tests · `P08-T08.3` Cache tests

#### P08-T09 — Market data security and compliance review

`SEC` · Size S · Wave P08.W5 · Approval: no

- **Objective:** Check key custody, redistribution terms and logging.
- **Depends on:** P08-T03
- **Parallel with:** P08-T08
- **Unblocks:** P08-GATE, P12-T05
- **Deliverables:** Review notes in docs/security.md.
- **Acceptance criteria:**
  - No provider terms violated; no keys in logs.
- **Verification:** CK-S; manual review.
- **Subtasks:** `P08-T09.1` Key custody · `P08-T09.2` Terms check · `P08-T09.3` Log review

#### P08-GATE — Phase P08 exit gate

`GATE` · Size S · Wave P08.W6 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Confirm market data.
- **Depends on:** P08-T01, P08-T02, P08-T03, P08-T04, P08-T05, P08-T06, P08-T07, P08-T08, P08-T09
- **Parallel with:** — (sequential)
- **Unblocks:** P09-T01, P12-T01, P12-T02
- **Deliverables:** Gate summary.
- **Acceptance criteria:**
  - User approval recorded.
- **Verification:** CK-B, CK-DB, CK-API, CK-S.
- **Quality gates required before completion:** QG-06.7, QG-09.5, QG-11.4
- **Subtasks:** `P08-GATE.1` Run gates · `P08-GATE.2` Present summary · `P08-GATE.3` Record approval

### P09 — Mobile-Backend Integration (UX Gate 4)

- **Goal:** Replace demo repositories with live ones, add offline/stale handling, notifications and end-to-end tests against the full stack.
- **Entry criteria:** Required backend phases and P07-GATE complete; DEC-08 (push) and DEC-12 (offline store) decided.
- **Exit criteria:** All 13 screens run on live data; DEMO appears only where data is still demo; E2E suite green.
- **Prerequisite phases:** P03, P04, P05, P06, P07, P08 · **Lane:** INTEGRATION
- **Entry gates:** prerequisite phase gates completed (P03, P04, P05, P06, P07, P08); cumulative quality criteria QG-01.1,2,3,5; QG-02.1–6; QG-03.1,2,4,5,6; QG-04.1–5; QG-05.1–4; QG-06.1–7; QG-08.1,3,6; QG-09.5; QG-10.1,3; QG-11.4; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** QG-03.3; QG-11.1,2,5,6 (required by `P09-GATE`) plus user review.
- **Release gates:** —

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P09.W1 | P09-T01 | Single task | Phase approved and cross-phase prerequisites complete | — |
| P09.W2 | P09-T02, P09-T03, P09-T04, P09-T05 | Parallel-safe | All dependencies from earlier waves of P09 complete | Each task owns a feature's live repository file; the provider-override registry is append-only. |
| P09.W3 | P09-T06, P09-T07, P09-T08 | Parallel-safe | All dependencies from earlier waves of P09 complete | — |
| P09.W4 | P09-T09 | Single task | All dependencies from earlier waves of P09 complete | — |
| P09.W5 | P09-T10 | Single task | All dependencies from earlier waves of P09 complete | — |
| P09.W6 | P09-GATE | Single task | All dependencies from earlier waves of P09 complete | — |

#### P09-T01 — API client and live-repository framework

`MOB` · Size L · Wave P09.W1 · Approval: no

- **Objective:** Typed API client, error mapping, auth interceptors and data-source switch.
- **Depends on:** P04-T06, P05-T10, P03-GATE, P04-GATE, P05-GATE, P06-GATE, P07-GATE, P08-GATE
- **Parallel with:** — (sequential)
- **Unblocks:** P09-T02, P09-T03, P09-T04, P09-T05, P09-T08, P09-GATE, P10-T10
- **Deliverables:** core/api, DTO generation or hand-written DTOs per P05-T10, LiveRepository base.
- **Acceptance criteria:**
  - Errors map to ErrorState/Offline states.
  - Switching data-source mode needs no screen change.
- **Verification:** CK-M
- **Subtasks:** `P09-T01.1` Client · `P09-T01.2` Error mapping · `P09-T01.3` Mode switch · `P09-T01.4` Tests

#### P09-T02 — Live dashboard and portfolio repositories

`MOB` · Size L · Wave P09.W2 · Approval: no

- **Objective:** Wire Home and Portfolio to backend; sync dashboard layout via preferences.
- **Depends on:** P09-T01, P06-T09
- **Parallel with:** P09-T03, P09-T04, P09-T05
- **Unblocks:** P09-T06, P09-T09, P09-GATE
- **Deliverables:** Live repositories and tests.
- **Acceptance criteria:**
  - Numbers match backend responses; no client-side recalculation.
- **Verification:** CK-M, CK-I
- **Subtasks:** `P09-T02.1` Dashboard repo · `P09-T02.2` Portfolio repo · `P09-T02.3` Preferences sync · `P09-T02.4` Tests

#### P09-T03 — Live calculator and forecast repository

`MOB` · Size M · Wave P09.W2 · Approval: no

- **Objective:** Replace canned forecast results with the real engine (resolves DEC-03).
- **Depends on:** P09-T01, P06-T02
- **Parallel with:** P09-T02, P09-T04, P09-T05
- **Unblocks:** P09-T09, P09-GATE
- **Deliverables:** LiveForecastRepository.
- **Acceptance criteria:**
  - Any valid input returns a real projection; DEMO notice removed.
- **Verification:** CK-M, CK-I
- **Subtasks:** `P09-T03.1` Repository · `P09-T03.2` Remove demo-only notice · `P09-T03.3` Tests

#### P09-T04 — Live holdings, transactions and investment details

`MOB` · Size L · Wave P09.W2 · Approval: no

- **Objective:** Wire holdings/transactions/detail and submit new transactions.
- **Depends on:** P09-T01, P05-T08
- **Parallel with:** P09-T02, P09-T03, P09-T05
- **Unblocks:** P09-T06, P09-T07, P09-T09, P09-GATE
- **Deliverables:** Live repositories.
- **Acceptance criteria:**
  - Submitting a transaction updates summaries; corrections are linked entries.
- **Verification:** CK-M, CK-I
- **Subtasks:** `P09-T04.1` Holdings · `P09-T04.2` Transactions incl. submit · `P09-T04.3` Detail · `P09-T04.4` Tests

#### P09-T05 — Live goals, net worth and income

`MOB` · Size L · Wave P09.W2 · Approval: no

- **Objective:** Wire Goals, Net Worth and Income.
- **Depends on:** P09-T01, P06-T09
- **Parallel with:** P09-T02, P09-T03, P09-T04
- **Unblocks:** P09-T09, P09-GATE
- **Deliverables:** Live repositories.
- **Acceptance criteria:**
  - Goal status shows assumption disclosure from the API.
- **Verification:** CK-M, CK-I
- **Subtasks:** `P09-T05.1` Goals · `P09-T05.2` Net worth · `P09-T05.3` Income · `P09-T05.4` Tests

#### P09-T06 — Offline, stale-data and error handling

`MOB` · Size L · Wave P09.W3 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Connectivity awareness, encrypted last-good cache (DEC-12), retries and banners.
- **Depends on:** P09-T02, P09-T04
- **Parallel with:** P09-T07, P09-T08
- **Unblocks:** P09-GATE
- **Deliverables:** Cache layer and banners.
- **Acceptance criteria:**
  - Offline shows last-good data with stale banner; no cross-user cache leakage after logout.
- **Verification:** CK-M, CK-I
- **Subtasks:** `P09-T06.1` Cache design · `P09-T06.2` Connectivity · `P09-T06.3` Banners · `P09-T06.4` Logout wipe · `P09-T06.5` Tests

#### P09-T07 — Live market-data surfaces

`MOB` · Size L · Wave P09.W3 · Approval: no

- **Objective:** Live prices, charts, watchlist and alerts with freshness labels.
- **Depends on:** P09-T04, P08-T06, P08-T07
- **Parallel with:** P09-T06, P09-T08
- **Unblocks:** P09-T09, P09-GATE
- **Deliverables:** Mobile wiring.
- **Acceptance criteria:**
  - Stale/missing data is labelled; no invented prices.
- **Verification:** CK-M, CK-I
- **Subtasks:** `P09-T07.1` Prices/charts · `P09-T07.2` Watchlist · `P09-T07.3` Alerts · `P09-T07.4` Tests

#### P09-T08 — Push notifications and deep links

`MOB` · Size L · Wave P09.W3 · Approval: no

- **Objective:** FCM/APNs integration, notification preferences and deep-link routing.
- **Depends on:** P09-T01, P04-T06
- **Parallel with:** P09-T06, P09-T07
- **Unblocks:** P09-T10, P09-GATE
- **Deliverables:** Notification service module and mobile handling.
- **Acceptance criteria:**
  - Deep link opens the correct route after authentication.
  - Payloads contain no sensitive amounts.
- **Verification:** CK-M, CK-B
- **Subtasks:** `P09-T08.1` Backend module · `P09-T08.2` Mobile handling · `P09-T08.3` Preferences · `P09-T08.4` Tests

#### P09-T09 — DEMO retirement and data-source governance

`MOB` · Size S · Wave P09.W4 · Approval: no

- **Objective:** Ensure DEMO labelling reflects actual data source; release builds cannot select demo mode.
- **Depends on:** P09-T02, P09-T03, P09-T04, P09-T05, P09-T07
- **Parallel with:** — (sequential)
- **Unblocks:** P09-T10, P09-GATE
- **Deliverables:** Mode policy, tests.
- **Acceptance criteria:**
  - Release build refuses demo mode.
- **Verification:** CK-M
- **Subtasks:** `P09-T09.1` Policy · `P09-T09.2` Tests

#### P09-T10 — End-to-end tests against the Docker stack

`QA` · Size L · Wave P09.W5 · Approval: no

- **Objective:** Run key journeys against a seeded backend.
- **Depends on:** P09-T09, P09-T08
- **Parallel with:** — (sequential)
- **Unblocks:** P09-GATE
- **Deliverables:** E2E suite and CI job.
- **Acceptance criteria:**
  - Journeys pass: sign in, view portfolio, add transaction, forecast, goal progress, notification deep link.
- **Verification:** CK-I, CK-B
- **Subtasks:** `P09-T10.1` Seed data · `P09-T10.2` Journeys · `P09-T10.3` CI job

#### P09-GATE — UX Gate 4 review

`GATE` · Size S · Wave P09.W6 · Approval: **USER REVIEW REQUIRED**

- **Objective:** User verifies live behaviour on device.
- **Depends on:** P09-T01, P09-T02, P09-T03, P09-T04, P09-T05, P09-T06, P09-T07, P09-T08, P09-T09, P09-T10
- **Parallel with:** — (sequential)
- **Unblocks:** P15-T01, P15-T02, P15-T04, P15-T05, P15-T06
- **Deliverables:** Gate summary.
- **Acceptance criteria:**
  - User approval recorded.
- **Verification:** CK-M, CK-I, CK-B.
- **Quality gates required before completion:** QG-03.3, QG-11.1, QG-11.2, QG-11.5, QG-11.6
- **Subtasks:** `P09-GATE.1` Run gates · `P09-GATE.2` Demo on device · `P09-GATE.3` Record approval

### P10 — AI Tool Layer & Wealth Copilot

- **Goal:** Secure allow-listed tool layer, provider abstraction, orchestrator and the live AI Wealth Copilot.
- **Entry criteria:** P04-T09, P06-T09 and P06-T02 complete; DEC-05 (LLM provider/budget/keys) decided.
- **Exit criteria:** Copilot answers only through authorised tools; adversarial suite passes; user approves.
- **Prerequisite phases:** P04, P05, P06 (P09-T01 for mobile wiring) · **Lane:** AI
- **Entry gates:** prerequisite phase gates completed (P04, P05, P06); cumulative quality criteria QG-01.1–3; QG-02.1–6; QG-03.1,2,4,5,6; QG-04.1,2,3,5; QG-05.1,2,4; QG-06.1–6; QG-08.1,3,6; QG-10.1,3; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** QG-07.1,2,3,5,6,8; QG-11.3 (required by `P10-GATE`) plus user review.
- **Release gates:** —

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P10.W1 | P10-T01 | Single task | Phase approved and cross-phase prerequisites complete | — |
| P10.W2 | P10-T02, P10-T05 | Parallel-safe | All dependencies from earlier waves of P10 complete | — |
| P10.W3 | P10-T03, P10-T04, P10-T07 | Parallel-safe | All dependencies from earlier waves of P10 complete | T03 and T04 write separate tool modules; T07 owns the only migration. |
| P10.W4 | P10-T06 | Single task | All dependencies from earlier waves of P10 complete | — |
| P10.W5 | P10-T08 | Single task | All dependencies from earlier waves of P10 complete | — |
| P10.W6 | P10-T09, P10-T10 | Parallel-safe | All dependencies from earlier waves of P10 complete | — |
| P10.W7 | P10-GATE | Single task | All dependencies from earlier waves of P10 complete | — |

#### P10-T01 — AI governance, threat model and provider policy

`DOC` · Size S · Wave P10.W1 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Define tool allow-list, data classification, logging/retention and provider data-handling.
- **Depends on:** P04-T09, P04-GATE, P05-GATE, P06-GATE
- **Parallel with:** — (sequential)
- **Unblocks:** P10-T02, P10-T05, P10-GATE
- **Deliverables:** Updated ai-governance.md, AI threat model, ADR for provider.
- **Acceptance criteria:**
  - No tool for SQL, shell or arbitrary URLs.
  - User approves provider and key-custody approach.
- **Verification:** User approval.
- **Subtasks:** `P10-T01.1` Allow-list · `P10-T01.2` Threat model · `P10-T01.3` Provider ADR

#### P10-T02 — Tool framework

`AI` · Size L · Wave P10.W2 · Approval: no

- **Objective:** Registry with Pydantic schemas, user-context propagation, per-tool authorisation, auditing, timeouts and rate limits.
- **Depends on:** P10-T01, P04-T03, P04-T04
- **Parallel with:** P10-T05
- **Unblocks:** P10-T03, P10-T04, P10-T07, P10-GATE
- **Deliverables:** ai/tools framework.
- **Acceptance criteria:**
  - A tool call without user context is rejected.
  - Each call emits an audit event with args hash and correlation ID.
- **Verification:** CK-B
- **Subtasks:** `P10-T02.1` Registry · `P10-T02.2` Schemas · `P10-T02.3` Authz and audit · `P10-T02.4` Tests

#### P10-T03 — Core read tools

`AI` · Size L · Wave P10.W3 · Approval: no

- **Objective:** get_portfolio_summary/allocation/performance, get_net_worth, get_goal_progress.
- **Depends on:** P10-T02, P06-T09
- **Parallel with:** P10-T04, P10-T07
- **Unblocks:** P10-T06, P10-GATE
- **Deliverables:** Tool modules.
- **Acceptance criteria:**
  - Each tool has a cross-user denial test.
  - Returns structured JSON with as-of timestamps.
- **Verification:** CK-B
- **Subtasks:** `P10-T03.1` Five tools · `P10-T03.2` Denial tests · `P10-T03.3` Schema tests

#### P10-T04 — Forecast tools

`AI` · Size M · Wave P10.W3 · Approval: no

- **Objective:** run_compound_forecast and run_goal_forecast.
- **Depends on:** P10-T02, P06-T02
- **Parallel with:** P10-T03, P10-T07
- **Unblocks:** P10-T06, P10-GATE
- **Deliverables:** Tool modules.
- **Acceptance criteria:**
  - Tools call the deterministic engine only.
- **Verification:** CK-B
- **Subtasks:** `P10-T04.1` Two tools · `P10-T04.2` Tests

#### P10-T05 — LLM provider abstraction and OpenAI adapter

`AI` · Size M · Wave P10.W2 · Approval: no

- **Objective:** Provider interface, OpenAI adapter, fake provider, model/version capture.
- **Depends on:** P10-T01
- **Parallel with:** P10-T02
- **Unblocks:** P10-T06, P10-GATE
- **Deliverables:** ai/providers.
- **Acceptance criteria:**
  - Keys come from environment/secret manager only.
  - Fake provider supports deterministic tests.
- **Verification:** CK-B, CK-S
- **Subtasks:** `P10-T05.1` Interface · `P10-T05.2` OpenAI adapter · `P10-T05.3` Fake · `P10-T05.4` Tests

#### P10-T06 — Orchestrator and /ai/chat with streaming

`AI` · Size L · Wave P10.W4 · Approval: no

- **Objective:** Tool-calling loop with scope enforcement, max-call limits and server-sent streaming.
- **Depends on:** P10-T03, P10-T04, P10-T05
- **Parallel with:** — (sequential)
- **Unblocks:** P10-T08, P10-GATE
- **Deliverables:** POST /api/v1/ai/chat.
- **Acceptance criteria:**
  - Unknown or unauthorised tool requests are refused.
  - Scope from the client is validated server-side.
- **Verification:** CK-B, CK-API
- **Subtasks:** `P10-T06.1` Loop · `P10-T06.2` Scope enforcement · `P10-T06.3` Streaming · `P10-T06.4` Tests

#### P10-T07 — Conversation persistence and AI audit

`DB` · Size M · Wave P10.W3 · Approval: no

- **Objective:** ai_conversations, ai_messages, ai_tool_calls with retention.
- **Depends on:** P10-T02
- **Parallel with:** P10-T03, P10-T04
- **Unblocks:** P10-T08, P10-GATE
- **Deliverables:** Schema/migration and repositories.
- **Acceptance criteria:**
  - Messages and tool calls are user-scoped; retention is configurable.
- **Verification:** CK-B, CK-DB
- **Subtasks:** `P10-T07.1` Schema · `P10-T07.2` Repositories · `P10-T07.3` Retention · `P10-T07.4` Tests

#### P10-T08 — Response validation and safety policy

`AI` · Size L · Wave P10.W5 · Approval: no

- **Objective:** Four-section structured output (observed/calculated/assumption/interpretation), refusal rules, guarantee-language guard, stale-data qualification.
- **Depends on:** P10-T06, P10-T07
- **Parallel with:** — (sequential)
- **Unblocks:** P10-T09, P10-T10, P10-GATE, P12-T01
- **Deliverables:** Validators and policy.
- **Acceptance criteria:**
  - Invalid output is rejected and retried or refused.
  - Forecasts never described as guaranteed.
- **Verification:** CK-B
- **Subtasks:** `P10-T08.1` Schema · `P10-T08.2` Guards · `P10-T08.3` Refusal rules · `P10-T08.4` Tests

#### P10-T09 — AI security and quality suite

`QA` · Size L · Wave P10.W6 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Prompt injection, cross-user adversarial, tool permission, hallucination regression, missing-data and citation tests.
- **Depends on:** P10-T08
- **Parallel with:** P10-T10
- **Unblocks:** P10-GATE
- **Deliverables:** Test suite in CI.
- **Acceptance criteria:**
  - All adversarial cases pass; results reviewed by the user.
- **Verification:** CK-B, CK-S
- **Subtasks:** `P10-T09.1` Injection · `P10-T09.2` Cross-user · `P10-T09.3` Hallucination · `P10-T09.4` Missing data · `P10-T09.5` Documented evaluation datasets and acceptance thresholds (DEC-17)

#### P10-T10 — Mobile Copilot live wiring

`MOB` · Size L · Wave P10.W6 · Approval: no

- **Objective:** Replace demo copilot with streaming live chat.
- **Depends on:** P10-T08, P09-T01, P03-T06
- **Parallel with:** P10-T09
- **Unblocks:** P10-GATE
- **Deliverables:** Live CopilotRepository.
- **Acceptance criteria:**
  - Scope chip is sent and enforced; refusal/retry states work with real events.
- **Verification:** CK-M, CK-I
- **Subtasks:** `P10-T10.1` Streaming consumer · `P10-T10.2` History · `P10-T10.3` States · `P10-T10.4` Tests

#### P10-GATE — Phase P10 exit gate

`GATE` · Size S · Wave P10.W7 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Confirm Copilot readiness.
- **Depends on:** P10-T01, P10-T02, P10-T03, P10-T04, P10-T05, P10-T06, P10-T07, P10-T08, P10-T09, P10-T10
- **Parallel with:** — (sequential)
- **Unblocks:** P11-T01, P12-T01, P12-T02, P15-T01, P15-T02, P15-T04, P15-T05, P15-T06
- **Deliverables:** Gate summary.
- **Acceptance criteria:**
  - User approval recorded.
- **Verification:** CK-B, CK-M, CK-I, CK-S.
- **Quality gates required before completion:** QG-07.1, QG-07.2, QG-07.3, QG-07.5, QG-07.6, QG-07.8, QG-11.3
- **Subtasks:** `P10-GATE.1` Run gates · `P10-GATE.2` Present summary · `P10-GATE.3` Record approval

### P11 — Multi-Currency Reporting & FX Management (FXCUR workstream)

- **Goal:** A global reporting currency: users switch every financial figure in the app (dashboard, portfolios, holdings, analytics, net worth, income, goals, calculator, forecasts, AI) between currencies with one setting, using timestamped provider rates, consistent snapshots and historically correct rates, without changing any underlying balance, transaction or historical record (ADR-0010).
- **Entry criteria:** P05-GATE, P06-GATE, P08-GATE, P09-GATE and P10-GATE complete; user approves the phase and ADR-0010 (P11-T01).
- **Exit criteria:** QG-21..QG-25 (QG-FXCUR-01..05) satisfied; reporting currency works end to end on Android and iOS and in the Copilot.
- **Prerequisite phases:** P05, P06, P08, P09, P10 · **Lane:** CORE (extends the P05/P08 FX foundations; later phases P12 AI Intelligence, P13 Forex and P15 hardening build on it)
- **Task alias:** FXCUR-nn = P11-Tnn; QG-FXCUR-nn = QG-(20+nn).
- **Entry gates:** prerequisite phase gates completed (P05, P06, P08, P09, P10); cumulative quality criteria QG-03.1–6; QG-06.1–7; QG-07.1,2,3,5,6,8; QG-08.1,3,6; QG-11.1–6; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** QG-21, QG-22, QG-23, QG-24, QG-25 (every criterion) required by `P11-GATE` plus user review.
- **Release gates:** `Gates-start` on P11-T11 and P11-T12: QG-21..QG-25 satisfied.

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P11.W1 | P11-T01 | Single task | Phase approved and all dependencies complete | — |
| P11.W2 | P11-T02 | Single task | Phase approved and all dependencies complete | — |
| P11.W3 | P11-T03 | Single task | Phase approved and all dependencies complete | — |
| P11.W4 | P11-T04, P11-T05 | Parallel-safe | Phase approved and all dependencies complete | Different modules (conversion vs history); no migration in either. |
| P11.W5 | P11-T06 | Single task | Phase approved and all dependencies complete | — |
| P11.W6 | P11-T07, P11-T08 | Parallel-safe | Phase approved and all dependencies complete | Mobile vs AI tool layer; disjoint code. |
| P11.W7 | P11-T09 | Single task | Phase approved and all dependencies complete | — |
| P11.W8 | P11-T10 | Single task | Phase approved and all dependencies complete | — |
| P11.W9 | P11-T11 | Single task | Phase approved and all dependencies complete | — |
| P11.W10 | P11-T12 | Single task | Phase approved and all dependencies complete | — |
| P11.W11 | P11-GATE | Single task | Phase approved and all dependencies complete | — |

#### P11-T01 — FXCUR-01 Requirements, architecture and reconciliation with existing FX work

`DOC` · Size M · Wave P11.W1 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Confirm the reporting-currency design (ADR-0010, docs/design/multi-currency-design.md) and reconcile it with what already exists: the FX service and rate-selection rules (P05-T06), the fx_rates table (P05-T01), FX ingestion and backfill (P08-T05), the provider abstraction (P08-T02), user preferences (P04-T05) and Settings (P07-T08). Resolve DEC-25..DEC-29.
- **Depends on:** P05-GATE, P06-GATE, P08-GATE, P09-GATE, P10-GATE
- **Parallel with:** — (sequential)
- **Unblocks:** P11-T02
- **Deliverables:** ADR-0010 Accepted; design approved; reuse/extension map of existing modules; decisions recorded.
- **Acceptance criteria:**
  - Every FXCUR capability is mapped to an existing module it extends, or justified as new; nothing is duplicated.
  - Reporting currency is a global user setting that changes presentation only; balances, transaction amounts and historical records are never altered.
- **Verification:** User approval of ADR-0010 and the design.
- **Subtasks:** `P11-T01.1` Inventory of existing FX and currency code · `P11-T01.2` Reuse/extension map · `P11-T01.3` ADR-0010 · `P11-T01.4` Decisions DEC-25..DEC-29

#### P11-T02 — FXCUR-02 Currency data model

`DB` · Size M · Wave P11.W2 · Approval: no

- **Objective:** currencies reference table (ISO 4217 code, name, symbol, minor units, active), user_currency_preferences (reporting currency, recent currencies), extension of the existing fx_rates table (rate_type, status, provider, rate_timestamp, retrieved_at, rate path) and fx_conversion_audit, with migrations and pair/date indexes.
- **Depends on:** P11-T01
- **Parallel with:** — (sequential)
- **Unblocks:** P11-T03
- **Deliverables:** Alembic migration, SQLAlchemy models, seed of the 10 initial currencies, schema tests.
- **Acceptance criteria:**
  - All amounts and rates are NUMERIC; no float columns.
  - Adding a currency is a data change, not a code change.
  - Indexes support (base, quote, timestamp) lookups; migration round-trips.
- **Verification:** CK-B, CK-DB.
- **Subtasks:** `P11-T02.1` currencies table and seed · `P11-T02.2` user_currency_preferences · `P11-T02.3` fx_rates extension · `P11-T02.4` fx_conversion_audit · `P11-T02.5` Indexes and migration tests

#### P11-T03 — FXCUR-03 FX provider integration, refresh and caching

`BE` · Size L · Wave P11.W3 · Approval: **USER REVIEW REQUIRED**

- **Objective:** FX rate adapters on the P08 provider abstraction with a configurable primary and fallback provider (DEC-25), scheduled refresh within provider quotas, exponential backoff, a central rate cache with TTL, batch retrieval, staleness detection and explicit status (current, delayed, indicative, cached, unavailable).
- **Depends on:** P11-T02
- **Parallel with:** — (sequential)
- **Unblocks:** P11-T04, P11-T05
- **Deliverables:** FX adapters, refresh job, cache, POST /api/v1/fx/refresh (authenticated, rate-limited), contract tests with recorded fixtures.
- **Acceptance criteria:**
  - Every rate carries provider, rate_type, rate_timestamp, retrieved_at and status; cached data is never labelled current.
  - When both providers fail the API reports unavailable with the last good rate and its age; no rate is invented.
  - Refresh respects quotas and does not call the provider per UI request.
- **Verification:** CK-B, CK-API; outage, fallback, staleness and cache tests.
- **Subtasks:** `P11-T03.1` Adapters and contract tests · `P11-T03.2` Primary and fallback selection · `P11-T03.3` Refresh scheduler and backoff · `P11-T03.4` Cache and batch retrieval · `P11-T03.5` Staleness and status · `P11-T03.6` Refresh endpoint with limits

#### P11-T04 — FXCUR-04 Conversion engine with rate snapshots and cross-rates

`BE` · Size L · Wave P11.W4 · Approval: no

- **Objective:** Extend the P05-T06 FX service into a deterministic reporting-conversion engine: Decimal arithmetic, per-currency precision and ADR-0006 rounding, direction-validated rates, cross-rates through a pivot currency with the rate path recorded, and immutable rate snapshots so every total on one screen or report uses the same rates.
- **Depends on:** P11-T03
- **Parallel with:** P11-T05
- **Unblocks:** P11-T06
- **Deliverables:** Conversion service, snapshot model, GET /api/v1/currencies, GET /api/v1/fx/rates, GET /api/v1/fx/rates/{base}/{quote}, POST /api/v1/fx/convert.
- **Acceptance criteria:**
  - Converted amount = original x rate in Decimal, rounded once at the end per the currency's minor units.
  - Inverse and cross rates are derived with direction checks and the path (e.g. AED->USD->KES) is returned.
  - Original amounts are never modified; conversions are read-only views.
- **Verification:** CK-B, CK-API; independent recomputation; property tests.
- **Subtasks:** `P11-T04.1` Direction-validated rate lookup · `P11-T04.2` Cross-rate path · `P11-T04.3` Precision and rounding · `P11-T04.4` Snapshots · `P11-T04.5` APIs · `P11-T04.6` Reference and property tests

#### P11-T05 — FXCUR-05 Historical rates

`BE` · Size M · Wave P11.W4 · Approval: no

- **Objective:** Historical conversion on top of the P08-T05 backfill: GET /api/v1/fx/history, and three distinct rate concepts (transaction rate, historical valuation rate, current reporting rate) kept apart in the domain model, with explicit flags when a historical rate is missing.
- **Depends on:** P11-T03
- **Parallel with:** P11-T04
- **Unblocks:** P11-T06
- **Deliverables:** History endpoint, rate-concept types, missing-rate flags, tests.
- **Acceptance criteria:**
  - Past transactions and historical valuations use the rate for their date, never today's rate.
  - A missing historical rate is flagged in the response, not silently substituted.
- **Verification:** CK-B, CK-API.
- **Subtasks:** `P11-T05.1` Rate concepts in the domain · `P11-T05.2` History endpoint · `P11-T05.3` Missing-rate handling · `P11-T05.4` Tests

#### P11-T06 — FXCUR-06 Reporting currency across portfolio, analytics, net worth, income, goals and forecasts

`BE` · Size L · Wave P11.W5 · Approval: no

- **Objective:** Add a reporting-currency parameter (default: the user's preference) and a rate snapshot to the dashboard, portfolio, holdings, analytics, net-worth, income, goals and forecast endpoints, plus GET/PATCH /api/v1/me/currency-preferences synchronised across devices. Goals keep their target currency, forecast assumptions are unchanged, and any optional FX scenario overlay is labelled as illustrative.
- **Depends on:** P11-T04, P11-T05
- **Parallel with:** — (sequential)
- **Unblocks:** P11-T07, P11-T08
- **Deliverables:** Endpoint changes with OpenAPI updates, preference API, reconciliation tests.
- **Acceptance criteria:**
  - Totals reconcile: the converted total equals the sum of converted parts under the same snapshot (within documented rounding).
  - Every response states the reporting currency, snapshot id, rates used and their timestamps.
  - Portfolio base currencies, goal target currencies and forecast assumptions are unchanged by a reporting-currency switch.
- **Verification:** CK-B, CK-API, CK-DB; IDOR tests for the preference API.
- **Subtasks:** `P11-T06.1` Reporting-currency parameter and snapshot on read APIs · `P11-T06.2` Preferences API and sync · `P11-T06.3` Goals and forecasts presentation · `P11-T06.4` Optional FX scenario overlay (behind DEC-29) · `P11-T06.5` Reconciliation and IDOR tests

#### P11-T07 — FXCUR-07 Mobile: global currency selector, converted figures and converter

`MOB` · Size L · Wave P11.W6 · Approval: no

- **Objective:** A global reporting-currency setting in Settings and next to Total Wealth on Home (searchable sheet with code, name, symbol, recent currencies and last rate update), applied app-wide through the shared CurrencyAmount and repositories; FX status chip (current / cached / unavailable, with time); a Currency Converter screen (source, target, amount, rate, timestamp, swap, refresh, recent conversions).
- **Depends on:** P11-T06
- **Parallel with:** P11-T08
- **Unblocks:** P11-T09
- **Deliverables:** Reporting-currency provider and persistence/sync, selector sheet, status chip, converter screen, live repository changes, widget and golden tests.
- **Acceptance criteria:**
  - Switching currency updates every figure in place without losing scroll position or navigation; missing rates show a loading or error state, never a guessed value.
  - The preference persists across sessions and syncs through the API.
  - Light/dark, 2.0x text, RTL and accessibility sweep pass.
- **Verification:** CK-M; widget, golden and accessibility tests.
- **Subtasks:** `P11-T07.1` Reporting-currency state and sync · `P11-T07.2` Selector sheet · `P11-T07.3` Home and Settings entry points · `P11-T07.4` App-wide conversion through CurrencyAmount and repositories · `P11-T07.5` FX status chip · `P11-T07.6` Converter screen · `P11-T07.7` Tests

#### P11-T08 — FXCUR-08 AI Copilot currency tools

`AI` · Size M · Wave P11.W6 · Approval: no

- **Objective:** Allow-listed, authorised tools on the P10 tool framework: get_current_fx_rate, get_historical_fx_rate, convert_currency, get_portfolio_value(portfolio_id, currency), get_net_worth(currency), get_fx_exposure(portfolio_id); evaluation set.
- **Depends on:** P11-T06
- **Parallel with:** P11-T07
- **Unblocks:** P11-T09
- **Deliverables:** Tool schemas and handlers, authorisation tests, evaluation cases, output-guard rules.
- **Acceptance criteria:**
  - Tools validate inputs and enforce ownership; cross-user access is impossible.
  - Every converted figure in an answer comes from a tool result with rate, source and timestamp; the model never states a rate it did not receive.
  - Tool conversions equal the conversion API's results for the same snapshot.
- **Verification:** CK-B, CK-AI; adversarial and invented-rate evaluation cases.
- **Subtasks:** `P11-T08.1` Tool schemas · `P11-T08.2` Authorisation · `P11-T08.3` Snapshot consistency with the API · `P11-T08.4` Evaluation set · `P11-T08.5` Tests

#### P11-T09 — FXCUR-09 Integration testing

`QA` · Size M · Wave P11.W7 · Approval: no

- **Objective:** End-to-end tests against the Docker stack: switch currency across all screens, outage and fallback drills, stale rates, historical reports, AI conversions, preference sync across two sessions.
- **Depends on:** P11-T07, P11-T08
- **Parallel with:** — (sequential)
- **Unblocks:** P11-T10
- **Deliverables:** E2E suite and report.
- **Acceptance criteria:**
  - Dashboard, portfolio, report and AI figures agree for the same snapshot.
  - Outage and fallback behave as specified with honest status labels.
- **Verification:** CK-I.
- **Subtasks:** `P11-T09.1` Cross-screen consistency · `P11-T09.2` Outage and fallback drills · `P11-T09.3` Preference sync · `P11-T09.4` Report

#### P11-T10 — FXCUR-10 FXCUR quality gates verification

`QA` · Size S · Wave P11.W8 · Approval: no

- **Objective:** Run and evidence QG-FXCUR-01..05 (QG-21..QG-25).
- **Depends on:** P11-T09
- **Parallel with:** — (sequential)
- **Unblocks:** P11-T11
- **Deliverables:** Quality report per gate under reports/quality/.
- **Acceptance criteria:**
  - Every criterion of QG-21..QG-25 is verified with evidence.
- **Verification:** python scripts/track.py qg check/pass per gate.
- **Quality gates required before completion:** QG-21, QG-22, QG-23, QG-24, QG-25
- **Subtasks:** `P11-T10.1` Accuracy and consistency gates · `P11-T10.2` Reliability gate · `P11-T10.3` Mobile and AI gates · `P11-T10.4` Report

#### P11-T11 — FXCUR-11 Integration and soak validation (local/CI stack)

`QA` · Size S · Wave P11.W9 · Approval: no

- **Objective:** Soak the refresh scheduler and cache on the local/CI stack against the provider sandbox (quota use, backoff, staleness over hours). Cloud staging does not exist yet (P14); FXCUR staging smoke tests are added to P14-T11.
- **Depends on:** P11-T10
- **Parallel with:** — (sequential)
- **Unblocks:** P11-T12
- **Deliverables:** Soak report.
- **Acceptance criteria:**
  - Provider calls stay within quota; no stale rate is labelled current; recovery after outage is automatic.
- **Verification:** Soak run on the local/CI stack.
- **Quality gates required before start:** QG-21, QG-22, QG-23, QG-24, QG-25
- **Subtasks:** `P11-T11.1` Quota and backoff soak · `P11-T11.2` Staleness soak · `P11-T11.3` Report

#### P11-T12 — FXCUR-12 Release readiness sign-off

`REL` · Size S · Wave P11.W10 · Approval: **USER REVIEW REQUIRED**

- **Objective:** User sign-off that the reporting-currency feature is ready to ship with the core release (P16), including FX-provider licence terms for in-app display (DEC-25) and the conversion-audit retention policy (DEC-28).
- **Depends on:** P11-T11
- **Parallel with:** — (sequential)
- **Unblocks:** P11-GATE
- **Deliverables:** Sign-off record, licence review note.
- **Acceptance criteria:**
  - Provider licence permits the intended display and caching.
  - Audit retention follows the approved policy; cosmetic UI conversions are not logged as financial records.
- **Verification:** User approval.
- **Quality gates required before start:** QG-21, QG-22, QG-23, QG-24, QG-25
- **Subtasks:** `P11-T12.1` Licence review · `P11-T12.2` Retention policy check · `P11-T12.3` Sign-off

#### P11-GATE — Phase P11 exit gate

`GATE` · Size S · Wave P11.W11 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Confirm multi-currency reporting.
- **Depends on:** P11-T01, P11-T02, P11-T03, P11-T04, P11-T05, P11-T06, P11-T07, P11-T08, P11-T09, P11-T10, P11-T11, P11-T12
- **Parallel with:** — (sequential)
- **Unblocks:** P12-T01, P12-T02, P13-T01, P15-T01, P15-T02, P15-T04, P15-T05, P15-T06
- **Deliverables:** Gate summary.
- **Acceptance criteria:**
  - User approval recorded.
- **Verification:** CK-B, CK-M, CK-I, CK-S.
- **Quality gates required before completion:** QG-21, QG-22, QG-23, QG-24, QG-25
- **Subtasks:** `P11-GATE.1` Run gates · `P11-GATE.2` Present summary · `P11-GATE.3` Record approval

---

### P12 — AI Investment Intelligence & Portfolio Doctor

- **Goal:** Evidence-backed, explainable opportunity discovery, Portfolio Doctor, Compare and Simulate with no trade execution.
- **Entry criteria:** P08-T06, P08-T09, P10-T08 complete.
- **Exit criteria:** Opportunities carry risks, assumptions, evidence and timestamps; safety suite passes; legal review done.
- **Prerequisite phases:** P08, P10, P11 · **Lane:** AI
- **Entry gates:** prerequisite phase gates completed (P08, P10); cumulative quality criteria QG-01.1–3; QG-02.1–6; QG-03.1,2,4,5,6; QG-04.1,2,3,5; QG-05.1,2,4; QG-06.1–7; QG-07.1,2,3,5,6,8; QG-08.1,3,6; QG-09.5; QG-10.1,3; QG-11.3–4; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** QG-07.4,7 (required by `P12-GATE`) plus user review.
- **Release gates:** —

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P12.W1 | P12-T01, P12-T02 | Parallel-safe | Phase approved and cross-phase prerequisites complete | T01 has no migration; T02 owns the migration in W1. |
| P12.W2 | P12-T03, P12-T04, P12-T05 | Parallel-safe | All dependencies from earlier waves of P12 complete | — |
| P12.W3 | P12-T06, P12-T07 | Parallel-safe | All dependencies from earlier waves of P12 complete | — |
| P12.W4 | P12-T08, P12-T09 | Parallel-safe | All dependencies from earlier waves of P12 complete | — |
| P12.W5 | P12-T10 | Single task | All dependencies from earlier waves of P12 complete | — |
| P12.W6 | P12-GATE | Single task | All dependencies from earlier waves of P12 complete | — |

#### P12-T01 — Portfolio Doctor service and API

`AI` · Size L · Wave P12.W1 · Approval: no

- **Objective:** Deterministic findings (concentration, class, sector, geography, currency, liquidity, volatility, income dependence, goal alignment) with severity.
- **Depends on:** P06-T09, P10-T08, P08-GATE, P10-GATE, P11-GATE
- **Parallel with:** P12-T02
- **Unblocks:** P12-T04, P12-GATE
- **Deliverables:** POST /ai/portfolio-doctor.
- **Acceptance criteria:**
  - Findings are computed deterministically; LLM only explains.
  - Alternative scenarios are not trades.
- **Verification:** CK-B, CK-API
- **Subtasks:** `P12-T01.1` Rules · `P12-T01.2` Severity model · `P12-T01.3` Endpoint · `P12-T01.4` Tests

#### P12-T02 — Investment universe and eligibility filters

`BE` · Size L · Wave P12.W1 · Approval: no

- **Objective:** Universe model, ingestion and hard eligibility rules.
- **Depends on:** P08-T06, P08-GATE, P10-GATE, P11-GATE
- **Parallel with:** P12-T01
- **Unblocks:** P12-T03, P12-T04, P12-T05, P12-GATE
- **Deliverables:** Schema/migration, service.
- **Acceptance criteria:**
  - Eligibility depends on risk profile, liquidity and jurisdiction rules.
- **Verification:** CK-B, CK-DB
- **Subtasks:** `P12-T02.1` Schema · `P12-T02.2` Ingestion · `P12-T02.3` Filters · `P12-T02.4` Tests

#### P12-T03 — Quantitative features and explainable scoring

`BE` · Size L · Wave P12.W2 · Approval: no

- **Objective:** Transparent factor scoring with configurable weights.
- **Depends on:** P12-T02, P08-T06
- **Parallel with:** P12-T04, P12-T05
- **Unblocks:** P12-T06, P12-T07, P12-GATE
- **Deliverables:** Scoring service.
- **Acceptance criteria:**
  - Each score is decomposable into factor contributions.
  - Missing data lowers confidence, not silently ignored.
- **Verification:** CK-B
- **Subtasks:** `P12-T03.1` Features · `P12-T03.2` Scoring · `P12-T03.3` Explanations · `P12-T03.4` Tests

#### P12-T04 — Portfolio compatibility and suitability

`BE` · Size M · Wave P12.W2 · Approval: no

- **Objective:** Diversification/concentration impact and suitability checks.
- **Depends on:** P12-T02, P12-T01
- **Parallel with:** P12-T03, P12-T05
- **Unblocks:** P12-T06, P12-T07, P12-GATE
- **Deliverables:** Compatibility service.
- **Acceptance criteria:**
  - Impact computed with deterministic analytics.
- **Verification:** CK-B
- **Subtasks:** `P12-T04.1` Impact calc · `P12-T04.2` Suitability rules · `P12-T04.3` Tests

#### P12-T05 — Research evidence ingestion and retrieval

`BE` · Size L · Wave P12.W2 · Approval: no

- **Objective:** research_items with pgvector, provenance and timestamps.
- **Depends on:** P12-T02, P08-T09
- **Parallel with:** P12-T03, P12-T04
- **Unblocks:** P12-T06, P12-GATE
- **Deliverables:** Schema/migration, retrieval service.
- **Acceptance criteria:**
  - Every evidence item has source, licence status and as-of time.
  - Retrieval is user-agnostic public data only.
- **Verification:** CK-B, CK-DB
- **Subtasks:** `P12-T05.1` Schema · `P12-T05.2` Ingestion · `P12-T05.3` Retrieval · `P12-T05.4` Tests

#### P12-T06 — Opportunity pipeline and schema

`AI` · Size L · Wave P12.W3 · Approval: no

- **Objective:** Run pipeline, generate LLM explanation from retrieved evidence only, validate and persist.
- **Depends on:** P12-T03, P12-T04, P12-T05
- **Parallel with:** P12-T07
- **Unblocks:** P12-T08, P12-T09, P12-GATE
- **Deliverables:** ai_recommendation_runs/ai_opportunities and POST /ai/opportunities.
- **Acceptance criteria:**
  - Output includes thesis, why surfaced, risks, assumptions, portfolio impact, evidence refs and data-as-of.
  - LLM cannot add facts or expected returns.
- **Verification:** CK-B, CK-DB, CK-API
- **Subtasks:** `P12-T06.1` Schema · `P12-T06.2` Pipeline · `P12-T06.3` LLM explanation and validation · `P12-T06.4` Persistence · `P12-T06.5` Tests

#### P12-T07 — Compare and Simulate APIs

`BE` · Size L · Wave P12.W3 · Approval: no

- **Objective:** Side-by-side comparison and simulation through the forecast engine with marked assumptions.
- **Depends on:** P12-T03, P12-T04, P06-T02
- **Parallel with:** P12-T06
- **Unblocks:** P12-T08, P12-T09, P12-GATE
- **Deliverables:** POST /ai/compare, /ai/simulate.
- **Acceptance criteria:**
  - Future returns appear only as assumptions/scenarios.
- **Verification:** CK-B, CK-API
- **Subtasks:** `P12-T07.1` Compare · `P12-T07.2` Simulate · `P12-T07.3` Tests

#### P12-T08 — Safety and quality suite

`QA` · Size L · Wave P12.W4 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Stale data, missing evidence, prompt injection, unauthorised access, invalid LLM output, guarantee-language and hallucination tests.
- **Depends on:** P12-T06, P12-T07
- **Parallel with:** P12-T09
- **Unblocks:** P12-T10, P12-GATE
- **Deliverables:** Suite in CI.
- **Acceptance criteria:**
  - All cases pass; results reviewed by the user.
- **Verification:** CK-B, CK-S
- **Subtasks:** `P12-T08.1` Suite · `P12-T08.2` Review

#### P12-T09 — Mobile wiring: Doctor, Opportunities, Compare, Simulate

`MOB` · Size L · Wave P12.W4 · Approval: no

- **Objective:** Replace demo content with live services.
- **Depends on:** P12-T06, P12-T07, P07-T06, P07-T07
- **Parallel with:** P12-T08
- **Unblocks:** P12-T10, P12-GATE
- **Deliverables:** Live repositories.
- **Acceptance criteria:**
  - No fixed advice copy in UI; all content timestamped and sourced; no trade buttons.
- **Verification:** CK-M, CK-I
- **Subtasks:** `P12-T09.1` Doctor · `P12-T09.2` Opportunities · `P12-T09.3` Compare · `P12-T09.4` Simulate · `P12-T09.5` Tests

#### P12-T10 — Disclosure and compliance content review

`DOC` · Size S · Wave P12.W5 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Legal/compliance review of disclaimers and wording (DEC-10).
- **Depends on:** P12-T08, P12-T09
- **Parallel with:** — (sequential)
- **Unblocks:** P12-GATE
- **Deliverables:** Approved copy and checklist.
- **Acceptance criteria:**
  - Reviewer signs off wording and jurisdictional disclosures.
- **Verification:** User/legal sign-off.
- **Subtasks:** `P12-T10.1` Copy inventory · `P12-T10.2` Review · `P12-T10.3` Apply changes

#### P12-GATE — Phase P12 exit gate

`GATE` · Size S · Wave P12.W6 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Confirm Investment Intelligence.
- **Depends on:** P12-T01, P12-T02, P12-T03, P12-T04, P12-T05, P12-T06, P12-T07, P12-T08, P12-T09, P12-T10
- **Parallel with:** — (sequential)
- **Unblocks:** P15-T01, P15-T02, P15-T04, P15-T05, P15-T06
- **Deliverables:** Gate summary.
- **Acceptance criteria:**
  - User approval recorded.
- **Verification:** CK-B, CK-M, CK-I, CK-S.
- **Quality gates required before completion:** QG-07.4, QG-07.7
- **Subtasks:** `P12-GATE.1` Run gates · `P12-GATE.2` Present summary · `P12-GATE.3` Record approval

### P13 — Forex Trading Intelligence (FX workstream)

- **Goal:** AI-assisted forex market intelligence, probabilistic forecasts, transparent opportunity ranking, deterministic trade-risk calculation, backtesting and paper trading, integrated into WealthSphere as a **decision-support and paper-trading** module. No live trade execution (see ADR-0009 and docs/design/forex-technical-design.md).
- **Entry criteria:** P08-GATE, P09-GATE, P10-GATE and P12-GATE complete; user approves the phase and ADR-0009 (P13-T01).
- **Exit criteria:** QG-13..QG-20 (QG-FX-01..08) satisfied; paper trading separate from real holdings; no live execution in the build; market-data licence and regulatory reviews recorded.
- **Prerequisite phases:** P08, P09, P10, P11, P12 · **Lane:** FX (sits between the AI phases and the cloud infrastructure phase P14; it needs no cloud environment, so it is validated on the local/CI stack and joins staging in P14-T11)
- **Task alias:** the FX-nn names are the same tasks as P13-Tnn (FX-01 = P13-T01 … FX-14 = P13-T14); the tracker tracks the P13-Tnn IDs. QG-FX-nn are the gates QG-(12+nn).
- **Entry gates:** prerequisite phase gates completed (P08, P09, P10, P11, P12); cumulative quality criteria QG-06.1–7; QG-07.1–8; QG-08.1,3,6; QG-11.3–4; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** QG-13, QG-14, QG-15, QG-16, QG-17, QG-18, QG-19, QG-20 (every criterion) required by `P13-GATE` plus user review.
- **Release gates:** `Gates-start` on P13-T13 and P13-T14: QG-13..QG-19 satisfied.

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P13.W1 | P13-T01 | Single task | Phase approved and all dependencies complete | — |
| P13.W2 | P13-T02 | Single task | Phase approved and all dependencies complete | — |
| P13.W3 | P13-T03, P13-T04 | Parallel-safe | Phase approved and all dependencies complete | T03 and T04 touch different modules (indicators vs calendar). |
| P13.W4 | P13-T05 | Single task | Phase approved and all dependencies complete | — |
| P13.W5 | P13-T06 | Single task | Phase approved and all dependencies complete | — |
| P13.W6 | P13-T07, P13-T08 | Parallel-safe | Phase approved and all dependencies complete | T07 and T08 touch different modules; only one adds a migration (T07 none, T08 report store). |
| P13.W7 | P13-T09 | Single task | Phase approved and all dependencies complete | — |
| P13.W8 | P13-T10 | Single task | Phase approved and all dependencies complete | — |
| P13.W9 | P13-T11 | Single task | Phase approved and all dependencies complete | — |
| P13.W10 | P13-T12 | Single task | Phase approved and all dependencies complete | — |
| P13.W11 | P13-T13 | Single task | Phase approved and all dependencies complete | — |
| P13.W12 | P13-T14 | Single task | Phase approved and all dependencies complete | — |
| P13.W13 | P13-GATE | Single task | Phase approved and all dependencies complete | — |

#### P13-T01 — FX-01 Requirements, architecture and regulatory scoping

`DOC` · Size M · Wave P13.W1 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Confirm the Forex module scope, amend SOLUTION_INTENT/brief/guide, approve ADR-0009 and the forex technical design, and record the open decisions (DEC-19..DEC-24).
- **Depends on:** P08-GATE, P10-GATE, P11-GATE
- **Parallel with:** — (sequential)
- **Unblocks:** P13-T02
- **Deliverables:** docs/design/forex-technical-design.md approved; ADR-0009 Accepted; intent documents amended; decisions DEC-19..DEC-24 resolved or scheduled.
- **Acceptance criteria:**
  - User approves the scope, the decision-support/paper-trading-only boundary and the release strategy (DEC-23).
  - No live execution, no guaranteed-return language and no mixing of paper balances with net worth are written into the design as hard rules.
- **Verification:** User approval of ADR-0009 and the design document.
- **Subtasks:** `P13-T01.1` Impact assessment on architecture and security · `P13-T01.2` Amend intent documents · `P13-T01.3` Technical design review · `P13-T01.4` ADR-0009 · `P13-T01.5` Decision register update

#### P13-T02 — FX-02 Market data provider abstraction, ingestion and streaming

`BE` · Size L · Wave P13.W2 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Extend the P08 provider abstraction with quote, candle and streaming interfaces for forex; WebSocket streaming with reconnect, heartbeat, caching and stale-data detection; time-series storage; a fake provider so development never invents prices.
- **Depends on:** P13-T01, P08-GATE
- **Parallel with:** — (sequential)
- **Unblocks:** P13-T03, P13-T04
- **Deliverables:** Forex market-data service, provider adapters for the DEC-19 choice, instrument registry (configurable universe), quote and candle tables with migration, streaming gateway to the app.
- **Acceptance criteria:**
  - Every stored quote carries provider, instrument, bid, ask, derived mid, timestamp (UTC), data type (tradable/indicative/delayed/simulated), quality and feed status.
  - When a provider is unavailable the API reports unavailable or stale; it never invents or interpolates a price.
  - Stale-data detection, heartbeat loss and reconnect are covered by tests with an injected clock.
- **Verification:** CK-B, CK-API, CK-DB; contract tests with recorded fixtures; reconnection and stale-data tests.
- **Subtasks:** `P13-T02.1` Quote and candle interfaces · `P13-T02.2` Instrument registry and configurable universe · `P13-T02.3` Time-series schema and migration · `P13-T02.4` Streaming client with heartbeat and reconnect · `P13-T02.5` Stale-data and outage handling · `P13-T02.6` Fake provider and recorded fixtures · `P13-T02.7` Tests

#### P13-T03 — FX-03 Technical analysis engine

`BE` · Size L · Wave P13.W3 · Approval: no

- **Objective:** Deterministic indicators (SMA, EMA, MACD, ADX, RSI, Stochastic, ROC, ATR, Bollinger Bands), market structure (swing points, support/resistance, breakouts, trendlines, channels) and candlestick/price-action detectors, plus timeframe aggregation.
- **Depends on:** P13-T02
- **Parallel with:** P13-T04
- **Unblocks:** P13-T05
- **Deliverables:** Indicator library with reference test vectors, timeframe aggregator (1m to 1M), market-structure and pattern detectors, API.
- **Acceptance criteria:**
  - Every indicator matches independently computed reference cases within a documented tolerance.
  - Aggregation handles missing candles, weekend gaps and irregular sessions without fabricating candles.
  - No LLM computes or edits an indicator value.
- **Verification:** CK-B; reference-vector and property tests; independent recomputation.
- **Subtasks:** `P13-T03.1` Trend indicators · `P13-T03.2` Momentum and volatility indicators · `P13-T03.3` Timeframe aggregation · `P13-T03.4` Market structure · `P13-T03.5` Price-action detectors · `P13-T03.6` Reference vectors and tests

#### P13-T04 — FX-04 Economic calendar and macroeconomic intelligence

`BE` · Size M · Wave P13.W3 · Approval: no

- **Objective:** Ingest scheduled economic events, central-bank decisions and rate differentials with source and timestamp, and keep confirmed data separate from interpretation.
- **Depends on:** P13-T02
- **Parallel with:** P13-T03
- **Unblocks:** P13-T05
- **Deliverables:** Calendar ingestion, event model (actual/forecast/previous, affected currencies, release time), event-risk windows used by the scanner, API.
- **Acceptance criteria:**
  - Each event shows source and timestamp; confirmed values and speculative commentary are different fields and different UI labels.
  - Release times are stored in UTC and shown in the user's timezone.
- **Verification:** CK-B, CK-API; fixture-based ingestion tests; timezone tests.
- **Subtasks:** `P13-T04.1` Event model and schema · `P13-T04.2` Provider adapter · `P13-T04.3` Event-risk windows · `P13-T04.4` API · `P13-T04.5` Tests

#### P13-T05 — FX-05 Prediction models and evaluation framework

`BE` · Size XL · Wave P13.W4 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Extensible model framework with baselines (random walk, no-change), statistical (ARIMA/SARIMA), gradient boosting (LightGBM/XGBoost), Random Forest, ensembles and volatility forecasts, evaluated with time-series-aware validation, calibration and drift monitoring.
- **Depends on:** P13-T03, P13-T04
- **Parallel with:** — (sequential)
- **Unblocks:** P13-T06
- **Deliverables:** Model registry with versions, feature pipeline, walk-forward evaluation, calibration and interval-coverage reports, drift monitor, forecast API.
- **Acceptance criteria:**
  - Every model is benchmarked against the baselines and the comparison is reported even when the baseline wins.
  - No future data reaches a feature or label (leakage tests pass).
  - Forecasts carry horizon, up/down probabilities, return distribution, expected volatility, price interval, calibration status, out-of-sample performance, freshness and model version.
  - A probability is labelled 'requires calibration' until calibration is established.
- **Verification:** CK-B; leakage tests; walk-forward and calibration reports under reports/quality/; user review of the evaluation report.
- **Subtasks:** `P13-T05.1` Feature pipeline · `P13-T05.2` Baselines · `P13-T05.3` Statistical and boosting models · `P13-T05.4` Ensembles and volatility · `P13-T05.5` Walk-forward evaluation · `P13-T05.6` Calibration and interval coverage · `P13-T05.7` Drift monitoring · `P13-T05.8` Forecast API

#### P13-T06 — FX-06 Strategy, signal engine and opportunity ranking

`BE` · Size L · Wave P13.W5 · Approval: no

- **Objective:** Detect setups (trend continuation, breakout, reversal, range, momentum, mean reversion), compute the transparent opportunity score, and rank pairs for the Opportunity Ranking Dashboard.
- **Depends on:** P13-T05
- **Parallel with:** — (sequential)
- **Unblocks:** P13-T07, P13-T08
- **Deliverables:** Signal rules, scoring with a published formula and weights, ranking API with market condition, opportunity type and risk per pair, explanation payload listing every factor.
- **Acceptance criteria:**
  - The score is a weighted, documented combination of trend, momentum, volatility, spread/costs, liquidity, confluence, macro-event risk, forecast calibration, strategy history and risk/reward.
  - Each ranked item exposes its factors, assumptions, key risks, data freshness and costs; output is labelled research candidates, never guaranteed outcomes.
  - Illustrative levels are generated only from timestamped market data and rule definitions.
- **Verification:** CK-B, CK-API; golden tests for scoring; guarantee-language guard.
- **Subtasks:** `P13-T06.1` Setup rules · `P13-T06.2` Scoring model and weights · `P13-T06.3` Ranking and market-condition classifier · `P13-T06.4` Explanation payload · `P13-T06.5` Ranking API · `P13-T06.6` Tests

#### P13-T07 — FX-07 Trade risk management engine

`BE` · Size L · Wave P13.W6 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Deterministic position sizing, pip value (per pair, quote and account currency with FX conversion), margin, costs, slippage and exposure, with configurable risk limits.
- **Depends on:** P13-T06
- **Parallel with:** P13-T08
- **Unblocks:** P13-T09
- **Deliverables:** Risk calculator service and API, instrument contract specifications, Decimal-only arithmetic with explicit rounding (ADR-0006), independent reference cases.
- **Acceptance criteria:**
  - No fixed pip-value assumption: pip value is derived from the quote currency, account currency and conversion rate for each pair (including JPY and USD-quote pairs).
  - Outputs: position size, pip value, potential loss and profit, risk/reward, margin, estimated costs, exposure and account impact.
  - Leverage and margin warnings are returned, and the output states that stop-losses can slip or gap.
- **Verification:** CK-B; independent recomputation; property tests; user review of formulas.
- **Subtasks:** `P13-T07.1` Contract specification model · `P13-T07.2` Pip value and conversion · `P13-T07.3` Position sizing · `P13-T07.4` Margin and leverage · `P13-T07.5` Costs and slippage · `P13-T07.6` Exposure and limits · `P13-T07.7` Reference cases and tests

#### P13-T08 — FX-08 Backtesting and strategy validation

`BE` · Size XL · Wave P13.W6 · Approval: no

- **Objective:** Event-driven backtester with spread, commission and slippage models, walk-forward and out-of-sample evaluation, benchmarks and reproducible reports.
- **Depends on:** P13-T06
- **Parallel with:** P13-T07
- **Unblocks:** P13-T09
- **Deliverables:** Backtest engine, metrics (return, drawdown, win rate, profit factor, Sharpe, Sortino, expectancy, streaks, exposure, cost and slippage sensitivity), report store.
- **Acceptance criteria:**
  - Look-ahead and future-leakage tests fail on a deliberately leaky strategy and pass on the real engine.
  - Costs and slippage are always included; sensitivity analysis is reported.
  - Same inputs and seed produce an identical report (hash recorded).
- **Verification:** CK-B; leakage tests; reproducibility test; reports under reports/quality/.
- **Subtasks:** `P13-T08.1` Engine and clock · `P13-T08.2` Cost and slippage models · `P13-T08.3` Metrics · `P13-T08.4` Walk-forward harness · `P13-T08.5` Benchmarks · `P13-T08.6` Reproducible reports · `P13-T08.7` Leakage tests

#### P13-T09 — FX-09 Paper trading and trade journal

`BE` · Size L · Wave P13.W7 · Approval: no

- **Objective:** Virtual account, simulated orders with virtual stop/take-profit, positions, realised/unrealised P/L, journal, strategy tags and performance analytics, kept apart from real holdings.
- **Depends on:** P13-T07, P13-T08
- **Parallel with:** — (sequential)
- **Unblocks:** P13-T10
- **Deliverables:** Paper-trading service and API, schema and migration, journal, analytics, isolation tests.
- **Acceptance criteria:**
  - Paper balances and trades are in separate tables and never enter net worth, holdings or analytics of real portfolios.
  - Every paper-trading response carries a PAPER TRADING marker; backtested, paper and live-observed performance are separate labelled series.
  - Ownership and IDOR tests pass for all endpoints.
- **Verification:** CK-B, CK-API, CK-DB, CK-S; isolation and IDOR tests.
- **Subtasks:** `P13-T09.1` Schema and migration · `P13-T09.2` Virtual account and orders · `P13-T09.3` Positions and P/L · `P13-T09.4` Journal and tags · `P13-T09.5` Analytics · `P13-T09.6` Isolation and IDOR tests

#### P13-T10 — FX-10 AI Forex Copilot (allow-listed tools)

`AI` · Size L · Wave P13.W8 · Approval: no

- **Objective:** Add forex tools to the AI orchestrator (quotes, indicators, forecasts, opportunities, calendar, risk calculator, backtest results, paper performance), each authorised server-side, with the four-part answer structure.
- **Depends on:** P13-T09, P10-GATE, P12-GATE
- **Parallel with:** — (sequential)
- **Unblocks:** P13-T11
- **Deliverables:** Tool definitions and schemas, orchestrator prompts, structured output validation, evaluation set, guarantee-language guard.
- **Acceptance criteria:**
  - The model can only call allow-listed tools; every market fact, indicator, forecast and risk figure comes from a tool result with timestamp and source.
  - Answers separate facts, model forecasts, assumptions and interpretation, include model version and data freshness, and refuse or qualify when data is stale.
  - No guaranteed-profit or personalised-advice language passes the output guard.
- **Verification:** CK-B, CK-AI; AI evaluation set including adversarial and stale-data cases.
- **Subtasks:** `P13-T10.1` Tool schemas and authorisation · `P13-T10.2` Orchestrator integration · `P13-T10.3` Structured output validation · `P13-T10.4` Guarantee-language guard · `P13-T10.5` Evaluation set · `P13-T10.6` Tests

#### P13-T11 — FX-11 Android and iOS Forex Intelligence integration

`MOB` · Size XL · Wave P13.W9 · Approval: no

- **Objective:** Forex section in the app: overview, live markets, chart, predictions, Opportunity Ranking Dashboard, scanner, trade setup, risk calculator, calendar, backtesting, paper trading, journal, Copilot and alerts, in the approved design language.
- **Depends on:** P13-T10, P09-GATE
- **Parallel with:** — (sequential)
- **Unblocks:** P13-T12
- **Deliverables:** Screens and widgets reusing the design system, streaming client with reconnection, notification preferences, DEMO-first fixtures then API wiring.
- **Acceptance criteria:**
  - Screens use the shared design system, light and dark, text scaling 2.0 and RTL; PAPER TRADING and DEMO labels are always visible where relevant.
  - Streaming updates keep charts responsive; background/foreground transitions and network interruptions recover cleanly.
  - Indicative or delayed prices are never shown as live executable quotes.
- **Verification:** CK-M, flutter test incl. goldens; integration tests; manual device pass.
- **Subtasks:** `P13-T11.1` Navigation and entry points · `P13-T11.2` Overview and live markets · `P13-T11.3` Chart and predictions · `P13-T11.4` Opportunity Ranking Dashboard and scanner · `P13-T11.5` Trade setup and risk calculator · `P13-T11.6` Calendar and backtesting · `P13-T11.7` Paper trading and journal · `P13-T11.8` Copilot and alerts · `P13-T11.9` Streaming resilience · `P13-T11.10` Tests

#### P13-T12 — FX-12 Forex quality gates verification

`QA` · Size M · Wave P13.W10 · Approval: no

- **Objective:** Run and evidence QG-FX-01..07 (QG-13..QG-19) with reports under reports/quality/.
- **Depends on:** P13-T11
- **Parallel with:** — (sequential)
- **Unblocks:** P13-T13
- **Deliverables:** Quality report per gate.
- **Acceptance criteria:**
  - Every criterion of QG-13..QG-19 is verified with evidence; failures block FX-13.
- **Verification:** python scripts/track.py qg check/pass per gate; CK-B, CK-M, CK-S.
- **Quality gates required before completion:** QG-13, QG-14, QG-15, QG-16, QG-17, QG-18, QG-19
- **Subtasks:** `P13-T12.1` Market data and indicator gates · `P13-T12.2` Prediction and risk gates · `P13-T12.3` Backtesting and AI gates · `P13-T12.4` Mobile gate · `P13-T12.5` Report

#### P13-T13 — FX-13 Integration and soak validation (local/CI stack)

`QA` · Size M · Wave P13.W11 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Run the module end to end on the local/CI stack (docker-compose, fake provider with recorded streams, and the licensed provider's sandbox or delayed feed where DEC-19 allows): streaming soak, outage drills, stale-data behaviour and user acceptance. Cloud staging does not exist yet (P14); the module's staging smoke tests are added to P14-T11.
- **Depends on:** P13-T12
- **Parallel with:** — (sequential)
- **Unblocks:** P13-T14
- **Deliverables:** Integration and soak validation report.
- **Acceptance criteria:**
  - Soak test and provider-outage drill pass; no invented prices; alerts and dashboards operational.
  - User acceptance recorded.
- **Verification:** Soak and drill tests on the local/CI stack; user approval.
- **Quality gates required before start:** QG-13, QG-14, QG-15, QG-16, QG-17, QG-18, QG-19
- **Subtasks:** `P13-T13.1` Streaming soak · `P13-T13.2` Outage and failover drills · `P13-T13.3` Observability check · `P13-T13.4` User acceptance

#### P13-T14 — FX-14 Release approval and regulatory readiness

`REL` · Size M · Wave P13.W12 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Complete market-data licence review, launch-market regulatory review, risk disclosures and the final decision on release, with live execution still disabled.
- **Depends on:** P13-T13
- **Parallel with:** — (sequential)
- **Unblocks:** P13-GATE
- **Deliverables:** Licence and regulatory review records, disclosure text, release decision.
- **Acceptance criteria:**
  - Market-data licence permits the in-app display, storage and any redistribution.
  - Regulatory review is complete for each launch market (DEC-20); disclosures are approved.
  - No live execution capability exists in the build; enabling one needs a separate approved phase.
  - The release decision covers the module's readiness only. Enabling the Forex feature flag in production additionally requires the core hardening gate (P15-GATE) and the staging smoke tests in P14-T11.
- **Verification:** User approval; legal review records.
- **Quality gates required before start:** QG-13, QG-14, QG-15, QG-16, QG-17, QG-18, QG-19
- **Subtasks:** `P13-T14.1` Licence review · `P13-T14.2` Regulatory review · `P13-T14.3` Risk disclosures · `P13-T14.4` Execution-disabled verification · `P13-T14.5` Release decision

#### P13-GATE — Phase P13 exit gate

`GATE` · Size S · Wave P13.W13 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Confirm the Forex Trading Intelligence module.
- **Depends on:** P13-T01, P13-T02, P13-T03, P13-T04, P13-T05, P13-T06, P13-T07, P13-T08, P13-T09, P13-T10, P13-T11, P13-T12, P13-T13, P13-T14
- **Parallel with:** — (sequential)
- **Unblocks:** —
- **Deliverables:** Gate summary.
- **Acceptance criteria:**
  - User approval recorded.
- **Verification:** CK-B, CK-M, CK-S.
- **Quality gates required before completion:** QG-13, QG-14, QG-15, QG-16, QG-17, QG-18, QG-19, QG-20
- **Subtasks:** `P13-GATE.1` Run gates · `P13-GATE.2` Present summary · `P13-GATE.3` Record approval

---

### P14 — Cloud Infrastructure & Deployment Pipeline

- **Goal:** Cloud-portable infrastructure as code, container delivery, secrets, observability, backup/DR and a verified staging environment.
- **Entry criteria:** P01-GATE complete; DEC-02 (cloud/region/data residency) decided in P14-T01.
- **Exit criteria:** Staging runs the full stack from pipeline with monitoring and a tested restore.
- **Prerequisite phases:** P01 (early start allowed); deployment tasks need P04-T01 · **Lane:** INFRA
- **Entry gates:** prerequisite phase gates completed (P01); cumulative quality criteria QG-01.1–2; QG-02.1–6; QG-03.1,6; QG-04.1–3; QG-05.1–2; QG-08.3,6; QG-10.1,3; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** QG-08.4,5,7; QG-10.2,4,5,6,7,8 (required by `P14-GATE`) plus user review.
- **Release gates:** P14-T11 → start: QG-02.1, QG-02.2, QG-02.3, QG-02.4, QG-03.1, QG-03.2, QG-03.6, QG-08.3, QG-08.4, QG-08.6, QG-11.1, QG-11.2, QG-11.5

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P14.W1 | P14-T01, P14-T04 | Parallel-safe | Phase approved and cross-phase prerequisites complete | T01 is a decision; T04 builds images. Disjoint paths. |
| P14.W2 | P14-T02 | Single task | All dependencies from earlier waves of P14 complete | — |
| P14.W3 | P14-T03, P14-T06 | Parallel-safe | All dependencies from earlier waves of P14 complete | — |
| P14.W4 | P14-T05 | Single task | All dependencies from earlier waves of P14 complete | — |
| P14.W5 | P14-T07, P14-T09, P14-T10 | Parallel-safe | All dependencies from earlier waves of P14 complete | — |
| P14.W6 | P14-T08 | Single task | All dependencies from earlier waves of P14 complete | — |
| P14.W7 | P14-T11 | Single task | All dependencies from earlier waves of P14 complete | — |
| P14.W8 | P14-GATE | Single task | All dependencies from earlier waves of P14 complete | — |

#### P14-T01 — Cloud provider, region and residency decision

`DOC` · Size S · Wave P14.W1 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Choose AWS/GCP/OCI, region(s) and data-residency approach.
- **Depends on:** P01-GATE
- **Parallel with:** P14-T04
- **Unblocks:** P14-T02, P14-GATE
- **Deliverables:** ADR.
- **Acceptance criteria:**
  - User approves (DEC-02).
- **Verification:** User approval.
- **Subtasks:** `P14-T01.1` Options and cost · `P14-T01.2` Residency/regulatory notes · `P14-T01.3` ADR

#### P14-T02 — Terraform foundation

`INF` · Size L · Wave P14.W2 · Approval: no

- **Objective:** State backend, network, IAM and environment modules (dev/staging/prod).
- **Depends on:** P14-T01
- **Parallel with:** — (sequential)
- **Unblocks:** P14-T03, P14-T06, P14-GATE
- **Deliverables:** infrastructure/terraform.
- **Acceptance criteria:**
  - `terraform validate` and plan are clean; no secrets in state outputs.
- **Verification:** CK-INF
- **Subtasks:** `P14-T02.1` State backend · `P14-T02.2` Network · `P14-T02.3` IAM · `P14-T02.4` Env modules

#### P14-T03 — Managed data services

`INF` · Size L · Wave P14.W3 · Approval: no

- **Objective:** PostgreSQL, Redis, object storage and queue via Terraform.
- **Depends on:** P14-T02
- **Parallel with:** P14-T06
- **Unblocks:** P14-T05, P14-T10, P14-GATE
- **Deliverables:** Terraform modules.
- **Acceptance criteria:**
  - Encryption at rest; private networking; backups enabled.
- **Verification:** CK-INF
- **Subtasks:** `P14-T03.1` PostgreSQL · `P14-T03.2` Redis · `P14-T03.3` Object storage · `P14-T03.4` Queue

#### P14-T04 — Container images and registry

`INF` · Size M · Wave P14.W1 · Approval: no

- **Objective:** Multi-stage, non-root images with scan and SBOM.
- **Depends on:** P01-T07, P01-T11, P01-GATE
- **Parallel with:** P14-T01
- **Unblocks:** P14-T05, P14-GATE
- **Deliverables:** Dockerfiles, registry workflow.
- **Acceptance criteria:**
  - Image scan has no unwaived high/critical findings.
- **Verification:** CK-S
- **Subtasks:** `P14-T04.1` Dockerfiles · `P14-T04.2` Registry push · `P14-T04.3` Scan and SBOM

#### P14-T05 — Compute platform and ingress

`INF` · Size L · Wave P14.W4 · Approval: no

- **Objective:** Managed container service, TLS ingress and autoscaling.
- **Depends on:** P14-T03, P14-T04
- **Parallel with:** — (sequential)
- **Unblocks:** P14-T07, P14-T08, P14-T09, P14-GATE
- **Deliverables:** Terraform modules.
- **Acceptance criteria:**
  - TLS 1.2+ only; health checks gate rollout.
- **Verification:** CK-INF
- **Subtasks:** `P14-T05.1` Service · `P14-T05.2` Ingress/TLS · `P14-T05.3` Autoscaling

#### P14-T06 — Secrets management and CI-to-cloud trust

`SEC` · Size M · Wave P14.W3 · Approval: no

- **Objective:** Secret manager, rotation policy and OIDC-based CI authentication.
- **Depends on:** P14-T02
- **Parallel with:** P14-T03
- **Unblocks:** P14-T07, P14-GATE
- **Deliverables:** Terraform and workflow changes.
- **Acceptance criteria:**
  - No long-lived cloud keys in GitHub secrets.
- **Verification:** CK-INF, CK-S
- **Subtasks:** `P14-T06.1` Secret manager · `P14-T06.2` Rotation · `P14-T06.3` CI OIDC

#### P14-T07 — Production Keycloak deployment

`INF` · Size L · Wave P14.W5 · Approval: no

- **Objective:** HA Keycloak with managed DB, SMTP and realm import.
- **Depends on:** P14-T05, P14-T06, P04-T01
- **Parallel with:** P14-T09, P14-T10
- **Unblocks:** P14-T08, P14-GATE
- **Deliverables:** Terraform and config.
- **Acceptance criteria:**
  - Mobile PKCE flow works against staging.
- **Verification:** Manual sign-in test
- **Subtasks:** `P14-T07.1` Deployment · `P14-T07.2` DB and SMTP · `P14-T07.3` Realm import

#### P14-T08 — CD pipelines

`INF` · Size L · Wave P14.W6 · Approval: no

- **Objective:** Build, scan, deploy to staging, run migrations, manual production promotion and rollback.
- **Depends on:** P14-T05, P14-T07
- **Parallel with:** — (sequential)
- **Unblocks:** P14-T11, P14-GATE, P16-T03
- **Deliverables:** Workflows.
- **Acceptance criteria:**
  - Rollback tested; migrations run as a gated job.
  - Staging job runs only after build/test/security/integration jobs succeed.
  - Production job needs a protected-environment manual approval and a `track.py qg require` check of the production start gates.
- **Verification:** Pipeline run
- **Subtasks:** `P14-T08.1` Staging deploy · `P14-T08.2` Migration job · `P14-T08.3` Production approval and gate check · `P14-T08.4` Promotion and rollback

#### P14-T09 — Observability stack

`INF` · Size L · Wave P14.W5 · Approval: no

- **Objective:** Prometheus/Grafana/OTel collector/Sentry with alerts and SLOs.
- **Depends on:** P14-T05, P01-T12
- **Parallel with:** P14-T07, P14-T10
- **Unblocks:** P14-T11, P14-GATE, P15-T09
- **Deliverables:** Dashboards and alert rules.
- **Acceptance criteria:**
  - Alert fires in a controlled failure test.
- **Verification:** Failure drill
- **Subtasks:** `P14-T09.1` Metrics/traces/logs · `P14-T09.2` Dashboards · `P14-T09.3` Alerts and SLOs

#### P14-T10 — Backup, restore and disaster recovery

`INF` · Size M · Wave P14.W5 · Approval: **USER REVIEW REQUIRED**

- **Objective:** PITR backups, restore test and RPO/RTO targets.
- **Depends on:** P14-T03
- **Parallel with:** P14-T07, P14-T09
- **Unblocks:** P14-GATE, P15-T09
- **Deliverables:** Runbook.
- **Acceptance criteria:**
  - Restore to a clean environment verified with row counts and checksums.
- **Verification:** Restore drill
- **Subtasks:** `P14-T10.1` Backups · `P14-T10.2` Restore test · `P14-T10.3` Runbook

#### P14-T11 — Staging verification (staging release gate)

`QA` · Size M · Wave P14.W7 · Approval: no

- **Objective:** Deploy the full stack to staging and run smoke tests. Staging deployment requires successful build, test, security and integration gates (spec 8.4).
- **Depends on:** P14-T08, P14-T09
- **Parallel with:** — (sequential)
- **Unblocks:** P14-GATE
- **Deliverables:** Smoke report.
- **Acceptance criteria:**
  - Start gates satisfied before deploying (recorded in evidence).
  - Smoke suite passes on staging; TLS and auth verified.
  - Deployment health checks pass.
  - Multi-currency reporting (P11) smoke tests pass on staging: switch reporting currency, rate status and timestamps, converter, provider fallback.
  - If phase P13 (Forex) is complete, its smoke tests (stream connect and reconnect, stale-data banner, paper-trade round trip, risk calculation) pass on staging; the Forex feature flag stays off in production until they do.
- **Verification:** Smoke tests; `python scripts/track.py qg require <start gates>`
- **Quality gates required before start:** QG-02.1, QG-02.2, QG-02.3, QG-02.4, QG-03.1, QG-03.2, QG-03.6, QG-08.3, QG-08.4, QG-08.6, QG-11.1, QG-11.2, QG-11.5
- **Subtasks:** `P14-T11.1` Check start gates · `P14-T11.2` Deploy · `P14-T11.3` Smoke · `P14-T11.4` Report

#### P14-GATE — Phase P14 exit gate

`GATE` · Size S · Wave P14.W8 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Confirm infrastructure.
- **Depends on:** P14-T01, P14-T02, P14-T03, P14-T04, P14-T05, P14-T06, P14-T07, P14-T08, P14-T09, P14-T10, P14-T11
- **Parallel with:** — (sequential)
- **Unblocks:** P15-T01, P15-T02, P15-T04, P15-T05, P15-T06
- **Deliverables:** Gate summary.
- **Acceptance criteria:**
  - User approval recorded.
- **Verification:** CK-INF, CK-S.
- **Quality gates required before completion:** QG-08.4, QG-08.5, QG-08.7, QG-10.2, QG-10.4, QG-10.5, QG-10.6, QG-10.7, QG-10.8
- **Subtasks:** `P14-GATE.1` Run gates · `P14-GATE.2` Present summary · `P14-GATE.3` Record approval

### P15 — Production Hardening & Quality Assurance

- **Goal:** Independent security review, load testing, privacy workflows, accessibility QA and production readiness.
- **Entry criteria:** P09-GATE, P10-GATE, P12-GATE and P14-GATE complete.
- **Exit criteria:** Findings remediated or accepted; go/no-go approved by the user.
- **Prerequisite phases:** P09, P10, P11, P12, P14 · **Lane:** HARDENING
- **Entry gates:** prerequisite phase gates completed (P09, P10, P11, P12, P14); cumulative quality criteria QG-01.1,2,3,5; QG-02.1–6; QG-03.1–6; QG-04.1–5; QG-05.1–4; QG-06.1–7; QG-07.1–8; QG-08.1,3,4,5,6,7; QG-09.5; QG-10.1–8; QG-11.1–6; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria.
- **Exit gates:** QG-01.4; QG-04.6; QG-05.5; QG-08.2,8; QG-09.1,2,3,4,6; QG-12.1,3,4,7 (required by `P15-GATE`) plus user review.
- **Release gates:** —

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P15.W1 | P15-T01, P15-T02, P15-T04, P15-T05, P15-T06 | Parallel-safe | Phase approved and cross-phase prerequisites complete | Review/test tasks write reports and test code, not application code. |
| P15.W2 | P15-T03, P15-T08, P15-T09 | Parallel-safe | All dependencies from earlier waves of P15 complete | — |
| P15.W3 | P15-T07 | Single task | All dependencies from earlier waves of P15 complete | — |
| P15.W4 | P15-T11 | Single task | All dependencies from earlier waves of P15 complete | — |
| P15.W5 | P15-T10 | Single task | All dependencies from earlier waves of P15 complete | — |
| P15.W6 | P15-GATE | Single task | All dependencies from earlier waves of P15 complete | — |

#### P15-T01 — OWASP API Security review

`SEC` · Size L · Wave P15.W1 · Approval: no

- **Objective:** Review the API against the OWASP API Top 10.
- **Depends on:** P09-GATE, P10-GATE, P11-GATE, P12-GATE, P14-GATE
- **Parallel with:** P15-T02, P15-T04, P15-T05, P15-T06
- **Unblocks:** P15-T03, P15-T08, P15-GATE
- **Deliverables:** Findings register and fixes.
- **Acceptance criteria:**
  - No open high findings.
- **Verification:** CK-B, CK-S
- **Subtasks:** `P15-T01.1` Checklist · `P15-T01.2` IDOR sweep · `P15-T01.3` Fixes

#### P15-T02 — OWASP MASVS mobile review

`SEC` · Size L · Wave P15.W1 · Approval: no

- **Objective:** MASVS L1/L2 review of the app.
- **Depends on:** P09-GATE, P10-GATE, P11-GATE, P12-GATE, P14-GATE
- **Parallel with:** P15-T01, P15-T04, P15-T05, P15-T06
- **Unblocks:** P15-T03, P15-T08, P15-GATE
- **Deliverables:** Findings register and fixes.
- **Acceptance criteria:**
  - Storage, network and platform controls verified; no open high findings.
- **Verification:** CK-M, CK-S
- **Subtasks:** `P15-T02.1` Checklist · `P15-T02.2` Storage/network audit · `P15-T02.3` Fixes

#### P15-T03 — Independent penetration test

`SEC` · Size L · Wave P15.W2 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Run and remediate a penetration test (DEC-11).
- **Depends on:** P15-T01, P15-T02
- **Parallel with:** P15-T08, P15-T09
- **Unblocks:** P15-T07, P15-T10, P15-T11, P15-GATE
- **Deliverables:** Report and remediation.
- **Acceptance criteria:**
  - All high/critical findings fixed or formally accepted.
- **Verification:** Retest
- **Subtasks:** `P15-T03.1` Scope · `P15-T03.2` Test · `P15-T03.3` Remediate

#### P15-T04 — Performance and load testing

`QA` · Size L · Wave P15.W1 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Measure latency and capacity incl. AI latency and cost.
- **Depends on:** P09-GATE, P10-GATE, P11-GATE, P12-GATE, P14-GATE
- **Parallel with:** P15-T01, P15-T02, P15-T05, P15-T06
- **Unblocks:** P15-T09, P15-GATE
- **Deliverables:** Load-test results and tuning.
- **Acceptance criteria:**
  - Targets agreed with the user are met.
- **Verification:** k6/Locust run
- **Subtasks:** `P15-T04.1` Confirm targets from docs/quality-targets.md · `P15-T04.2` API and database load scenarios · `P15-T04.3` Mobile start-up, memory and crash measurements on devices · `P15-T04.4` Capacity assumptions and bottlenecks · `P15-T04.5` Tuning

#### P15-T05 — Privacy and compliance workflows

`BE` · Size L · Wave P15.W1 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Data export, account deletion, retention and consent.
- **Depends on:** P09-GATE, P10-GATE, P11-GATE, P12-GATE, P14-GATE
- **Parallel with:** P15-T01, P15-T02, P15-T04, P15-T06
- **Unblocks:** P15-T07, P15-GATE
- **Deliverables:** Endpoints, jobs, policies.
- **Acceptance criteria:**
  - Deletion removes or anonymises user data per policy and is audited.
- **Verification:** CK-B
- **Subtasks:** `P15-T05.1` Export · `P15-T05.2` Deletion · `P15-T05.3` Retention · `P15-T05.4` Policies

#### P15-T06 — Accessibility QA (UX Gate 5)

`QA` · Size L · Wave P15.W1 · Approval: **USER REVIEW REQUIRED**

- **Objective:** TalkBack/VoiceOver, dynamic type, RTL, reduced motion and contrast on real devices; compare with concept board.
- **Depends on:** P09-GATE, P10-GATE, P11-GATE, P12-GATE, P14-GATE
- **Parallel with:** P15-T01, P15-T02, P15-T04, P15-T05
- **Unblocks:** P15-T07, P15-GATE
- **Deliverables:** Completed QA report.
- **Acceptance criteria:**
  - No blocking accessibility defects on Android and iOS.
- **Verification:** CK-M, CK-I; manual
- **Subtasks:** `P15-T06.1` Android · `P15-T06.2` iOS · `P15-T06.3` Report

#### P15-T07 — Full regression and E2E on staging

`QA` · Size L · Wave P15.W3 · Approval: no

- **Objective:** Run all suites on staging.
- **Depends on:** P15-T03, P15-T05, P15-T06
- **Parallel with:** — (sequential)
- **Unblocks:** P15-T10, P15-T11, P15-GATE
- **Deliverables:** Regression report.
- **Acceptance criteria:**
  - All suites green; no open blockers.
- **Verification:** CK-B, CK-M, CK-I
- **Subtasks:** `P15-T07.1` Backend · `P15-T07.2` Mobile · `P15-T07.3` E2E

#### P15-T08 — Final dependency and licence audit

`SEC` · Size M · Wave P15.W2 · Approval: no

- **Objective:** CVE triage, licence check and pinned versions.
- **Depends on:** P15-T01, P15-T02
- **Parallel with:** P15-T03, P15-T09
- **Unblocks:** P15-T10, P15-T11, P15-GATE
- **Deliverables:** SBOM and report.
- **Acceptance criteria:**
  - No unwaived high/critical CVEs.
- **Verification:** CK-S
- **Subtasks:** `P15-T08.1` Audit · `P15-T08.2` Triage

#### P15-T09 — Operational readiness

`INF` · Size M · Wave P15.W2 · Approval: no

- **Objective:** Runbooks, incident process and executed DR drill.
- **Depends on:** P14-T09, P14-T10, P15-T04
- **Parallel with:** P15-T03, P15-T08
- **Unblocks:** P15-T10, P15-T11, P15-GATE
- **Deliverables:** Runbooks and drill record.
- **Acceptance criteria:**
  - On-call and escalation defined; DR drill within RTO.
- **Verification:** Drill
- **Subtasks:** `P15-T09.1` Runbooks · `P15-T09.2` Incident process · `P15-T09.3` DR drill

#### P15-T10 — Production readiness review

`DOC` · Size M · Wave P15.W5 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Compare against MVP acceptance criteria (brief section 16) and the quality-gate register.
- **Depends on:** P15-T03, P15-T07, P15-T08, P15-T09, P15-T11
- **Parallel with:** — (sequential)
- **Unblocks:** P15-GATE
- **Deliverables:** Go/no-go document.
- **Acceptance criteria:**
  - Every MVP criterion has evidence.
- **Verification:** User decision
- **Subtasks:** `P15-T10.1` Criteria matrix · `P15-T10.2` Risk register · `P15-T10.3` Go/no-go

#### P15-T11 — Final quality-gate re-verification

`QA` · Size L · Wave P15.W4 · Approval: no

- **Objective:** Re-run every automated gate and re-verify every QG criterion due at or before P15 against the current release candidate (spec 8.5).
- **Depends on:** P15-T03, P15-T07, P15-T08, P15-T09
- **Parallel with:** — (sequential)
- **Unblocks:** P15-T10, P15-GATE
- **Deliverables:** Updated Verification timestamps and evidence in QUALITY_GATES.md; list of failures with remediation tasks.
- **Acceptance criteria:**
  - Every QG-01..QG-11 criterion due by P15 is satisfied on the release candidate, or the failure is recorded and blocks release.
  - `track.py qg check QG-12.1` succeeds.
- **Verification:** All CK suites; `python scripts/track.py qg status`
- **Subtasks:** `P15-T11.1` Re-run all CK suites · `P15-T11.2` Re-verify criteria with fresh evidence · `P15-T11.3` Record failures and remediation · `P15-T11.4` qg check QG-12.1

#### P15-GATE — Phase P15 exit gate

`GATE` · Size S · Wave P15.W6 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Confirm readiness.
- **Depends on:** P15-T01, P15-T02, P15-T03, P15-T04, P15-T05, P15-T06, P15-T07, P15-T08, P15-T09, P15-T10, P15-T11
- **Parallel with:** — (sequential)
- **Unblocks:** P16-T01, P16-T03
- **Deliverables:** Gate summary.
- **Acceptance criteria:**
  - User go decision recorded.
- **Verification:** All quality gates.
- **Quality gates required before completion:** QG-01.4, QG-04.6, QG-05.5, QG-08.2, QG-08.8, QG-09.1, QG-09.2, QG-09.3, QG-09.4, QG-09.6, QG-12.1, QG-12.3, QG-12.4, QG-12.7
- **Subtasks:** `P15-GATE.1` Run gates · `P15-GATE.2` Present summary · `P15-GATE.3` Record decision

### P16 — Release & Production Deployment

- **Goal:** Store accounts, signed release builds, production deployment, store submission, staged rollout and hypercare.
- **Entry criteria:** P15-GATE complete; DEC-09 (developer accounts) ideally started during P09.
- **Exit criteria:** App live on Google Play and the App Store with monitoring and a support process.
- **Prerequisite phases:** P15 · **Lane:** RELEASE
- **Entry gates:** prerequisite phase gates completed (P15); cumulative quality criteria QG-01.1–5; QG-02.1–6; QG-03.1–6; QG-04.1–6; QG-05.1–5; QG-06.1–7; QG-07.1–8; QG-08.1–8; QG-09.1–6; QG-10.1–8; QG-11.1–6; QG-12.1,3,4,7; user approval of the phase.
- **Task-level gates:** each task's CK suites and acceptance criteria; additionally quality criteria: P16-T03 → QG-12.5.
- **Exit gates:** QG-04.7; QG-05.6; QG-12.2,5,6,8 (required by `P16-GATE`) plus user review.
- **Release gates:** P16-T03 → start: QG-all@P15, QG-12.1, QG-12.3, QG-12.4, QG-12.7, QG-12.8; P16-T07 → start: QG-all@P16, QG-12.2, QG-12.5, QG-12.6, QG-12.8

| Wave | Tasks | Mode | Entry condition | Conflict notes |
|---|---|---|---|---|
| P16.W1 | P16-T01, P16-T03 | Parallel-safe | Phase approved and cross-phase prerequisites complete | T01 is mostly user/administrative; T03 is infrastructure. |
| P16.W2 | P16-T02 | Single task | All dependencies from earlier waves of P16 complete | — |
| P16.W3 | P16-T04, P16-T05 | Parallel-safe | All dependencies from earlier waves of P16 complete | — |
| P16.W4 | P16-T06 | Single task | All dependencies from earlier waves of P16 complete | — |
| P16.W5 | P16-T07 | Single task | All dependencies from earlier waves of P16 complete | — |
| P16.W6 | P16-T08 | Single task | All dependencies from earlier waves of P16 complete | — |
| P16.W7 | P16-GATE | Single task | All dependencies from earlier waves of P16 complete | — |

#### P16-T01 — Store accounts, identifiers and signing

`REL` · Size M · Wave P16.W1 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Apple Developer and Google Play accounts, app IDs, signing keys in secret store, privacy/data-safety forms.
- **Depends on:** P15-GATE
- **Parallel with:** P16-T03
- **Unblocks:** P16-T02, P16-GATE
- **Deliverables:** Accounts and signing assets ready.
- **Acceptance criteria:**
  - Keys are stored only in the secret manager; builds can be signed in CI.
- **Verification:** Dry-run signed build
- **Subtasks:** `P16-T01.1` Accounts · `P16-T01.2` Signing · `P16-T01.3` Forms

#### P16-T02 — Release builds and pipeline

`REL` · Size L · Wave P16.W2 · Approval: no

- **Objective:** Android AAB and iOS IPA with versioning and automated upload.
- **Depends on:** P16-T01
- **Parallel with:** — (sequential)
- **Unblocks:** P16-T04, P16-T05, P16-GATE
- **Deliverables:** Release workflow.
- **Acceptance criteria:**
  - Reproducible signed builds from CI.
- **Verification:** CI release run
- **Subtasks:** `P16-T02.1` Android · `P16-T02.2` iOS · `P16-T02.3` Versioning

#### P16-T03 — Production infrastructure deployment (production release gate)

`INF` · Size L · Wave P16.W1 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Deploy production via pipeline, run migrations, configure Keycloak and monitoring.
- **Depends on:** P15-GATE, P14-T08
- **Parallel with:** P16-T01
- **Unblocks:** P16-T04, P16-GATE
- **Deliverables:** Production environment.
- **Acceptance criteria:**
  - All quality criteria due by P15 and QG-12.1/.3/.4/.7/.8 satisfied before deployment starts.
  - Smoke tests pass; backups verified; monitoring active.
- **Verification:** Smoke tests; `track.py qg require QG-all@P15 QG-12.3 QG-12.4 QG-12.7 QG-12.8`
- **Quality gates required before start:** QG-all@P15, QG-12.1, QG-12.3, QG-12.4, QG-12.7, QG-12.8
- **Quality gates required before completion:** QG-12.5
- **Subtasks:** `P16-T03.1` Check release gates · `P16-T03.2` Deploy · `P16-T03.3` Migrate · `P16-T03.4` Verify

#### P16-T04 — Internal and closed testing

`REL` · Size L · Wave P16.W3 · Approval: no

- **Objective:** Play internal track and TestFlight; triage and fix feedback.
- **Depends on:** P16-T02, P16-T03
- **Parallel with:** P16-T05
- **Unblocks:** P16-T06, P16-GATE
- **Deliverables:** Test report.
- **Acceptance criteria:**
  - No open blocker or critical defects.
- **Verification:** Test report
- **Subtasks:** `P16-T04.1` Distribute · `P16-T04.2` Collect feedback · `P16-T04.3` Fix

#### P16-T05 — Store listings and policy compliance

`REL` · Size M · Wave P16.W3 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Screenshots, descriptions, privacy and financial-app declarations.
- **Depends on:** P16-T02
- **Parallel with:** P16-T04
- **Unblocks:** P16-T06, P16-GATE
- **Deliverables:** Store listings.
- **Acceptance criteria:**
  - Listings avoid guaranteed-return language; declarations complete.
- **Verification:** Store pre-checks
- **Subtasks:** `P16-T05.1` Assets · `P16-T05.2` Copy · `P16-T05.3` Declarations

#### P16-T06 — Launch rehearsal and checklist

`QA` · Size M · Wave P16.W4 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Go-live rehearsal and rollback plan.
- **Depends on:** P16-T04, P16-T05
- **Parallel with:** — (sequential)
- **Unblocks:** P16-T07, P16-GATE
- **Deliverables:** Launch checklist.
- **Acceptance criteria:**
  - Rehearsal passes; rollback tested.
- **Verification:** Rehearsal
- **Subtasks:** `P16-T06.1` Checklist · `P16-T06.2` Rehearsal · `P16-T06.3` Rollback

#### P16-T07 — Store submission and staged rollout

`REL` · Size M · Wave P16.W5 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Submit and roll out in stages.
- **Depends on:** P16-T06
- **Parallel with:** — (sequential)
- **Unblocks:** P16-T08, P16-GATE
- **Deliverables:** Live app versions.
- **Acceptance criteria:**
  - All release-build criteria satisfied before submission.
  - Approved by both stores; staged rollout started.
- **Verification:** Store consoles; `track.py qg require QG-all@P16 QG-12.2 QG-12.5 QG-12.6 QG-12.8`
- **Quality gates required before start:** QG-all@P16, QG-12.2, QG-12.5, QG-12.6, QG-12.8
- **Subtasks:** `P16-T07.1` Check release gates · `P16-T07.2` Submit · `P16-T07.3` Staged rollout

#### P16-T08 — Post-launch monitoring and hypercare

`REL` · Size M · Wave P16.W6 · Approval: no

- **Objective:** Watch dashboards, crash and error rates; run support process; retrospective.
- **Depends on:** P16-T07
- **Parallel with:** — (sequential)
- **Unblocks:** P16-GATE
- **Deliverables:** Hypercare report.
- **Acceptance criteria:**
  - Error budget respected for the agreed period.
- **Verification:** Dashboards
- **Subtasks:** `P16-T08.1` Monitoring · `P16-T08.2` Support · `P16-T08.3` Retrospective

#### P16-GATE — Release sign-off

`GATE` · Size S · Wave P16.W7 · Approval: **USER REVIEW REQUIRED**

- **Objective:** Close the programme.
- **Depends on:** P16-T01, P16-T02, P16-T03, P16-T04, P16-T05, P16-T06, P16-T07, P16-T08
- **Parallel with:** — (sequential)
- **Unblocks:** —
- **Deliverables:** Release summary.
- **Acceptance criteria:**
  - User sign-off recorded.
- **Verification:** All gates.
- **Quality gates required before completion:** QG-04.7, QG-05.6, QG-12.2, QG-12.5, QG-12.6, QG-12.8
- **Subtasks:** `P16-GATE.1` Run gates · `P16-GATE.2` Present summary · `P16-GATE.3` Record sign-off

## Appendix A — Requirement traceability

| Requirement (source) | Delivered by |
|---|---|
| Design tokens, themes, shared component library (UI spec) | P02-T01…T08 |
| Forex Trading Intelligence module: market dashboard, predictions, technical analysis, economic calendar, Opportunity Ranking Dashboard, trade-risk engine, backtesting, paper trading, Forex Copilot (extension request, 2026-10-09) | P13-T01…T14 (FX-01…FX-14); gates QG-13…QG-20 (QG-FX-01…08) |
| Multi-currency reporting: global reporting currency, FX provider service, conversion engine, historical rates, converter, AI currency tools (request 2026-10-10) | P11-T01…T12 (FXCUR-01…FXCUR-12); gates QG-21…QG-25; extends P05-T06, P08-T05 |
| Screen 1 Welcome/Onboarding, 2 Sign In/Up | P04-T08 |
| Screen 3 Home Dashboard | P03-T02 → live P09-T02 |
| Screen 4 Portfolio Overview | P03-T03 → live P09-T02 |
| Screen 5 Investments/Holdings | P07-T02 → live P09-T04 |
| Screen 6 AI Wealth Copilot | P03-T06 → live P10-T10 |
| Screen 7 Investment Details | P07-T04 → live P09-T04/T07 |
| Screen 8 Transactions | P07-T03 → live P09-T04 |
| Screen 9 Compounding Calculator / 10 Wealth Forecast | P03-T04/T05 → live P09-T03; engine P06-T01/T02 |
| Screen 11 Financial Goals | P07-T05 → live P09-T05; backend P06-T06 |
| Screen 12 Portfolio Doctor | P07-T06 → live P12-T01/T09 |
| Screen 13 AI Investment Opportunities | P07-T07 → live P12-T06/T07/T09 |
| Identity, OIDC+PKCE, MFA, biometrics | P04-T01, T02, T06, T07 |
| Server-side authorisation, IDOR tests, audit trail | P04-T03/T04, P05-T09, P10-T02 |
| Portfolios, assets, transactions, holdings, valuations | P05-T01…T08 |
| Multi-currency with FX provenance | P05-T06, P08-T05 |
| Analytics (return, CAGR, XIRR, TWR, allocation, concentration, volatility, drawdown) | P06-T03, T04, T08, T09 |
| Compound growth and goal forecasting | P06-T01, T02, T06 |
| Passive income, net worth, liabilities | P06-T05, T07 |
| Market data, FX, history, watchlists, alerts | P08-T01…T09, P09-T07 |
| Notifications and deep links | P09-T08 |
| Offline / stale-data behaviour | P09-T06 |
| AI tool layer, orchestrator, Copilot, AI audit | P10-T01…T10 |
| AI Investment Intelligence, Portfolio Doctor, Compare, Simulate | P12-T01…T10 |
| Privacy: export, deletion, retention | P15-T05 |
| CI/CD and security scanning | P01-T09…T11, P14-T08 |
| Cloud infrastructure, secrets, backup/DR, observability | P14-T01…T11, P01-T12 |
| OWASP MASVS / API review, pen test, load test | P15-T01…T04 |
| Accessibility QA (UX gate 5) | P03-T07, P07-T09, P15-T06 |
| App Store / Google Play release | P16-T01…T08 |
| Mandatory platform quality gates QG-01…QG-12 (spec section 8) | QUALITY_GATES.md; bound to phase gates (§7.3); P00-T04, P01-T15, P01-T16, P15-T11; release gates P14-T11, P16-T03, P16-T07 |
| Brief phases 0–6 / CLAUDE.md 17-step order / SOLUTION_INTENT phases 0–10 | P01 (0), P04–P05 (1–2), P06 (3–5), P08 (6), P10 (7–8), P12 (9), P14–P16 (10) |

## Appendix B — UI plan step mapping

| `docs/UI_EXECUTION_PLAN.md` | This plan |
|---|---|
| Step 0 | P01-T02, P01-T03 |
| Step 1 | P01-T06, P01-T10 |
| Step 2 | P02-T01 |
| Step 3 | P02-T02 |
| Step 4 | P02-T03, P02-T04 |
| Step 5 | P02-T05 |
| Step 6 | P02-T06 |
| Step 7 | P02-T07 |
| Step 8 | P02-T08, P02-GATE |
| Step 9 | P03-T01 |
| Step 10 | P03-T02 |
| Step 11 | P03-T03 |
| Step 12 | P03-T04 |
| Step 13 | P03-T05 |
| Step 14 | P03-T06 |
| Step 15 | P03-T07, P03-GATE |
