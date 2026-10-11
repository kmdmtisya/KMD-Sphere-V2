# Market-data provider abstraction

Status: Implemented in P08-T02. Decision record: [ADR-0014](../adr/0014-market-data-providers.md). Code: `backend/app/modules/market_data/providers/`.

Feature code depends on one interface, so a vendor can be replaced without touching it. No vendor adapter exists yet (P08-T03); a deterministic fake stands in.

## 1. Interface (`base.py`)

`MarketDataProvider` (a `Protocol`): `name`, `supported_kinds`, and async `get_quote(symbol, kind)`, `get_history(symbol, kind, start, end)`, `get_fx_rate(base, quote)`, `get_fx_history(base, quote, start, end)`.

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

## 6. Adapters (P08-T03)

| Adapter | Serves | Key | Notes |
|---|---|---|---|
| `ecb.py` | FX only | none | Daily euro reference rates (XML, parsed with `defusedxml`). Any pair is crossed through EUR. A currency the ECB does not publish (for example AED, KES) is `SymbolNotFound`; a fallback FX provider covers it. Indicative, not for transactions |
| `coingecko.py` | crypto, quoted in USD | header `x-cg-demo-api-key` / `x-cg-pro-api-key` | Our symbol maps to a coin id. Production needs a paid plan and the attribution line |
| `twelvedata.py` | equities, ETFs, indices, FX | header `Authorization: apikey ...` | Errors can arrive as HTTP 200 with a body code, mapped here. **Not for production on an Individual plan** (ADR-0014) |

Shared rules:
- **HTTP boundary** (`http.py`): adapters use an injected `HttpClient`. Timeouts and connection errors are `ProviderUnavailable`, 429 is `RateLimited` (`Retry-After` honoured), 401/403 is `ProviderAuthError` (not retried, counts against health, lets a chain move on), 5xx is `ProviderUnavailable`. Messages name the provider and status, never the URL, headers or key.
- **Decimals:** JSON is parsed with `parse_float=Decimal`; no vendor number passes through a float.
- **Rate limiting** (`throttle.py`): a sliding-window `RateLimiter` per adapter (ECB 10 a minute, CoinGecko demo 30, Twelve Data Basic 8); calls wait instead of being refused.
- **Keys:** `Settings.coingecko_api_key` and `twelvedata_api_key` are `SecretStr`, read from the environment (`.env.example` lists the names, empty), never in source. Each adapter's `repr` omits the key; a missing key fails with `ProviderAuthError` before any call. Tests prove the key is in no URL, parameter, error message, repr or log line.

## 7. Contract tests

`tests/market_data/provider_contract.py` is the contract every provider must pass (provenance on every value, validated numbers, loud failure for unknown symbols, history ordered and in range, FX including history). The fake and all three adapters run it offline against fixtures in `tests/market_data/fixtures/`: the ECB files are **recorded** from the real feed (2026-10-12); the CoinGecko and Twelve Data files are **synthetic** in the vendors' documented shapes, to be re-recorded once keys exist (see the fixtures README).

## 8. Rule enforced by a test

Code outside the package may import only `base`, `models`, `errors` and `resilience`; never an adapter or the fake (`tests/market_data/test_provider_architecture.py`). The composition point (`registry.py`) arrives with the adapters.
