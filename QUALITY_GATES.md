# WealthSphere — Quality Gates Register

**This file is the authoritative quality-gate register.** It is edited only through `python scripts/track.py qg …`, which records timestamps from the system clock, requires evidence for every verification, and refreshes PROGRESS_DASHBOARD.md and EXECUTION_LOG.md. Never fabricate checks, timestamps, coverage figures or approvals.

Gate statuses: `NOT_STARTED` · `IN_PROGRESS` · `BLOCKED` · `FAILED` · `PASSED` · `WAIVED`. A criterion is satisfied when it is ticked with evidence or covered by an active waiver. Each criterion shows the phase in which it first becomes required (`Required`), the task that produces its evidence (`By`) and `CRITICAL` where a waiver is not permitted. Phase exit gates (`Pnn-GATE`) require the criteria due in their phase; see EXECUTION_PLAN.md section 7.

## Summary

<!-- QG-AUTO:BEGIN -->
_Generated at 2026-10-10T02:04:39+04:00 by `scripts/track.py`._

| Gate | Name | Status | Criteria satisfied | Owner | Blocking issues |
|---|---|---|---|---|---|
| QG-01 | Architecture and Design | 🔄 IN_PROGRESS | 3/5 | Unassigned | — |
| QG-02 | Code Quality | ✅ PASSED | 6/6 | Unassigned | — |
| QG-03 | Automated Testing | 🔄 IN_PROGRESS | 2/6 | Unassigned | — |
| QG-04 | Android Platform | 🔄 IN_PROGRESS | 3/7 | Unassigned | — |
| QG-05 | iOS Platform | 🔄 IN_PROGRESS | 2/6 | Unassigned | — |
| QG-06 | Financial Accuracy and Data Integrity | ⬜ NOT_STARTED | 0/7 | Unassigned | — |
| QG-07 | AI Reliability and Investment Intelligence | ⬜ NOT_STARTED | 0/8 | Unassigned | — |
| QG-08 | Security and Privacy | 🔄 IN_PROGRESS | 2/8 | Unassigned | — |
| QG-09 | Performance and Scalability | ⬜ NOT_STARTED | 0/6 | Unassigned | — |
| QG-10 | CI/CD and Infrastructure | 🔄 IN_PROGRESS | 2/8 | Unassigned | — |
| QG-11 | End-to-End Integration | ⬜ NOT_STARTED | 0/6 | Unassigned | — |
| QG-12 | Production Release Readiness | ⬜ NOT_STARTED | 0/8 | Unassigned | — |
| QG-13 | QG-FX-01: Market Data Integrity | ⬜ NOT_STARTED | 0/5 | Unassigned | — |
| QG-14 | QG-FX-02: Technical Indicator Accuracy | ⬜ NOT_STARTED | 0/3 | Unassigned | — |
| QG-15 | QG-FX-03: Prediction Model Validation | ⬜ NOT_STARTED | 0/6 | Unassigned | — |
| QG-16 | QG-FX-04: Trading Risk Accuracy | ⬜ NOT_STARTED | 0/5 | Unassigned | — |
| QG-17 | QG-FX-05: Backtesting Integrity | ⬜ NOT_STARTED | 0/4 | Unassigned | — |
| QG-18 | QG-FX-06: AI Trading Intelligence | ⬜ NOT_STARTED | 0/5 | Unassigned | — |
| QG-19 | QG-FX-07: Mobile Experience | ⬜ NOT_STARTED | 0/5 | Unassigned | — |
| QG-20 | QG-FX-08: Release and Regulatory Readiness | ⬜ NOT_STARTED | 0/5 | Unassigned | — |

Waivers: 0 active (0 expired — must be resolved), 0 closed.
Criteria satisfied overall: 20/119.

Current phase **P03** exit-gate criteria outstanding: QG-04.4, QG-05.3.
<!-- QG-AUTO:END -->

### QG-01: Architecture and Design

