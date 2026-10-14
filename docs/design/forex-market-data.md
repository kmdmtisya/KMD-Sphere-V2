# Forex market data, as built (P13-T02)

How the forex market-data layer was built: provider interfaces, the simulated and vendor-shaped providers, storage, the streaming client and the app's quote API. The design is in [forex-technical-design.md](forex-technical-design.md) section 4, and the decisions behind it are in [forex-reconciliation.md](forex-reconciliation.md).

**Status:**
- **Fixture-only (DEC-19).** The only provider the app can use is the simulated one, and every price it produces is labelled `simulated`. The vendor-shaped adapter is tested against synthetic recorded responses; no key exists and no live call is made.
- **Off by default (DEC-23).** The flag cannot be switched on outside the local and test environments (DEC-20).

## 1. Code

The code lives in `backend/app/modules/forex/`. It shares nothing with `app/modules/fx`, which converts the user's own money into a reporting currency.

| File | Content |
|---|---|
| `instruments/universe.json`, `registry.py`, `models.py` | The instrument registry (12 pairs, including USD/KES and USD/ZAR) with pip location, display precision and liquidity tier. `forex_universe` selects the active pairs. Rows are deactivated, never deleted. Contract specifications (lot size, margin) are a separate reviewed table in P13-T07 (DEC-24) |
| `marketdata/types.py` | `Quote` (Decimal bid and ask, UTC provider time, data type; the mid is derived), `ReceivedQuote` (adds receipt time, quality and feed status), `Candle`, `Heartbeat`, and the enums. A value that fails validation raises `ProviderDataError` and is never stored |
| `marketdata/provider.py` | The `ForexProvider` protocol: `snapshot`, `stream`, `candles`. `ResilientForexProvider` reuses P08's retry and circuit breaker (`call_guarded`) |
| `marketdata/fake.py` | The simulated provider. Prices are deterministic and Decimal-only: a daily wave around synthetic reference levels plus hashed noise. The market is closed from Friday 21:00 to Sunday 21:00 UTC. Scripts and outages are available for tests |
| `marketdata/oanda.py` | A vendor-shaped adapter (v20 pricing, pricing stream, candles), fixture-only. A price the vendor marks as not tradeable is downgraded to `indicative_rate`. A vendor feed can never be labelled `simulated` |
| `marketdata/quality.py` | The rules in section 3 |
| `marketdata/monitor.py`, `stream.py` | Heartbeat windows, and the streaming client with reconnect, dedupe and gap detection (section 4) |
| `marketdata/models.py`, `partitions.py`, `repository.py` | The time-series tables, monthly partitions, and insert-only storage (section 2) |
| `marketdata/gateway.py`, `feed.py`, `service.py` | The fan-out hub, the feed that stores and publishes each quote, and the quote board |
| `api.py`, `stream_api.py` | REST endpoints and the WebSocket (section 5) |

## 2. Storage (migration 0020, DEC-21)

- **Tables.**
  - `forex_instruments` is reference data.
  - `forex_quotes` and `forex_candles` are range-partitioned by month on their time column, with BRIN indexes for range scans and a btree index on (pair, time) for the latest quote.
- **What a quote row holds.** Each row carries:
  - provider and pair;
  - provider time and receipt time (UTC);
  - bid and ask;
  - the mid, which **PostgreSQL computes** as `(bid + ask) / 2`; code cannot write it;
  - data type, quality, and the feed's status at receipt.
- **Append-only.**
  - The primary key is (provider, pair, time), so a duplicate or replayed quote is dropped on insert.
  - Only complete candles are stored, so no row is ever rewritten.
- **Partitions.**
  - The migration creates DEFAULT partitions only, because a migration must not depend on the date it runs.
  - `partitions.ensure_months` creates monthly partitions ahead of time. It runs in the daily worker job `forex_maintenance` at 01:15 UTC, three months ahead, and at feed start.
  - Rows that landed in DEFAULT for a month are moved into that month's new partition in the same transaction.
  - An advisory lock serialises concurrent runs.
- **`alembic check`.** The migration environment ignores the job-made partitions (`forex_*_default`, `forex_*_pYYYYMM`).
- **Not built yet.** Retention and downsampling are not built. The soak (P13-T13) measures volume first.

## 3. Quality, staleness and outages (T02.5)

