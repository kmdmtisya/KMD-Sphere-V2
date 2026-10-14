# P13 exit gate summary: Forex Trading Intelligence (2026-10-14)

**Outcome: the module is built and verified, and it is not released.** Forex is off by default and refused outside the `local` and `test` environments. Every price comes from the simulated provider and is labelled as simulated. There is no live execution.

## Tasks

| Task | Result | PR |
|---|---|---|
| P13-T01 Scope, ADR-0009, decisions DEC-19 to DEC-24 | Approved with the proposals as written | — |
| P13-T02 Market data (quotes, candles, stream, fake provider, OANDA-style adapter) | Complete | #154 |
| P13-T03 Indicators, candles, patterns | Complete | #156 |
| P13-T04 Economic calendar | Complete | #157 |
| P13-T05 Forecasting registry and baselines | Complete | #158 |
| P13-T06 Opportunity ranking | Complete | #159 |
| P13-T07 Trade-risk engine and contract specifications | Complete | #160 |
| P13-T08 Backtesting | Complete | #161 |
| P13-T09 Paper trading | Complete | #162 |
| P13-T10 Forex Copilot (11 read-only tools, evaluation sets) | Complete | #163 |
| P13-T11 Mobile forex screens | Complete | #164 |
| P13-T12 Quality gates QG-13 to QG-19 | All passed | #165 |
| P13-T13 Soak, outage drill, feed metrics | Complete; one defect found and fixed (stale prices shown as fresh during an outage) | #166 |
| P13-T14 Release readiness and decision | Complete: licence checklist, regulatory questions, disclosures approved, execution disabled, **not released** | #167, #168 |

## Gates

| Gate | Status |
|---|---|
| QG-13 to QG-19 | Passed ([p13-forex-gates-summary.md](p13-forex-gates-summary.md)) |
| QG-20.3 Risk disclosures reviewed | Verified: approved by the user as drafted |
| QG-20.4 Paper trading separate from real holdings (CRITICAL) | Verified |
| QG-20.5 No live execution without approval (CRITICAL) | Verified |
| QG-20.1 Market-data licensing reviewed (CRITICAL) | **Not done.** Moved to P17-T09 by the user's plan change of 2026-10-14; not waived |
| QG-20.2 Launch-market regulations reviewed (CRITICAL) | **Not done.** Moved to P17-T09 by the same plan change; not waived |

## Open before forex is switched on outside development (P17-T09)

1. Choose a market-data provider and sign the licence review (DEC-19, QG-20.1).
2. Complete the regulatory review for Kenya and the UAE (DEC-20, QG-20.2), and have the named reviewer review the disclosures for real data.
3. Run the staging smoke tests (P15-T11) and pass the core hardening gate (P16-GATE).
4. Record the hands-on acceptance of the forex screens and the manual device pass (QG-19 limit, P13-T13.4).
5. Make an approved change to the configuration guard in `backend/app/core/config.py`.

## Known limits carried

- **Simulated data only:** all prices, the soak and the backtests use simulated data, and the calendar is DEMO data.
- **Forecast probabilities need calibration:** they are labelled as such.
- **No live monitoring yet:** Prometheus, Grafana and Alertmanager are not running locally. They come in P15 and P16.
- **Live-Keycloak tests fail locally:** the dev user needs an OTP. These tests are skipped in CI, and no identity change was made.