- [x] QG-01.1 Architecture complies with the approved solution intent and architectural decisions · Required: P01 · By: P01-T03 · Evidence: Architecture follows the approved solution intent: docs/architecture.md derived from SOLUTION_INTENT sections 22, 26, 27 and the implementation guide (modular monolith, backend authoritative for financial truth, allow-listed AI tools, provider abstractions); ADR-0001..0008 all Accepted by the user; 11 document conflicts (D1-D11) listed with resolutions in EXECUTION_PLAN.md section 2; plan approved at P00-GATE · Verified: 2026-10-09T18:33:56+04:00
- [x] QG-01.2 Module boundaries and dependencies are documented · Required: P01 · By: P01-T04 · Evidence: Module boundaries and dependencies documented in docs/architecture.md section 2 (11 modules, responsibility and allowed-dependency table, rule: modules call only service interfaces), ADR-0004 (backend layout: api/service/repository/schemas) and ADR-0005 (repository layout); backend/app/modules reserved for domain modules · Verified: 2026-10-09T18:33:56+04:00
- [ ] QG-01.3 API contracts and database designs are reviewed · Required: P05 · By: P05-T10
- [ ] QG-01.4 No unresolved critical architectural risks · Required: P14 · By: P14-T10
- [x] QG-01.5 UI/UX implementation follows the approved WealthSphere design system · Required: P02 · By: P02-T08 · Evidence: UX Gate 1: user reviewed the component gallery against the concept board and approved (2026-10-09). Design system per docs/design/design-system.md: tokens with measured contrast (contrast tests), shared components and 3 charts, light/dark, 2.0x text, RTL; style guard test enforces tokens (no colour literals, no left/right APIs, no double in money code); 34 golden images (28 gallery + 6 chart) compared on CI Linux; format and analyze clean, 576 tests pass locally (34 goldens skipped on Windows). TalkBack read-through of chart summaries not yet performed. · Verified: 2026-10-09T23:38:20+04:00

Status: IN_PROGRESS  
Owner: Unassigned  
Start Timestamp: 2026-10-09T18:33:56+04:00  
End Timestamp: —  
Verification Timestamp: 2026-10-09T23:38:20+04:00  
Evidence: 3/5 criteria verified; latest QG-01.5 at 2026-10-09T23:38:20+04:00  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-02: Code Quality

