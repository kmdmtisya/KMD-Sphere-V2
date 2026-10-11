# Analytics API and caching

Status: Implemented in P06-T09. The API publishes the P06 figures; each endpoint's methods are in the linked design document.

## Endpoints

| Route | Figures | Methods |
|---|---|---|
| `GET /api/v1/portfolios/{id}/performance` | value, contributions, withdrawals, net invested, profit/loss, simple return, money-weighted return (XIRR), realised and unrealised profit, income, expenses | performance.md |
| `GET /api/v1/portfolios/{id}/allocation` | allocation by asset class, currency, country and sector (weights adding up to 100), concentration | allocation.md |
| `GET /api/v1/portfolios/{id}/income` | trailing 12 months, months, years, by asset and type, yields | income.md |
| `GET /api/v1/portfolios/{id}/risk?frequency=&start=&end=` | value series, volatility, maximum drawdown, time-weighted return, or an explicit status | risk.md |
| `GET /api/v1/income/summary?currency=` | passive income across active portfolios (monthly, yearly) | income.md, below |
| `GET /api/v1/net-worth?currency=` | net worth with FX provenance (P06-T07) | net-worth.md |
| `GET /api/v1/goals/summary` | goals on track (P06-T06) | goals.md |
| `GET /api/v1/dashboard?currency=` | the Home screen: net worth, passive income, goals on track | below |

**Authorisation and formats:**
- Portfolio routes answer 404 for another user's portfolio, exactly like a missing one (ADR-0011), and each has a cross-user test.
- Amounts are Money at the currency's minor units, half-up.
- Rates and shares are percentages with at most 2 decimals, half-up; trailing zeros are dropped, so 8.50 is shown as 8.5.
- The Herfindahl index is given to 4 decimals and effective positions to 2.
- Performance and risk responses carry the notice that past performance is not a reliable indicator of future results.

**Income summary.** Each active portfolio's trailing-12-month income is converted from its base currency at the latest rate. A portfolio whose currency has no rate is listed with `value: null`, left out of the totals, and named in `unconverted_currencies` (`complete: false`).

**Dashboard.**
- Net worth comes from the net-worth figures.
- Passive income is the income summary in the same currency.
- Goals on track come from the goals summary.
- `complete` is false when any part is incomplete.

## Cache

**Where.** Responses of the routes above are cached in Redis (`app/core/cache.py`):
- `analytics_cache=redis`, with entries expiring after `analytics_cache_seconds` (300).
- Tests use a per-process store; `off` disables the cache.

**Never another user's data:**
- Keys are `ws:an:<user id>:<generation>:<route>:<hash of the parameters>`.
- An answer is only ever read back for the user who caused it.
- The route authorises before anything is computed, and only successful answers are stored, so a refused request leaves nothing behind.
- Tests check that another user's request for a cached portfolio still gets 404, and that nothing is stored under their id.

**Invalidated on ledger changes.** A middleware increments the signed-in user's generation after **any successful write** (POST, PUT, PATCH, DELETE with a 2xx answer), before the response is sent. That covers:
- ledger postings and reversals;
- valuations;
- liabilities;
- goals;
- portfolio changes;
- future write routes, automatically.

Reads after the response always miss and recompute. A failed write, a read, a forecast (computed from the request alone) and another user's writes do not invalidate.

**Time and market data.** Figures that depend on the clock or on the latest FX rates (and, from P08, prices) can be served unchanged for at most the TTL.

**Redis down.** Requests are computed without the cache (logged). A failed invalidation is logged at error level, and entries still expire within the TTL.

**What Redis holds.** Cached answers contain the user's financial figures. Redis is internal to the deployment (no public access, password-protected; TLS in deployed environments, P14), and entries expire after 5 minutes. Nothing is cached for a request that was not authorised.
