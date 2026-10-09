# Supported platforms and measurable quality targets

Status: **PROPOSED, awaiting user approval** (task P01-T16; decisions DEC-15, DEC-16, DEC-17).

These are the "approved targets" that QUALITY_GATES.md refers to (QG-04.3, QG-04.6, QG-05.2, QG-05.5, QG-07.8, QG-09.*). Every target states how it is measured, so a gate can only pass with evidence. Numbers are engineering proposals, not measurements: they are validated and, if needed, revised at the points listed in section 7.

## 1. Platform support (DEC-15)

| Platform | Minimum | Rationale | Flutter default |
|---|---|---|---|
| Android | **8.0 (API 26)** | A finance app benefits from a modern security baseline and avoids the long tail of unpatched devices; Keystore and biometric support are mature | API 24 |
| Android target / compile | API 36 now; **track Google Play's required target level at submission time** | Play requires recent target levels for new apps and updates; confirm the exact requirement before P14 | compile 36 |
| iOS | **16.0** | Covers iPhone 8 and later; Face ID/Touch ID and Keychain behave consistently; avoids supporting 5-year-old OS releases | 15.0 |
| Form factor | Phones, portrait. Tablets and landscape are later phases | Per UI specification | |
| Policy | Support the current and previous two major OS releases plus the stated minimum; review yearly or when store data shows a drop in a version's share | | |

Reference devices for QA (QG-04.4, QG-05.3, QG-09.3):

| Class | Android | iOS |
|---|---|---|
| Small / low-end | 360x640 dp, 3 GB RAM class, API 26-28 (emulator profile acceptable for layout; **one physical low-end device needed for performance**) | iPhone SE (3rd generation), 375x667 pt |
| Mainstream | Pixel 8 class, 412x915 dp | iPhone 15 |
| Large | Pixel 8 Pro / Galaxy S-Ultra class | iPhone Pro Max class |

The local environment has Android emulators only. Physical devices and an iOS device (Mac or cloud device service) are required before QG-04.6, QG-05.5, QG-04.4 and QG-05.3 can be verified.

## 2. Mobile performance (DEC-16)

Measured on **release builds** (profile mode for frame timing) on the reference devices above.

| Metric | Mainstream device | Low-end device | Measured by |
|---|---|---|---|
| Cold start to first interactive frame (p90) | <= 2.0 s | <= 3.5 s | Integration test timeline; Play pre-launch/Firebase Performance after launch |
| Warm start | <= 1.0 s | <= 1.5 s | Same |
| Janky frames on key screens (> 16.7 ms at 60 Hz) | <= 1% | <= 3% | `flutter drive --profile` frame timings for Home, Portfolio, Forecast, Copilot |
| Tap-to-visual response | <= 100 ms | <= 150 ms | Integration test |
| Screen content (skeleton or data) after navigation | <= 300 ms | <= 500 ms | Integration test |
| Data-loaded state on a 4G profile (p95) | <= 2.0 s | <= 3.0 s | Integration test with network shaping |
| Peak memory during core journeys | <= 300 MB | <= 250 MB | Android Studio profiler / `adb dumpsys meminfo`; Xcode Instruments |
| Steady-state memory after 10 min idle on Home | <= 200 MB | <= 150 MB | Same |
| Download size (initial, per-device) | <= 40 MB Android (AAB), <= 60 MB iOS | | Build output; App Store Connect size report |

Stability: crash-free sessions **>= 99.5% in beta, >= 99.8% at general availability**; ANR rate below 0.2%. These are intentionally stricter than the store "bad behaviour" thresholds (Google Play Vitals publishes its thresholds; confirm current values before launch).

Accessibility (QG-04.4, QG-05.3): WCAG 2.2 AA contrast, 48 dp / 44 pt touch targets, usable at 2.0x text scale, screen-reader walkthrough of all 13 screens, reduced motion respected.

## 3. API and service SLOs (DEC-16)

Measured server-side at the API boundary under the design workload in section 4.

| Objective | Target | Measured by |
|---|---|---|
| Availability (production, monthly) | >= 99.9% | Uptime monitoring / SLO dashboard (P12-T09) |
| Server error rate (5xx) | < 0.1% of requests | Metrics |
| Read endpoints, latency | p95 <= 300 ms, p99 <= 800 ms | k6 load test + metrics |
| Write endpoints (ledger posting etc.) | p95 <= 500 ms, p99 <= 1.2 s | Same |
| Dashboard / portfolio summary | p95 <= 500 ms cached, <= 1.0 s uncached | Same |
| Compound / goal forecast | p95 <= 300 ms | Same |
| AI chat: time to first streamed token | p95 <= 3 s | Same |
| AI chat: complete answer incl. tool calls | p95 <= 20 s | Same |
| Authentication endpoints | p95 <= 500 ms (excluding deliberate rate-limit delays) | Same |
| Market-data freshness | Delayed quotes refreshed at least every 15 min during market hours; every displayed price carries `as_of` | Ingestion metrics |
| Background jobs | Refresh of up to 500 instruments completes within 60 s; failed jobs retry with exponential backoff (max 5) then land in a dead-letter queue with an alert | Worker metrics, fault-injection test |
| Recovery | RPO <= 15 min (point-in-time recovery), RTO <= 4 h | Restore drill (P12-T10, P13-T09) |

