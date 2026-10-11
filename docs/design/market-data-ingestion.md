# Price and FX ingestion

Status: Implemented in P08-T05. Code: `backend/app/modules/market_data/{ingestion,freshness}.py`, `providers/registry.py`, jobs in `backend/app/worker/tasks.py`. Depends on the provider interface ([market-data-provider.md](market-data-provider.md)) and the job infrastructure ([jobs.md](jobs.md)).

## 1. What is stored

**`market_prices`** (migration 0011). One row is one price of one global asset from one provider. Rows are immutable: a newer price is a new row.

| Column | Meaning |
|---|---|
| `asset_id` | the asset (global, market-valued) |
| `price`, `currency` | NUMERIC(28,12), in the asset's own currency (checked) |
| `price_type` | `quote` (latest) or `close` (daily close from a backfill) |
| `provider` | who provided it |
| `as_of` | when it was valid (the provider's time) |
| `retrieved_at` | when we fetched it |
| `ingested_at` | when we stored it |

Unique on (`asset_id`, `provider`, `price_type`, `as_of`): this is what makes ingestion idempotent. The table also refuses a price <= 0, a malformed currency, an unknown type and `retrieved_at < as_of`.

**`fx_rates`** (P05) gets the same treatment: unique on (pair, provider, `rate_timestamp`), `ON CONFLICT DO NOTHING`.

## 2. Rules

- **Idempotent.** Every store is `INSERT ... ON CONFLICT DO NOTHING`; running a job or a backfill again, over the same or an overlapping range, stores only what is new. Jobs also claim an idempotency key (`job_runs`), so a repeated or overlapping run does nothing at all.
- **Own currency only.** A price is stored only if the provider's currency equals the asset's. A mismatch is a failure, never a conversion: we do not guess an FX rate to fix a price.
- **Failures are isolated.** One unknown symbol or failing pair does not stop the others; failures come back in the result (type and a short message).
- **An outage is a failed run, not a quiet success.** When nothing was stored or already known and something failed, the job fails and Celery retries with backoff (the claim is retaken on retry).
- **Nothing is invented.** If a provider has nothing, nothing is stored.

## 3. Which assets get prices

Global, active assets whose class is valued from prices, with a symbol, and whose class maps to a provider kind (`freshness.KIND_BY_ASSET_CLASS`): stocks and REITs (equity), ETFs and mutual funds (ETF), cryptocurrency (crypto). Bonds and commodities are valued from prices in principle but have no provider yet, so they keep manual valuations. User-defined assets are never sent to a provider.

## 4. Staleness

`latest_price` returns the newest stored price at or before now, with a `stale` flag when it is older than its kind's window (`freshness.FRESH_FOR`: 4 days for listed assets, which covers a weekend and a holiday; 6 hours for crypto). A stale price is still returned with its `as_of`; the valuation shows the flag (P08-T06). No price at all returns `None`, and the caller falls back to manual valuations. The windows are provisional until DEC-26 (P11-T01).

## 5. Jobs

| Job | Key | When | Does |
|---|---|---|---|
| `ingest_prices` | quarter-hour bucket | every 15 minutes | latest quote of every eligible asset |
| `ingest_fx` | day | 16:30 UTC daily (after the ECB publishes) | latest rate of every (currency, portfolio base currency) pair in use |
| `backfill_prices(asset_id, start, end)` | asset and range | on demand | daily closes |
| `backfill_fx(base, quote, start, end)` | pair and range | on demand | daily rates |

Providers come from `providers/registry.py`: with `MARKET_DATA_MODE=fake` a deterministic fake serves everything (local development); in `real` mode a provider is present only when its key is set (ECB needs none), so the system runs on what is available and reports the rest as unavailable.

## 6. Tests

`tests/market_data/test_ingestion.py` (provenance on every row, idempotency, overlapping backfills, failure isolation, outage, currency refusal, table constraints, pairs needed, latest price and staleness) and `tests/worker/test_market_jobs.py` (the jobs end to end: claim, retry after an outage, persistent outage fails, reruns skipped, backfills, schedule, registry), both against the migrated database with the fake provider.