- [x] QG-02.1 Formatting and linting checks pass · Required: P01 · By: P01-T09,P01-T10 · Evidence: Formatting and lint pass: PR #4 required checks all green ('lint, types, tests, migrations' = ruff format --check + ruff check; 'format, analyze, test (incl. goldens)' = dart format --set-exit-if-changed + flutter analyze); pre-commit 'run --all-files' all 12 hooks Passed; negative tests showed ruff-check fails on an unused import, and a failing check blocked PR #5 from merging · Verified: 2026-10-09T18:33:56+04:00
- [x] QG-02.2 Static type checks pass · Required: P01 · By: P01-T09 · Evidence: Static types pass: mypy --strict 'Success: no issues found in 30 source files' (backend, incl. tests and OpenTelemetry/SQLAlchemy/asyncpg stubs) in CI; flutter analyze 'No issues found' with strict-casts, strict-inference and strict-raw-types in CI · Verified: 2026-10-09T18:33:56+04:00
- [x] QG-02.3 No unresolved critical or high-severity code-quality issues · Required: P01 · By: P01-T15 · Evidence: No unresolved critical/high code-quality issues: ruff (rules incl. flake8-bandit S, bugbear, asyncio) clean; mypy --strict 'no issues found in 30 source files'; CodeQL python security-extended on PR #4 and main: 0 open code-scanning alerts (GitHub API); Trivy HIGH/CRITICAL: none; dependency audit (pip-audit, OSV): none. Required-check gates now block merges (ruleset 'main protection') · Verified: 2026-10-09T18:14:49+04:00
- [x] QG-02.4 No hardcoded credentials or secrets · Required: P01 · By: P01-T11 · Evidence: No hardcoded credentials or secrets: gitleaks full-history scan in CI (fetch-depth 0) 'no leaks found' on runs 37931445813 and every later PR/push; local gitleaks history scan of 15 commits clean; Trivy secret scan clean; pre-commit gitleaks hook blocks staged secrets; SEEDED TEST: random fake key on a throwaway branch failed CI run 37931671715 (generic-api-key) and was blocked by the local hook; .env git-ignored; a JWT-shaped test fixture was replaced by runtime construction instead of suppressing the rule · Verified: 2026-10-09T18:33:57+04:00 · CRITICAL
- [x] QG-02.5 Code reviews are completed for relevant changes · Required: P01 · By: P01-T15 · Evidence: User accepted the compensating review controls of ADR-0008 in chat ('Accept these controls'): CODEOWNERS requests the maintainer on every PR (explicitly on .github/, backend/app/core/, migrations, security docs, tracker, quality-gate register); PR template with Definition of Done checklist; mandatory recorded user approval for every task flagged Approval: yes and every phase gate; independent diff review before completing tasks touching money, authorization, AI tools or migrations. Ruleset requires 0 approving reviews because the sole maintainer cannot approve own PRs; to be raised to 1 with code-owner review when a second maintainer joins. All changes land via pull requests (PR #4 merged; direct pushes rejected) · Verified: 2026-10-09T18:22:40+04:00
- [x] QG-02.6 No unexplained technical debt introduced · Required: P01 · By: P01-T13 · Evidence: No unexplained technical debt: docs/tech-debt.md lists 11 known shortcuts with risk, owner and resolve-by point, plus every inline lint/type suppression with its justification (scan of backend/ and scripts/ found 11 suppression sites, all with rule codes); PR template and CONTRIBUTING now require debt to be recorded in the same pull request. Notable entries: TD-05 tracker has no automated test suite (to be added before P02), TD-03 iOS Xcode not pinned · Verified: 2026-10-09T18:33:57+04:00

Status: PASSED  
Owner: Unassigned  
Start Timestamp: 2026-10-09T18:14:49+04:00  
End Timestamp: 2026-10-09T18:34:15+04:00  
Verification Timestamp: 2026-10-09T18:34:15+04:00  
Evidence: All six QG-02 criteria verified with evidence (formatting/lint, static types, no critical code-quality findings (CodeQL 0 alerts), no hardcoded secrets, code-review controls accepted by user, tech-debt register). Re-verified at P14-T11  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-03: Automated Testing

- [x] QG-03.1 All required unit tests pass · Required: P01 · By: P01-T09,P01-T10 · Evidence: Required unit tests pass: backend pytest 109 passed (0 skipped in CI; coverage 96.6%, per-module report in job summary) and mobile flutter test passed, in PR #4 CI and on main after merge (runs 37944172314 backend, 37944172316 mobile) · Verified: 2026-10-09T18:33:57+04:00
- [ ] QG-03.2 All required integration tests pass · Required: P05 · By: P05-T09
- [ ] QG-03.3 Relevant end-to-end tests pass · Required: P09 · By: P09-T10
- [ ] QG-03.4 Critical financial calculations achieve 100% requirement/edge-case coverage through documented test cases · Required: P06 · By: P06-T10 · CRITICAL
- [ ] QG-03.5 At least 85% automated line coverage for business-critical backend modules, without using coverage as a substitute for meaningful tests · Required: P06 · By: P06-T10
- [x] QG-03.6 No unresolved critical test failures · Required: P01 · By: P01-T15 · Evidence: No unresolved critical test failures: backend 109 passed (96.6% coverage, 0 skipped in CI incl. integration against service containers), mobile flutter test passed, all four required checks green on PR #4 (backend gate, mobile gate, security gate, tracker validate); a deliberately failing check on throwaway PR #5 made 'backend gate' fail and the merge was refused by the base-branch policy · Verified: 2026-10-09T18:14:49+04:00

Status: IN_PROGRESS  
Owner: Unassigned  
Start Timestamp: 2026-10-09T18:14:49+04:00  
End Timestamp: —  
Verification Timestamp: 2026-10-09T18:33:57+04:00  
Evidence: 2/6 criteria verified; latest QG-03.1 at 2026-10-09T18:33:57+04:00  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-04: Android Platform

- [x] QG-04.1 Android application builds successfully · Required: P01 · By: P01-T06 · Evidence: Android app builds: CI job 'android debug build' success on PR #4 and earlier runs 37931445838 / 37926752270; local flutter build apk --debug produces an APK reporting minSdkVersion 26, targetSdkVersion 36 (aapt2 badging), app id com.kmdmtisya.wealthsphere_app; installed and launched on an Android 17 emulator · Verified: 2026-10-09T18:33:58+04:00
- [x] QG-04.2 Flutter analysis and tests pass · Required: P01 · By: P01-T10 · Evidence: Flutter analysis and tests pass: flutter analyze 'No issues found', dart format clean, flutter test passed (app shell test) locally and in CI job 'format, analyze, test (incl. goldens)' on PR #4 · Verified: 2026-10-09T18:33:58+04:00
- [x] QG-04.3 Supported Android versions are explicitly documented · Required: P01 · By: P01-T16 · Evidence: docs/quality-targets.md section 1: supported Android versions documented (minimum Android 8.0 / API 26, target level tracked against Google Play policy, reference devices); approved by user 2026-10-09 · Verified: 2026-10-09T15:52:48+04:00
- [ ] QG-04.4 Navigation, responsive layouts, accessibility and lifecycle behaviour are verified · Required: P03 · By: P03-T07
- [ ] QG-04.5 Secure storage and biometric authentication work correctly · Required: P04 · By: P04-T07
- [ ] QG-04.6 App startup, crash behaviour and memory consumption meet approved performance targets · Required: P14 · By: P14-T04
- [ ] QG-04.7 Release signing and Google Play requirements are validated · Required: P15 · By: P15-T02

Status: IN_PROGRESS  
Owner: Unassigned  
Start Timestamp: 2026-10-09T15:52:48+04:00  
End Timestamp: —  
Verification Timestamp: 2026-10-09T18:33:58+04:00  
Evidence: 3/7 criteria verified; latest QG-04.2 at 2026-10-09T18:33:58+04:00  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-05: iOS Platform

- [x] QG-05.1 iOS application builds successfully using the supported Xcode toolchain · Required: P01 · By: P01-T10 · Evidence: iOS app builds: CI job 'ios compile (no codesign)' success on macOS runner image macos-26-arm64 (run 37931445838; 'Built build/ios/iphoneos/Runner.app (15.7MB)') and on PR #4, with IPHONEOS_DEPLOYMENT_TARGET 16.0 in all three Runner configurations. CAVEAT recorded as TD-03: the runner's default Xcode is used and its version is not logged or pinned yet; pinning is scheduled for P15-T02 · Verified: 2026-10-09T18:33:58+04:00
- [x] QG-05.2 Supported iOS versions and devices are documented · Required: P01 · By: P01-T16 · Evidence: docs/quality-targets.md section 1: supported iOS versions and devices documented (minimum iOS 16.0, iPhone SE 3rd gen / iPhone 15 / Pro Max classes, update policy); approved by user 2026-10-09 · Verified: 2026-10-09T15:52:49+04:00
- [ ] QG-05.3 Navigation, safe areas, accessibility and lifecycle behaviour are verified · Required: P03 · By: P03-T07
- [ ] QG-05.4 Face ID/Touch ID and Keychain storage work correctly · Required: P04 · By: P04-T07
- [ ] QG-05.5 App startup, crash behaviour and memory consumption meet approved performance targets · Required: P14 · By: P14-T04
- [ ] QG-05.6 App signing, provisioning, privacy declarations and App Store requirements are validated · Required: P15 · By: P15-T02,P15-T05

Status: IN_PROGRESS  
Owner: Unassigned  
Start Timestamp: 2026-10-09T15:52:49+04:00  
End Timestamp: —  
Verification Timestamp: 2026-10-09T18:33:58+04:00  
Evidence: 2/6 criteria verified; latest QG-05.1 at 2026-10-09T18:33:58+04:00  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-06: Financial Accuracy and Data Integrity

- [ ] QG-06.1 Financial calculations are deterministic and reproducible · Required: P06 · By: P06-T01 · CRITICAL
- [ ] QG-06.2 Decimal precision and rounding rules are tested · Required: P05 · By: P05-T05 · CRITICAL
- [ ] QG-06.3 Compound-growth calculations are verified against independently calculated reference cases · Required: P06 · By: P06-T10 · CRITICAL
- [ ] QG-06.4 Portfolio valuations, realized/unrealized gains, fees, income and currency conversions reconcile correctly · Required: P06 · By: P06-T10 · CRITICAL
- [ ] QG-06.5 Transaction history is auditable · Required: P05 · By: P05-T09 · CRITICAL
- [ ] QG-06.6 No unexplained financial reconciliation differences · Required: P06 · By: P06-T10 · CRITICAL
- [ ] QG-06.7 Historical prices and FX rates retain their timestamps and provenance · Required: P08 · By: P08-T05 · CRITICAL

Status: NOT_STARTED  
Owner: Unassigned  
Start Timestamp: —  
End Timestamp: —  
Verification Timestamp: —  
Evidence: —  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-07: AI Reliability and Investment Intelligence

- [ ] QG-07.1 AI tools enforce user authorization · Required: P10 · By: P10-T09 · CRITICAL
- [ ] QG-07.2 No unrestricted LLM database access · Required: P10 · By: P10-T02 · CRITICAL
- [ ] QG-07.3 Structured AI responses pass schema validation · Required: P10 · By: P10-T08
- [ ] QG-07.4 Investment opportunities include rationale, risks, assumptions, supporting evidence and data freshness · Required: P11 · By: P11-T06
- [ ] QG-07.5 AI does not invent market prices or guaranteed investment returns · Required: P10 · By: P10-T08 · CRITICAL
- [ ] QG-07.6 Prompt-injection and cross-user data-access tests pass · Required: P10 · By: P10-T09 · CRITICAL
- [ ] QG-07.7 Stale, missing or contradictory market data is handled safely · Required: P11 · By: P11-T08
- [ ] QG-07.8 AI output quality is assessed using documented evaluation datasets and acceptance thresholds · Required: P10 · By: P10-T09

Status: NOT_STARTED  
Owner: Unassigned  
Start Timestamp: —  
End Timestamp: —  
Verification Timestamp: —  
Evidence: —  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-08: Security and Privacy

- [ ] QG-08.1 Authentication and authorization tests pass · Required: P04 · By: P04-T09 · CRITICAL
- [ ] QG-08.2 No known unresolved critical or high-severity exploitable vulnerabilities at release · Required: P14 · By: P14-T03 · CRITICAL
- [x] QG-08.3 Secrets scanning passes · Required: P01 · By: P01-T11 · Evidence: Secrets scanning passes: gitleaks job in security.yml (full history) green on PR #4, #6, #7 and main (run 37944172283); seeded-secret test (run 37931671715) proved the scan fails when a secret is present; local pre-commit gitleaks hook also active · Verified: 2026-10-09T18:33:58+04:00 · CRITICAL
- [ ] QG-08.4 Dependency and container vulnerability scanning passes · Required: P13 · By: P13-T04
- [ ] QG-08.5 Encryption in transit and at rest is verified · Required: P13 · By: P13-T03,P13-T05 · CRITICAL
- [x] QG-08.6 Sensitive financial data is excluded from inappropriate logs · Required: P01 · By: P01-T12 · Evidence: Sensitive data excluded from logs: app/core/redaction.py applied to every log record (messages, extra fields, exception text); tests/test_redaction.py covers 15 leak cases (bearer, JWT, URL/DSN credentials incl. redis://:pw@host, password/secret/api_key/token pairs, financial amount/balance/price/net_worth), 5 clean-text cases, key detection, recursion, depth cap and an end-to-end log line; live server log showed no password; found and fixed the empty-username URL gap. Baseline mechanism; re-verified on the release candidate at P14-T11 · Verified: 2026-10-09T18:33:59+04:00 · CRITICAL
- [ ] QG-08.7 Backup and restore procedures are tested · Required: P13 · By: P13-T10
- [ ] QG-08.8 Privacy, retention, consent and account-deletion requirements are verified · Required: P14 · By: P14-T05 · CRITICAL

Status: IN_PROGRESS  
Owner: Unassigned  
Start Timestamp: 2026-10-09T18:33:58+04:00  
End Timestamp: —  
Verification Timestamp: 2026-10-09T18:33:59+04:00  
Evidence: 2/8 criteria verified; latest QG-08.6 at 2026-10-09T18:33:59+04:00  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-09: Performance and Scalability

- [ ] QG-09.1 API response times meet defined service-level objectives · Required: P14 · By: P14-T04
- [ ] QG-09.2 Database queries meet approved performance thresholds · Required: P14 · By: P14-T04
- [ ] QG-09.3 Mobile startup and interaction latency meet agreed targets · Required: P14 · By: P14-T04
- [ ] QG-09.4 Load and stress tests pass against representative workloads · Required: P14 · By: P14-T04
- [ ] QG-09.5 Background jobs, retries and failure recovery operate correctly · Required: P08 · By: P08-T08
- [ ] QG-09.6 Capacity assumptions and bottlenecks are documented · Required: P14 · By: P14-T04

Status: NOT_STARTED  
Owner: Unassigned  
Start Timestamp: —  
End Timestamp: —  
Verification Timestamp: —  
Evidence: —  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-10: CI/CD and Infrastructure

- [x] QG-10.1 CI pipelines pass · Required: P01 · By: P01-T09,P01-T10 · Evidence: CI pipelines pass: workflows backend, mobile, security, tracker all success on main after the last merge (runs 37944172314, 37944172316, 37944172283, 37944172361 on f525b80) and all four required gate checks green on PRs #4, #6, #7; ruleset blocks merges otherwise (PR #5 demonstration) · Verified: 2026-10-09T18:33:59+04:00
- [ ] QG-10.2 Build artifacts are reproducible and versioned · Required: P13 · By: P13-T04
- [x] QG-10.3 Database migrations are validated · Required: P01 · By: P01-T08 · Evidence: Database migrations validated: baseline revision 0001 (pgcrypto, vector); CI step 'Migrations' runs alembic upgrade head, check ('No new upgrade operations detected'), downgrade base, upgrade head and asserts a single head; pytest round-trip on a throwaway database, single-head and no-credentials-in-migrations tests; local CLI cycle on a scratch database · Verified: 2026-10-09T18:33:59+04:00
- [ ] QG-10.4 Infrastructure changes are reviewed · Required: P13 · By: P13-T02
- [ ] QG-10.5 Deployment health checks pass · Required: P13 · By: P13-T11
- [ ] QG-10.6 Monitoring, logs, metrics and alerts are operational · Required: P13 · By: P13-T09
- [ ] QG-10.7 Rollback procedures are tested · Required: P13 · By: P13-T08
- [ ] QG-10.8 Staging and production configurations are appropriately isolated · Required: P13 · By: P13-T02

Status: IN_PROGRESS  
Owner: Unassigned  
Start Timestamp: 2026-10-09T18:33:59+04:00  
End Timestamp: —  
Verification Timestamp: 2026-10-09T18:33:59+04:00  
Evidence: 2/8 criteria verified; latest QG-10.3 at 2026-10-09T18:33:59+04:00  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-11: End-to-End Integration

- [ ] QG-11.1 Android and iOS clients successfully communicate with backend APIs · Required: P09 · By: P09-T10
- [ ] QG-11.2 Portfolio data flows correctly through transactions, holdings, analytics, dashboards and forecasts · Required: P09 · By: P09-T10
- [ ] QG-11.3 AI Copilot accesses only authorized portfolio data · Required: P10 · By: P10-T09 · CRITICAL
- [ ] QG-11.4 Market-data ingestion and refresh workflows function correctly · Required: P08 · By: P08-T08
- [ ] QG-11.5 Core user journeys pass end-to-end testing · Required: P09 · By: P09-T10
- [ ] QG-11.6 Error handling, offline states and recovery scenarios are verified · Required: P09 · By: P09-T06

Status: NOT_STARTED  
Owner: Unassigned  
Start Timestamp: —  
End Timestamp: —  
Verification Timestamp: —  
Evidence: —  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-12: Production Release Readiness

- [ ] QG-12.1 All mandatory platform quality gates pass (every QG-01..QG-11 criterion due at or before P14 is satisfied; verified with `track.py qg check QG-12.1`) · Required: P14 · By: P14-T11
- [ ] QG-12.2 Android and iOS release builds are verified · Required: P15 · By: P15-T02
- [ ] QG-12.3 Security and privacy reviews are complete · Required: P14 · By: P14-T10 · CRITICAL
- [ ] QG-12.4 Disaster-recovery procedures are validated · Required: P14 · By: P14-T09
- [ ] QG-12.5 Production monitoring and alerting are active · Required: P15 · By: P15-T03
- [ ] QG-12.6 Release notes and operational runbooks are available · Required: P15 · By: P15-T06
- [ ] QG-12.7 Required legal/regulatory reviews are complete for the intended launch markets and investment-intelligence features · Required: P14 · By: P14-T10 · CRITICAL
- [ ] QG-12.8 Final user approval is obtained before production deployment · Required: P15 · By: P15-T06 · CRITICAL

Status: NOT_STARTED  
Owner: Unassigned  
Start Timestamp: —  
End Timestamp: —  
Verification Timestamp: —  
Evidence: —  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-13: QG-FX-01: Market Data Integrity

- [ ] QG-13.1 Streaming connectivity is verified · Required: P12 · By: P12-T02
- [ ] QG-13.2 Bid/ask prices are validated against provider records · Required: P12 · By: P12-T02 · CRITICAL
- [ ] QG-13.3 Stale-data detection is tested · Required: P12 · By: P12-T02
- [ ] QG-13.4 Timestamp and timezone handling is verified · Required: P12 · By: P12-T02
- [ ] QG-13.5 Feed outages are handled safely and prices are never invented or shown as live when delayed, indicative or simulated · Required: P12 · By: P12-T02 · CRITICAL

Status: NOT_STARTED  
Owner: Unassigned  
Start Timestamp: —  
End Timestamp: —  
Verification Timestamp: —  
Evidence: —  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-14: QG-FX-02: Technical Indicator Accuracy

- [ ] QG-14.1 Indicator calculations match independently validated reference cases · Required: P12 · By: P12-T03
- [ ] QG-14.2 Timeframe aggregation is correct · Required: P12 · By: P12-T03
- [ ] QG-14.3 Missing candles and irregular market hours are handled · Required: P12 · By: P12-T03

Status: NOT_STARTED  
Owner: Unassigned  
Start Timestamp: —  
End Timestamp: —  
Verification Timestamp: —  
Evidence: —  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-15: QG-FX-03: Prediction Model Validation

- [ ] QG-15.1 Models outperform, or are honestly reported against, the random-walk and no-change baselines · Required: P12 · By: P12-T05
- [ ] QG-15.2 No data leakage in features, labels or splits · Required: P12 · By: P12-T05
- [ ] QG-15.3 Out-of-sample testing is completed · Required: P12 · By: P12-T05
- [ ] QG-15.4 Probability calibration is evaluated · Required: P12 · By: P12-T05
- [ ] QG-15.5 Prediction intervals are assessed for coverage · Required: P12 · By: P12-T05
- [ ] QG-15.6 Model drift monitoring is configured · Required: P12 · By: P12-T05

Status: NOT_STARTED  
Owner: Unassigned  
Start Timestamp: —  
End Timestamp: —  
Verification Timestamp: —  
Evidence: —  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-16: QG-FX-04: Trading Risk Accuracy

- [ ] QG-16.1 Position sizing is verified against independent reference cases · Required: P12 · By: P12-T07 · CRITICAL
- [ ] QG-16.2 Pip-value conversions are verified for each quote and account currency case · Required: P12 · By: P12-T07 · CRITICAL
- [ ] QG-16.3 Risk/reward calculations are verified · Required: P12 · By: P12-T07 · CRITICAL
- [ ] QG-16.4 Margin and leverage calculations are verified · Required: P12 · By: P12-T07 · CRITICAL
- [ ] QG-16.5 Costs and slippage are included in outputs · Required: P12 · By: P12-T07 · CRITICAL

Status: NOT_STARTED  
Owner: Unassigned  
Start Timestamp: —  
End Timestamp: —  
Verification Timestamp: —  
Evidence: —  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-17: QG-FX-05: Backtesting Integrity

- [ ] QG-17.1 Look-ahead bias tests pass · Required: P12 · By: P12-T08 · CRITICAL
- [ ] QG-17.2 Transaction costs and slippage are included · Required: P12 · By: P12-T08
- [ ] QG-17.3 Walk-forward validation is completed · Required: P12 · By: P12-T08
- [ ] QG-17.4 Backtest reports are reproducible · Required: P12 · By: P12-T08

Status: NOT_STARTED  
Owner: Unassigned  
Start Timestamp: —  
End Timestamp: —  
Verification Timestamp: —  
Evidence: —  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-18: QG-FX-06: AI Trading Intelligence

- [ ] QG-18.1 Market facts are source-backed with timestamps · Required: P12 · By: P12-T10 · CRITICAL
- [ ] QG-18.2 Prediction timestamps and model versions are included · Required: P12 · By: P12-T10
- [ ] QG-18.3 No guaranteed-profit language passes the output guard · Required: P12 · By: P12-T10 · CRITICAL
- [ ] QG-18.4 Structured AI output is validated · Required: P12 · By: P12-T10
- [ ] QG-18.5 Stale-data conditions are handled · Required: P12 · By: P12-T10

Status: NOT_STARTED  
Owner: Unassigned  
Start Timestamp: —  
End Timestamp: —  
Verification Timestamp: —  
Evidence: —  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-19: QG-FX-07: Mobile Experience

- [ ] QG-19.1 Android and iOS builds pass · Required: P12 · By: P12-T11
- [ ] QG-19.2 Charts remain responsive during streaming updates · Required: P12 · By: P12-T11
- [ ] QG-19.3 Background and foreground transitions are handled · Required: P12 · By: P12-T11
- [ ] QG-19.4 Notifications are tested · Required: P12 · By: P12-T11
- [ ] QG-19.5 Network interruption recovery is verified · Required: P12 · By: P12-T11

Status: NOT_STARTED  
Owner: Unassigned  
Start Timestamp: —  
End Timestamp: —  
Verification Timestamp: —  
Evidence: —  
Blocking Issues: —  
Blocks: —  
Approved By: —

### QG-20: QG-FX-08: Release and Regulatory Readiness

- [ ] QG-20.1 Market-data licensing is reviewed · Required: P12 · By: P12-T14 · CRITICAL
- [ ] QG-20.2 Launch-market financial-advice and trading regulations are reviewed · Required: P12 · By: P12-T14 · CRITICAL
- [ ] QG-20.3 Risk disclosures are reviewed · Required: P12 · By: P12-T14
- [ ] QG-20.4 Paper trading remains separate from real holdings · Required: P12 · By: P12-T09 · CRITICAL
- [ ] QG-20.5 No live execution is enabled without explicit approval · Required: P12 · By: P12-T14 · CRITICAL

Status: NOT_STARTED  
Owner: Unassigned  
Start Timestamp: —  
End Timestamp: —  
Verification Timestamp: —  
Evidence: —  
Blocking Issues: —  
Blocks: —  
Approved By: —

## Waiver register

A waiver needs explicit approval, a documented justification, a future expiry/review date and a named risk owner. Critical security, financial-integrity and authorisation criteria cannot be waived by the tracker. Expired waivers fail `track.py validate`.

| Waiver | Criterion | Justification | Approved by | Risk owner | Granted | Expires | Status |
|---|---|---|---|---|---|---|---|
<!-- WAIVERS:BEGIN -->
<!-- WAIVERS:END -->

## Scope changes
Changes to when a criterion is required are decisions, recorded here and in EXECUTION_LOG.md.

| Date | Criterion | Change | Reason | Approved by |
|---|---|---|---|---|
| 2026-10-09 | QG-08.4 | Required phase P01 → P13; evidence task P01-T11 → P13-T04 | The criterion covers dependency **and container** scanning. Dependency scanning is already running in CI (P01-T11); no container images exist until P13-T04, so the container half cannot be satisfied earlier. Not a waiver: the full criterion still applies, at the phase where it can be met. | user (option b) |
| 2026-10-09 | QG-13…QG-20 | Eight Forex gates (QG-FX-01…08, 38 criteria, all required at P12) added to the register | Forex Trading Intelligence module requested as workstream P12; mapping QG-FX-nn = QG-(12+nn). Additive: no existing criterion changed. Approved with phase P12. | user |
