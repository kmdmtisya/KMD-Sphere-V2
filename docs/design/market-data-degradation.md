# Market data: what happens when it goes wrong (P08-T08)

Proven by `backend/tests/market_data/test_degradation*.py`, with the fake provider scripting every
failure. The rule: an outage or stale data never becomes an error screen or a silently wrong number.

| Situation | Behaviour |
|---|---|
| One provider down | Retry, then the fallback chain answers; the value is credited to the provider that answered. |
| Every provider down | `AllProvidersFailed`; ingestion stores nothing and reports failures (error type only). The job is failed and retried. |
| Provider keeps failing | The circuit opens and calls stop reaching it; a trial call after the cool-down closes it again. |
| Rate limited | Retried with the provider's `retry-after`, then failed over. |
| One instrument fails | The others are still stored. |
| Outage, a price is stored | Reads keep working: the last price values the holding, flagged `value_stale` once past its window (4 days listed, 6 h crypto); the summary lists it under `freshness.stale_prices`. |
| Outage, no price ever | The holding is unpriced (value null, `complete: false`), never zero or invented. |
| Provider returns old data | Stored with its true `as_of`, flagged stale, and never replaces a fresher price. |
| Recovery | The next run stores a current price and the flag clears. |

## Cache

Analytics and dashboard responses are cached per user (`app/core/cache.py`). A new market price
does not invalidate the cache, so a figure can lag a new price by at most `analytics_cache_seconds`
(default 300 s); any successful write by the user refreshes it at once. If Redis is down, responses
are computed live. Figures are never shared between users.
