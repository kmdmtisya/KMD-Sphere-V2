# QG-23 (QG-FXCUR-03): Data Reliability — P11-T10, 2026-10-13

| Criterion | Evidence | Result |
|---|---|---|
| 23.1 Provider outages are handled without inventing rates | `tests/fx/test_refresh_and_status.py::test_when_every_provider_fails_the_last_good_rate_is_shown_with_its_age`; integration drill (total outage keeps the last good rates and conversions use the last good snapshot); currencies no provider supplies stay missing | Pass |
| 23.2 Stale-rate detection is tested | Status windows per provider (DEC-26) at every boundary; the board computes status on each read, even from its cache; stale labels end to end (status board, reporting block, single rate) | Pass |
| 23.3 Fallback provider is tested | A primary without AED/KES, a primary that is down, bad data and a refused key each move on to the next provider; the resilient wrapper retries a batch | Pass |
| 23.4 Rate timestamps and status are displayed | API: every rate carries provider, rate type, published and fetched times and status. Mobile: FX status line (current, cached, old, unavailable, with time) on Home and in the selector; the converter shows rate time and status (widget tests, e2e journey 8) | Pass |
| 23.5 Cache behaviour is verified | One refresh per window whoever asks (a second call does not reach the provider); the window is released after a total failure; quota arithmetic (2,976 ≤ 30,000); the board cache is invalidated by a refresh and never shows a cached row as current | Pass |

Runs: `cd backend && uv run pytest tests/fx -q`; `cd mobile/wealthsphere_app && flutter test test/features/currency` (both passed).

**Update (P11-T11, 2026-10-13):** the soak found that releasing the window after a total failure let every user refresh retry during an outage (about 366 requests an hour per source and process). A failed refresh now keeps its window and the next attempt comes in the next window. This tightens 23.5: an outage is bounded to 4 attempts an hour across all processes, and recovery happens within one window. See docs/fxcur-soak-report.md. The gate result is unchanged.
