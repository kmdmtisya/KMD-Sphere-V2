# FXCUR soak report (P11-T11)

Date: 2026-10-13. Scope: the reporting-currency rate refresh, cache and status under sustained use, run on the local stack (PostgreSQL with every migration) with a **simulated clock and scripted providers**. This is option A of the advance approval: **no real FX vendor was called**. The soak against the real provider moves to P14-T11.

Harness: [`backend/tests/fx/soak.py`](../backend/tests/fx/soak.py). Machine-readable result: [`reports/fx-soak/fx-soak-96h.json`](../reports/fx-soak/fx-soak-96h.json). A 12-hour run is part of the test suite ([`backend/tests/fx/test_soak.py`](../backend/tests/fx/test_soak.py)), so CI repeats it on every change.

## Set-up

- **Sources, in the default `fx_provider_order`:**
  - a daily ECB-like source that publishes at 15:00 UTC on weekdays and lacks AED and KES;
  - an hourly commercial source with the 30,000 monthly quota (`FX_MONTHLY_REQUEST_BUDGET`).
- **Production code paths throughout:**
  - each source is wrapped in the production `ResilientProvider`, which retries 3 times and has a circuit breaker, both on the simulated clock;
  - refreshes go through `refresh_once_per_window`, and the rate board through `RateBoard.lines`.
- **Load (worst case):**
  - two users press refresh at the same moment every 30 seconds, without pause;
  - the hourly job runs at :05;
  - retry back-off takes no simulated time, so retries arrive faster than in production.
- **Run:** 96 simulated hours, from Thursday 00:00 to Monday 00:00.
- **Checks:** the board is read every simulated minute (5,760 reads, 9 currencies each).
- **Scripted faults.** Each lasts longer than the 2-hour current window and ends 7 minutes into a refresh window:

  | Fault | When (from the start) |
  |---|---|
  | Commercial source down | 10:00 to 13:07 |
  | Commercial source answers "quota reached" | 18:00 to 21:07 |
  | Every source down | 30:00 to 36:07 |

## Finding fixed during the soak

The first runs failed the quota check.

**What happened:** when every source failed, `refresh_once_per_window` released the refresh window so that someone could retry. During a total outage, every user refresh therefore became a provider call.

- The circuit breaker opens for 30 seconds after 5 failed calls, so it still let a trial call through every 30 seconds, and that trial made 3 attempts.
- The result was about **366 requests an hour per source**, against 12 in normal operation.
- The breaker lives in each API process, so the rate multiplies by the number of processes.
- A 3-hour total outage used 1,086 requests per source, more than twice the budget prorated to the 12-hour run.

**Fix (P11-T11):** a refresh that fails at every source still uses up its window. The next attempt waits for the next window.

- Windows are claimed in the database, so this bounds an outage to 4 attempts an hour across all processes.
- Rates come back at most one window (15 minutes) after the source returns.
- The worker's quick Celery retries now find the window already used. Its next real attempt is in the next window.

Changed files:

- [`app/modules/fx/refresh.py`](../backend/app/modules/fx/refresh.py);
- the test that asserted the old release, now `test_when_every_provider_fails_the_next_attempt_waits_for_the_next_window`;
- [`docs/design/fx-refresh.md`](design/fx-refresh.md).

## Results (96 hours, after the fix)

| Check | Result |
|---|---|
| Requests per source in a window where it answered | at most 1 (both sources) |
| Busiest hour, per source (including outages) | 12 requests (4 windows × 3 retry attempts) |
| Requests over the run | ECB 434, commercial 486; prorated budget 3,870 |
| Normal operation extrapolated to a 31-day month | 2,976 per source; budget 30,000 |
| Simulated quota hit without being scripted | 0 times |
| Rates labelled current although older than their current window | 0 |
| Rates shown that no source published, or dated in the future | 0 |

Outages:

| Fault | Requests during it (ECB / commercial) | Felt on the board | Current again after the fault ended |
|---|---|---|---|
| Commercial down, 3h07 | 13 / 39 | yes: AED and KES became `cached` | 8 minutes (the next window) |
| Commercial "quota reached", 3h07 | 13 / 39 | yes | 8 minutes |
| Everything down, 6h07 | 75 / 75 | yes | 8 minutes |

Status seen over the run: 41,863 `current` and 9,977 `cached` readings; nothing `stale` or `unavailable`.

Acceptance for P11-T11:

- **Provider calls within quota:** met.
- **No stale rate labelled current:** met.
- **Automatic recovery after an outage:** met, within one refresh window and with no manual action.

## Observations for the release decision (not changed here)

1. **Weekend rates show as cached.**
   - Because `ecb` is first in `fx_provider_order`, the 7 currencies it publishes come from the ECB even when the commercial source has newer rates.
   - From Sunday 03:00 (36 hours after Friday's publication) until Monday's 15:00 publication, those 7 currencies show as `cached`. In the run, 8,813 of 20,160 weekend readings of ECB rates were `cached`.
   - This is honest and within DEC-26, but it is about 36 hours a week.
   - Over a TARGET holiday weekend (for example Good Friday to Easter Monday), the gap reaches 96 hours, past the 72-hour cached window, so those rates would show as `stale`. That case is computed from the windows, not simulated.
   - Options:
     - put `exchangerate_api` first: it supplies every currency, uses the same 2,976 requests a month, and the ECB becomes the fallback;
     - or ask the next source for currencies whose stored rate is no longer current.
2. **Total-outage cost is now bounded by time, not by users.**
   - Each source costs at most 12 requests an hour (4 windows × 3 retry attempts).
   - A whole month of total outage would cost 8,928 requests, still inside 30,000.
3. **Limits of this soak.**
   - Simulated clock and scripted sources.
   - One API process, with the breaker in memory. Window coordination happens in the database and is shared across processes; the breaker is not.
   - Concurrency comes from back-to-back calls, not parallel requests.
   - Real vendor behaviour (latency, how a "quota reached" answer is counted, publication times) is for P14-T11 against the real provider.

## How to run

```
cd backend
uv run python -m tests.fx.soak --hours 96 --out ../reports/fx-soak/fx-soak-96h.json
uv run pytest tests/fx/test_soak.py -q
```

The harness creates a throwaway database, migrates it to head and drops it afterwards (`tests/db_fixtures.py::throwaway_database`).
