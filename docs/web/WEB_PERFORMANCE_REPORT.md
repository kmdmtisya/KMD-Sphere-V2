# Web portal performance report

**Status:** P14-T20, 2026-10-16. Lab measurements on one development machine, against the production build. They show whether the portal is within the proposed budgets; they are not field data and not a load test.

## Budgets (DEC-36, proposed)

Lighthouse performance at least 85 and accessibility at least 95; LCP at most 2.5 s, INP at most 200 ms, CLS at most 0.1 (at p75 in the field; here, single lab runs); dashboard API p95 at most 500 ms. **DEC-36 is not yet approved by the user**; the figures below are measured against the proposed values, and QG-31.1 ("against the approved budgets") stays open until they are approved or changed.

## Method

- Lighthouse 12 (desktop preset, its simulated throttling) driven by `web/scripts/perf/lighthouse.mjs` on Chrome chrome, signed in through the real login page, one run per page after a warm-up visit. The server was the standalone production build on loopback over plain HTTP, with the API, PostgreSQL, Redis and Keycloak on the same machine.
- Large book and responsiveness: `web/e2e/perf.spec.ts` (WS_E2E_PERF=1) seeds 80 assets and 1500 postings through the API, then times pages, interactions (event timing, long tasks) and the API through the portal.
- Bundle size from the production build; JS heap from the browser after the interactions.

## Lighthouse, signed in

| Page | Performance | Accessibility | Best practices | LCP | CLS | TBT | Transfer |
|---|---|---|---|---|---|---|---|
| `/home` | 97 | 100 | 81 | 1.17 s | 0.034 | 0 ms | 347 KB |
| `/portfolio` | 99 | 100 | 81 | 0.99 s | 0.002 | 7 ms | 331 KB |
| `/portfolio/analytics` | 98 | 100 | 81 | 0.95 s | 0.069 | 5 ms | 345 KB |
| `/goals` | 99 | 100 | 81 | 0.94 s | 0.018 | 3 ms | 336 KB |
| `/planning/calculator` | 99 | 100 | 81 | 0.93 s | 0.002 | 4 ms | 316 KB |
| `/ai` | 99 | 100 | 81 | 0.76 s | 0.002 | 10 ms | 320 KB |
| `/reports` | 100 | 100 | 81 | 0.72 s | 0.002 | 0 ms | 324 KB |
| `/settings` | 98 | 100 | 81 | 1.03 s | 0.013 | 16 ms | 326 KB |

Best practices scores 81 on every page for two audits only: `is-on-https` (the lab server is plain HTTP on loopback; deployments use HTTPS) and `valid-source-maps` (production source maps are not shipped, on purpose).

## Findings and fixes

| Finding | Fix |
|---|---|
| CLS over 0.1 on Home (0.13 to 0.16), Goals (0.12 to 0.20), Settings (0.14 to 0.19) and Analytics (0.12): loading placeholders were much shorter than the content that replaced them | `LoadingState` takes a `reserve` height; the dashboard sections, the goal cards, the settings cards and the analytics cards keep their space while loading. CLS is now 0.002 to 0.069 on every page. |
| Home had no wealth-over-time chart (a reference-review finding) | A net-worth trend card from the history endpoint; its space is reserved while loading. |
| Compact axis labels could repeat ("$198M", "$198M") | Two fraction digits on chart axes. |

## Large book (81 holdings, 1500 postings)

| Measure | Result |
|---|---|
| Holdings page until the table is usable | 768 ms |
| Ledger page (first 25 rows, "Load more") | 610 ms |
| Analytics (performance, risk chart, allocation) | 1444 ms |
| Home | 1286 ms |
| Sorting a column twice: slowest event | 56 ms (0 long task) |
| Opening and closing the add-transaction drawer: slowest event | 104 ms (2 long tasks) |
| Changing the chart period four times: slowest event | 40 ms (0 long tasks) |
| JS heap after the interactions | 32 MB |

The slowest interaction (the drawer, 112 ms) is inside the 200 ms INP budget. INP itself is a field metric over real sessions; this is the lab's closest figure.

## API latency through the portal (large book, 30 sequential calls each)

| Endpoint | First call (ms) | p50 (ms) | p95 (ms) |
|---|---|---|---|
| `dashboard` | 879 | 41 | 58 |
| `net-worth` | 373 | 38 | 44 |
| `portfolios/consolidated/summary` | 255 | 181 | 420 |
| `income/summary` | 270 | 79 | 102 |
| `goals/summary` | 61 | 36 | 42 |
| `portfolios/{id}/summary` | 128 | 116 | 317 |
| `portfolios/{id}/holdings` | 69 | 53 | 65 |
| `portfolios/{id}/performance` | 37 | 29 | 33 |
| `portfolios/{id}/allocation` | 76 | 27 | 33 |
| `portfolios/{id}/risk?frequency=monthly` | 276 | 39 | 57 |
| `portfolios/{id}/transactions?limit=25` | 86 | 46 | 74 |

The dashboard workload's p95 is at most 420 ms (the consolidated summary), inside the 500 ms budget. First calls are slower because the response cache is cold (the dashboard's first call took 879 ms); the budget is a p95 of repeated use.

## Resource usage

Production JavaScript: 33 files, 1.5 MB raw, 499 KB gzip across all routes; the largest chunk (the chart library) is 184 KB gzip; CSS 6 KB gzip. A page transfers 316 to 347 KB (Lighthouse). JS heap 30 MB on the large book.

## Browsers

| Browser | Version tested | How | Result |
|---|---|---|---|
| Chrome | 155.0.8059.41 (Windows) | Whole e2e suite and the cross-browser journeys at 1440, 1280, 1024, 768 and 375 px, Light and Dark | Pass |
| Edge | 155.0.4283.45 (Windows) | The cross-browser journeys at the same widths and themes | Pass |
| Firefox | Playwright's Firefox | The cross-browser journeys, in CI (the bundled browsers cannot be downloaded on this machine) | See the CI result in the pull request |
| Safari | Playwright's WebKit, in CI | The cross-browser journeys. WebKit is Safari's engine, not Safari: a real Safari on macOS and iOS has not been tested | Not claimed (QG-32.4 stays open) |

**Supported browsers (proposed with DEC-36):** the latest two major versions of Chrome, Edge and Firefox, and Safari 17 or later. The sign-in uses `__Host-` Secure cookies, which need HTTPS in deployments (loopback HTTP is treated as secure by Chromium and Firefox).

## Limits

Single machine, loopback network, one run per page; Lighthouse's own variance is a few points. Numbers on other hardware or networks will differ. No field data exists yet. Real Safari, a phone browser and a slow network were not measured.