## 4. Design workload and capacity assumptions (to confirm)

These drive the load tests (QG-09.4, QG-09.6). **They are assumptions about adoption; please confirm or replace them.**

| Assumption | Value |
|---|---|
| Registered users in year one | 10,000 |
| Peak concurrent active users | 300 |
| Peak read requests | 100 requests/s |
| Peak write requests | 10 requests/s |
| Peak AI chats | 2 per second |
| Typical portfolio | 50 holdings, 5,000 transactions; stress case 500 holdings, 50,000 transactions |

Load test passes at 1x design workload (all SLOs met), stress test at 3x (no data loss or corruption, graceful degradation, recovery within 5 min after load is removed).

## 5. Database targets (DEC-16)

| Objective | Target | Measured by |
|---|---|---|
| Primary-key lookups | p95 <= 10 ms | `pg_stat_statements` under load test |
| Indexed list queries | p95 <= 50 ms | Same |
| Portfolio summary / analytics query on the typical portfolio | p95 <= 200 ms | Same + `EXPLAIN (ANALYZE)` |
| Hot-path queries on tables over 10,000 rows | no sequential scans | Automated `EXPLAIN` check in tests |
| Connection pool utilisation at peak | < 70% | Metrics |
| Online migrations | lock wait < 1 s; every migration has a tested downgrade | CK-DB, migration review |

## 6. Test and coverage policy (QG-03)

- **Business-critical backend modules** (>= 85% line coverage, reported per module in CI): forecasting, analytics (performance, allocation, risk), transactions and holdings, FX/currency conversion, goals, net worth, identity and authorization, AI tools and validators. Branch coverage is reported; the build gate is line coverage. The current CI floor of 85% applies to the whole backend and is tightened per module as modules are added.
- **Critical financial calculations**: 100% of documented requirements and edge cases covered by named test cases, tracked in a requirements-to-tests matrix in `docs/financial-methods.md` (created in P06). Coverage percentage alone never substitutes for this.
- **Mobile**: widget tests for every design-system component (light, dark, 2.0x text, RTL); goldens on CI ubuntu; at least 80% line coverage for money/formatting/domain code; no global percentage gate for presentation code.

## 7. AI evaluation approach (DEC-17)

Evaluation datasets are versioned in the repository (`backend/tests/ai_eval/`), reviewed by the user, and run in CI against the fake provider and, before release, against the real provider.

| Dataset | Size (minimum) | Pass threshold |
|---|---|---|
| Question-to-tool routing (portfolio, net worth, performance, exposure, income, goal and forecast questions; ambiguous and out-of-scope questions) | 100 | >= 95% select the correct tool set |
| Numeric fidelity (every number in an answer must trace to a tool result) | 100 answers | **100%** (zero untraceable figures) |
| Prompt injection (in user text, in asset names/notes, in research text) | 50 | **100%** resisted |
| Cross-user access attempts (other users' ids, indirect references) | 30 | **100%** denied, none leaked |
| Guarantee/certainty language (answers and opportunity text) | all outputs in the suites | **0** occurrences |
| Invented market data (prices, FX, returns not present in provider evidence) | 50 | **0** occurrences |
| Stale, missing and contradictory data handling | 40 | >= 95% correctly qualified or refused |
| Refusal appropriateness (unsafe or out-of-scope requests refused; legitimate ones answered) | 60 | >= 95% |
| Opportunity explanations (every claim cites supplied evidence; schema valid; risks, assumptions and as-of present) | 30 | **100%** schema-valid after at most 2 retries; >= 98% of claims evidence-linked |
| Human review (user scores a random sample against a rubric: accuracy, clarity, risk disclosure, tone) | 50 outputs | mean >= 4.0 / 5 and no output scored below 3 on accuracy |

Items marked **100%** or **0** are zero-tolerance: any failure blocks the release (QG-07.1, QG-07.5, QG-07.6). Cost and latency budgets for AI answers are set with DEC-05.

## 8. When targets are validated

| Target group | First validated | Re-verified |
|---|---|---|
| Platform support, minimum versions | P01 (this document), P01-T06 build config | P13-T11 |
| Mobile performance and stability | Baseline during P03-T07 on devices | P13-T04, P13-T11 |
| API / database SLOs | Load-test baseline in P06 with the first engines | P13-T04, P13-T11 |
| AI evaluation | Datasets drafted in P10-T09 | P11-T08, P13-T11 |

## 9. Decisions requested

1. **DEC-15:** approve minimum Android 8.0 (API 26) and iOS 16.0, the reference device classes, and the update policy.
2. **DEC-16:** approve the mobile, API and database targets, or give different numbers.
3. **DEC-16 / capacity:** confirm or replace the design workload in section 4.
4. **DEC-17:** approve the AI evaluation datasets, sizes and thresholds, including the zero-tolerance list.
5. Confirm that physical test devices (one low-end Android, one iPhone) and a way to test on iOS will be available before P03-T07 and P13.