| Case | Result |
|---|---|
| Crossed quote (bid above ask) | `suspect`: stored for the record, never served or published as the latest price |
| Mid more than 5% from the pair's last good mid | `suspect` |
| Quote already older than 60 s when received | `stale` |
| Served quote older than 60 s (`forex_quote_stale_seconds`) | `freshness: stale`, `quality: stale`, with its true `age_seconds` |
| No usable quote within 7 days (`forex_quote_lookback_days`) | `freshness: unavailable`, with **no price fields** |
| Provider outage | Nothing is stored or shown in its place. The feed reports `disconnected`, and the board shows the last good quote with its true age, which becomes stale |
| Gap after a reconnect (more than 2 minutes in a pair's provider time) | Backfilled from the provider's own 1-minute candles, at most one day. Never interpolated |

## 4. Streaming client and feed status (T02.4)

**Feed status.** Every message, price or heartbeat, restarts the heartbeat window:

- `connected` while messages arrive;
- `degraded` after 10 s of silence;
- `disconnected` after 30 s. The client then drops the connection and reconnects.

The windows are half-open: silence of exactly 10 s already counts as `degraded`. The feed counts as connected only from a connection's first message, so an outage never flaps the status.

**Reconnect.**
- The backoff is exponential: 1 s, doubling, capped at 60 s, with ±20% jitter.
- It starts over after a connection that delivered.
- Refused credentials stop the client.

**Duplicates and replays.** A quote whose provider time is not after the pair's last one is dropped.

**Tests.** Time, sleeping, waiting and randomness are injected, so the tests drive heartbeat loss and reconnects on a fake clock without waiting.

**Where the feed runs.** The feed runs in the API process only when both `forex_enabled` and `forex_feed_enabled` are set. A REST call made where no feed runs reports the feed as `disconnected`. Fan-out across several API processes (Redis pub/sub) is a P16 hardening item.

## 5. API

These endpoints require sign-in, serve reference data that is the same for every user, and return 404 when the flag is off. Authentication is checked first.

- `GET /api/v1/forex/instruments`
- `GET /api/v1/forex/quotes?instrument=EUR_USD&instrument=...` returns every active pair when none is named. Each item carries:
  - bid, ask, and the derived mid (`mid_derived: true`);
  - provider time, receipt time and true age;
  - data type, quality and freshness;
  - the feed's status.
- `GET /api/v1/forex/candles?instrument=&timeframe=&price_basis=&start=&end=` returns stored candles oldest first. The `truncated` flag says when more exist. Gaps are left absent.

### WebSocket `/api/v1/forex/stream`

The protocol is documented in `stream_api.py`.

- **Authentication.** The first message must be `{"type": "auth", "token": ...}` within 5 s.
  - The token is the same OIDC access token used for REST. It is never accepted in the URL, where it would be logged.
  - The account must exist and be enabled.
  - The socket closes with 4401 when the token expires.
- **Limits per user.**
  - At most 3 sockets.
  - At most 20 pairs per socket.
  - At most 60 client messages per minute.
  - Messages of at most 4 KiB.
- **Close codes:** 4401, 4404, 4429, 1008 and 1009.
- **Updates.**
  - Updates are coalesced per pair, so memory per socket is bounded.
  - Only quotes that are not suspect are sent.
  - A subscription starts with a snapshot from storage, in which a pair with no quote is `unavailable`.
- **Rate limiting.** The REST rate limiter does not see WebSockets; the limits above take its place.

## 6. Settings

| Setting | Default | Notes |
|---|---|---|
| `forex_enabled` | false | Refused in staging and production (DEC-20, DEC-23) |
| `forex_feed_enabled` | false | Runs the simulated feed in the API process |
| `forex_provider` | `fake` | No other value is accepted (DEC-19) |
| `forex_universe` | all | Codes from `universe.json` |
| `forex_heartbeat_degraded_seconds` / `_disconnected_seconds` | 10 / 30 | |
| `forex_quote_stale_seconds` | 60 | |
| `forex_quote_lookback_days` | 7 | |
| `forex_stream_max_connections_per_user` / `_max_instruments` / `_messages_per_minute` / `_auth_timeout_seconds` | 3 / 20 / 60 / 5 | |
| `forex_candles_max` | 2000 | |

## 7. Tests

All tests are in `backend/tests/forex/`.

| File | What it covers |
|---|---|
| `test_marketdata_core.py` | Values, quality, the monitor on an injected clock, the registry, the simulated provider and the reused retry |
| `test_stream_client.py` | Heartbeat loss, reconnect, backoff and jitter, dedupe, gaps, suspect quotes, outages, refused credentials |
| `test_oanda_adapter.py` | Contract tests against synthetic recorded fixtures (`fixtures/`) |
| `test_forex_api.py` | Integration on the real database: registry, partitions, the database-derived mid, the quote board, candles, the flag, the feed, backfill, and the WebSocket's authentication, limits and expiry |
| `test_hard_rules.py` | No order, trade or position route or vendor endpoint; the simulated-only provider; the flag rules |

## 8. Open items

- **A real feed (QG-20.1, CRITICAL).** It needs a vendor and its streaming, display and redistribution licence (DEC-19), and a contract test of `oanda.py` against the real API.
- **The simulated market's calendar.** Its Friday-to-Sunday closure is approximate. The session calendar with DST and rollover is P13-T03.
- **Multi-process fan-out (Redis pub/sub)** is not built. Neither are retention and downsampling jobs.
- **Batched quote writes.** These wait for the soak (P13-T13) to measure volume.
