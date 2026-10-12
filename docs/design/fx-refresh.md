# FX providers, refresh and rate status (P11-T03)

Decisions: [ADR-0010](../adr/0010-global-reporting-currency.md), [fxcur-reconciliation.md](fxcur-reconciliation.md) (DEC-25 provider, DEC-26 status windows, DEC-27 USD pivot). Builds on the P08 provider abstraction ([market-data-provider.md](market-data-provider.md)).

## Providers

| Order | Provider | Covers | Rate type | Request |
|---|---|---|---|---|
| 1 | ECB euro reference rates | about 30 currencies, crossed through EUR (path recorded, e.g. USD→EUR→GBP); no AED or KES | indicative | one daily file for every currency |
| 2 | ExchangeRate-API (DEC-25) | the launch currencies including AED and KES | indicative ("indicative mid-rate" in its documentation) | `latest/{pivot}` returns every currency in one request |
| 3 | Twelve Data (if its key is set) | further fallback | indicative | one request per pair |

`FX_PROVIDER_ORDER` sets the order; a provider without a key is left out. **ExchangeRate-API is built from its public documentation with synthetic fixtures only: no key exists and no live call has been made** (fixture-only approval of P11-T03). Production use of both the ECB and ExchangeRate-API waits for the licence review at P11-T12.

## One refresh

Every active currency in `currencies` is fetched against the pivot (`FX_PIVOT_CURRENCY`, USD). Each provider is asked, in order, for the currencies the previous ones did not supply, in one batch request when it can. A failing provider (outage, refused key, unusable data) is skipped; its data is never used and never replaced by a guess. A currency no provider supplies stays missing and shows as unavailable. Rates are stored once per (pair, provider, published time) with their type and path.

## Quota and backoff

At most **one refresh per window** (`FX_REFRESH_WINDOW_MINUTES`, 15) per pivot, whoever asks: the hourly job and users share the window through the idempotent job runner, so screens never call a provider. Worst case: 4 requests an hour per provider, 2,976 in a 31-day month, inside the 30,000 of the commercial plan (a test checks the arithmetic against `FX_MONTHLY_REQUEST_BUDGET`). Inside a refresh, the resilient wrapper retries with exponential backoff and a circuit breaker; when every provider fails, the window is released and the job is retried with exponential backoff.

## Status (DEC-26)

| Status | ECB (daily) | Hourly providers |
|---|---|---|
| current | up to 36 hours old | up to 2 hours |
| cached | up to 72 hours | up to 24 hours |
| stale | older (shown with its age) | older |
| unavailable | no rate stored | no rate stored |

The status is computed when a rate is read, never stored, so a cached rate can never be shown as current. An unknown provider is held to the stricter hourly windows. Over a weekend the ECB rate is cached, as it should be.

## API

| Route | Purpose |
|---|---|
| `GET /api/v1/fx/status` | Every active currency against the pivot: rate (string), provider, rate type, published and fetched times, path, status, age |
| `POST /api/v1/fx/refresh` | Ask for fresh rates (5 per user per hour); returns whether a refresh ran, which provider supplied what, what is missing, and the status. When every provider fails it returns the last stored rates with their status and age |

Reads go through a short cache of stored rows (60 s), invalidated by a refresh; the status is still computed per read. Both routes are on the reviewed list of routes that carry market data (per signed-in user, with provenance).
