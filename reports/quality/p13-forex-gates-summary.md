# P13 forex quality gates, QG-13 to QG-19 — P13-T12, 2026-10-14

One report per gate. The register of record is `QUALITY_GATES.md`, updated only through `scripts/track.py qg ...`.

| Gate | Report | Criteria | Result | Limits carried forward |
|---|---|---|---|---|
| QG-13 Market Data Integrity | [qg-13-forex-market-data.md](qg-13-forex-market-data.md) | 5 | Pass | Provider records are vendor-format fixtures. Re-verify on a licensed feed (DEC-19, QG-20.1) |
| QG-14 Technical Indicator Accuracy | [qg-14-forex-indicators.md](qg-14-forex-indicators.md) | 3 | Pass | — |
| QG-15 Prediction Model Validation | [qg-15-forex-model-validation.md](qg-15-forex-model-validation.md) | 6 | Pass | Validated on synthetic and simulated data only. No edge is claimed; a real-market evaluation needs licensed data |
| QG-16 Trading Risk Accuracy | [qg-16-forex-trading-risk.md](qg-16-forex-trading-risk.md) | 5 | Pass | Contract specifications are unreviewed DEMO defaults (DEC-24) |
| QG-17 Backtesting Integrity | [qg-17-forex-backtest-validation.md](qg-17-forex-backtest-validation.md) | 4 | Pass | No stored spread history (the spread is assumed per tier); swaps not modelled |
| QG-18 AI Trading Intelligence | [qg-18-forex-ai.md](qg-18-forex-ai.md) | 5 | Pass | Real-model routing waits for ADR-0017; the advice check is a wording rule |
| QG-19 Mobile Experience | [qg-19-forex-mobile.md](qg-19-forex-mobile.md) | 5 | Pass | Manual device pass not done (a release item); forex pushes not sent by the server yet |

**Not covered here.** QG-20 (release and regulatory readiness) belongs to P13-T13 (soak), P13-T14 (regulatory pack) and P13-GATE. The forex module stays off outside development (DEC-20, DEC-23).

**Evidence runs, 2026-10-14:**
- backend forex, AI, financial-matrix and integrity suites: 753 passed;
- mobile forex, journey and guard tests: 73 passed;
- CI on PR #164: mobile tests with goldens, the Android debug build and the iOS compile all passed.
