# Market-data provider abstraction

Status: Implemented in P08-T02. Decision record: [ADR-0014](../adr/0014-market-data-providers.md). Code: `backend/app/modules/market_data/providers/`.

Feature code depends on one interface, so a vendor can be replaced without touching it. No vendor adapter exists yet (P08-T03); a deterministic fake stands in.

## 1. Interface (`base.py`)

`MarketDataProvider` (a `Protocol`): `name`, `supported_kinds`, and async `get_quote(symbol, kind)`, `get_history(symbol, kind, start, end)`, `get_fx_rate(base, quote)`.

- Implementations raise the errors below, never a vendor exception.
- They never return a guessed or filled-in value: if the vendor has nothing, they raise.
- History is daily closes, oldest first, one per day; days without a close (weekends, holidays) are absent.

## 2. Values and provenance (`models.py`)

| Type | Meaning |
|---|---|
| `Provenance` | provider, `as_of` (when the value was valid), `retrieved_at` (when we fetched it). Both timezone-aware; `as_of` may not be after `retrieved_at`. `age(now)` and `is_stale(now, max_age)` |
| `PriceQuote` | symbol, kind, price (Decimal > 0, finite), currency (ISO code), provenance |
| `PricePoint` | a daily close with the same checks |
| `FxQuote` | 1 base = rate quote; two different currencies, rate > 0 |

A value that fails validation raises `ProviderDataError` on construction, so a bad provider payload is never stored. Amounts are `Decimal` (ADR-0003); a float is refused.

## 3. Errors (`errors.py`)

| Error | Retried | Counts against provider health |
|---|---|---|
| `ProviderUnavailable` | yes | yes |
| `RateLimited` (`retry_after`) | yes, waiting as told (capped) | yes |
| `CircuitOpen` | no (fails fast) | n/a |
| `SymbolNotFound`, `UnsupportedKind` | no | no |
| `ProviderDataError` | no | no |
| `AllProvidersFailed` (lists each error) | n/a | n/a |

## 4. Resilience (`resilience.py`)

- **`RetryPolicy`**: up to 3 attempts, exponential backoff from 0.5 s (factor 2, cap 10 s).
- **`CircuitBreaker`**: opens after 5 failed calls in a row (each already retried); open for 30 s, then one trial call (half-open): success closes it, failure reopens it. Only one trial runs at a time.
- **`ResilientProvider`**: wraps any provider with both. Same interface.
- **`FallbackChain`**: tries providers in order; fails over on `ProviderUnavailable` (including an open circuit); skips a provider that does not serve the kind. An unknown symbol is not retried on another provider silently.

Time and sleeping are injected, so tests do not wait.

## 5. Fake provider (`fake.py`)

Fixed prices and FX, a reproducible daily history (no weekends except crypto, never in the future). Scripted by tests: `set_outage`, `set_stale_by`, `fail_next(n, error)`, `rate_limit_next(n, retry_after)`, `set_price`; every call is recorded in `calls`. Wired in at composition time only.

## 6. Contract tests

`tests/market_data/provider_contract.py` is the contract every provider must pass (provenance on every value, validated numbers, loud failure for unknown symbols, history ordered and in range). The fake runs it now; the adapters reuse it against recorded fixtures in P08-T03.

## 7. Rule enforced by a test

Code outside the package may import only `base`, `models`, `errors` and `resilience`; never an adapter or the fake (`tests/market_data/test_provider_architecture.py`). The composition point (`registry.py`) arrives with the adapters.
