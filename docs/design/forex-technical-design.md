# Forex Trading Intelligence module: technical design

Status: **Proposed**, awaiting user approval (P15-T01). Nothing in this document is implemented. Related: [ADR-0009](../adr/0009-forex-intelligence-module.md), `EXECUTION_PLAN.md` phase P15 (tasks FX-01…FX-14 = P15-T01…T14), quality gates QG-13…QG-20 (QG-FX-01…08).

## 1. Purpose and boundary

An AI-assisted **decision-support and paper-trading** module inside WealthSphere: live market data, indicators, probabilistic forecasts, a transparent opportunity ranking, deterministic trade-risk calculation, backtesting, paper trading and a Forex Copilot.

Hard boundaries (they apply to every task in P15):

1. **No live trade execution.** The build contains no order-placement code path and no broker trading credentials. Enabling execution needs a separate, explicitly approved phase, regulatory review and dedicated trading risk controls.
2. **No guarantees.** A forecast, score or setup is never presented as a guaranteed or expected profit. Output is "research candidate", "scenario", "illustrative level".
3. **Paper trading is separate from wealth.** Virtual balances never enter net worth, holdings, analytics or the AI's view of real portfolios.
4. **The backend is authoritative** for prices, indicators, forecasts, risk and backtests. Flutter formats and displays. The LLM only explains tool results.
5. **No invented prices.** If a provider is unavailable the system says so. Delayed, indicative or simulated values are never shown as live executable quotes.
6. **Money and prices are `Decimal`** (ADR-0003, ADR-0006). `double` is allowed only inside model training/inference math and at the chart plotting boundary; every stored or displayed price, pip value, size and P/L is Decimal.

## 2. Impact on the existing architecture

| Area | Impact |
|---|---|
| Modular monolith | New backend modules under `backend/app/modules/forex/` (sub-packages below). Same layering as ADR-0004 (api / service / repository / schemas). No new deployable service in v1. |
| Market data (P08) | The P08 provider abstraction is **extended** with quote streaming and candles for forex; it is not duplicated. DEC-04 (providers) is widened by DEC-19 for forex streaming rights. |
| Database (ADR-0005) | New migrations: instruments, quotes, candles, economic events, forecasts and model registry, signals, backtests, paper accounts/orders/positions/journal. Time-series volume decides DEC-21 (partitioning vs TimescaleDB). |
| AI (P10, P11) | New allow-listed tools for the orchestrator; same four-section answer structure, same output guard. Forex tools are read-only except paper-trading simulation inside the user's own paper account. |
| Mobile | New "Forex" section reached from More (and Home shortcut) so the approved five-tab navigation (ADR-0002) is unchanged. Reuses the design system (cards, charts, `DataAsOfLabel`, `DemoBadge`, state widgets). Adds a `PaperTradingBadge`. |
| Security | New endpoints go through the existing authn/authz and ownership harness (P04). Provider credentials only in the secret store. Streaming is authenticated. Paper data is per-user with IDOR tests. |
| Observability | Feed status, staleness, stream lag, model drift and backtest job metrics added to the OTel pipeline. |
| Infrastructure | Long-lived WebSocket connections and a worker for scanning/backtests (Celery/RabbitMQ as already planned). TimescaleDB only if DEC-21 selects it. |
| Intent documents | `SOLUTION_INTENT.md` section 30 (non-goals) is clarified and a Forex extension section is added; brief and guide get a matching section. |

## 3. Module layout

```text
backend/app/modules/forex/
  instruments/   instrument registry, contract specs, configurable universe
  marketdata/    provider interface, adapters, ingestion, streaming gateway, quality + staleness
  candles/       aggregation (1m..1M), gap handling, session calendar
  analysis/      indicators, market structure, price-action detectors
  calendar/      economic events, central-bank decisions, rate differentials
  forecast/      features, models, registry, evaluation, calibration, drift
  signals/       setup rules, scoring, ranking, market-condition classifier
  risk/          pip value, position size, margin, costs, exposure, limits
  backtest/      engine, cost/slippage models, metrics, walk-forward, reports
  paper/         virtual accounts, orders, positions, journal, analytics
  ai_tools/      allow-listed tool definitions for the orchestrator
mobile/.../features/forex/   presentation, data (repositories), domain
```

Dependency rule: `ai_tools` and `api` call services; `signals` consumes `analysis`, `forecast`, `calendar`, `risk`; `backtest` consumes `analysis`, `signals`, `risk`; `paper` consumes `risk` and `marketdata`; nothing consumes `ai_tools`.

## 4. Market data

### 4.1 Provider interface (extends P08)

```text
QuoteProvider:   subscribe(instruments) -> stream[Quote]; snapshot(instrument) -> Quote | Unavailable
CandleProvider:  candles(instrument, timeframe, start, end) -> list[Candle]
CalendarProvider: events(start, end, currencies) -> list[EconomicEvent]
ProviderHealth:  status(), last_message_at, latency
```

Providers are evaluated in FX-01/FX-02 against: instrument coverage (including USD/KES, USD/ZAR), bid/ask availability, streaming and update rate, history depth, economic-calendar availability, redistribution and in-app display rights, cost, geographic availability and SLA. Candidates to evaluate: OANDA, Interactive Brokers and other licensed vendors (DEC-19). No provider is assumed to offer all pairs or rights.

### 4.2 Stored quote

| Field | Notes |
|---|---|
| provider, instrument | Registry key, e.g. `EUR_USD` |
| bid, ask | Decimal; mid is **derived** and flagged `derived=true` |
| ts_provider, ts_received | UTC. Provider time and receipt time are both kept |
| data_type | `tradable_quote`, `indicative_rate`, `delayed`, `simulated` |
| quality | `ok`, `suspect` (crossed or out-of-band), `stale` |
| feed_status | `connected`, `degraded`, `disconnected` at receipt time |

Tradable broker quotes and indicative exchange rates are different `data_type`s end to end; the API and UI show the type. Less liquid pairs default to `indicative_rate` unless the provider says otherwise.

### 4.3 Streaming and resilience

- Backend subscribes once per instrument per provider, fans out to clients over an authenticated WebSocket (`/forex/stream`) with per-user subscription limits.
- Heartbeat: if no message arrives within the configured window, status becomes `degraded`, then `disconnected`; quotes older than the staleness threshold are marked `stale` and the UI greys them with "Stale since …".
- Reconnect with exponential backoff and jitter; resubscribe; gap detection triggers a candle backfill; deduplicate by (provider, instrument, ts).
- Cache last good quote with its timestamp. A cached quote is returned with its true age, never as current.
- Mobile: foreground subscribe, background unsubscribe, resume on foreground, backoff on network loss, and a visible feed-status chip.

### 4.4 Storage

Candles and quotes are append-only. v1 default (DEC-21, proposed): native PostgreSQL range partitioning by month on `ts` with BRIN indexes, retention and downsampling jobs; TimescaleDB is adopted only if measured volume justifies the extra infrastructure. Instrument is a foreign key, so the universe is configuration, not code.

### 4.5 Timeframes and sessions

Timeframes: 1m, 5m, 15m, 30m, 1H, 4H, 1D, 1W, 1M. Higher timeframes are **aggregated from 1m/stored candles by the backend** with an explicit session calendar (FX week opens Sunday, closes Friday, DST handling, per-pair rollover time). Missing candles are marked, never filled with invented values. Trading-session information (Sydney/Tokyo/London/New York overlaps) comes from the session calendar.

## 5. Technical analysis engine

Pure functions over candle arrays, `Decimal` in and out, deterministic, no I/O.

| Group | Items |
|---|---|
| Trend | SMA, EMA, MACD, ADX |
| Momentum | RSI, Stochastic, Rate of change |
| Volatility | ATR, Bollinger Bands |
| Structure | swing highs/lows, support/resistance (clustered pivots with touch counts), breakouts, trendlines, channels |
| Price action | candlestick patterns, continuation, reversal, consolidation, breakout-and-retest |

Rules: warm-up periods are explicit (an indicator returns `None` before it has enough data), smoothing conventions (Wilder vs standard EMA) are documented per indicator, results are tested against independently computed reference vectors, and the LLM never produces an indicator value. Pattern detectors return the candles involved and a rule identifier so the UI and AI can cite them.

## 6. Economic calendar and macro intelligence

`EconomicEvent`: name, affected currencies, scheduled time (UTC), actual / forecast / previous (nullable), unit, importance, source, retrieved_at. Central-bank decisions and rate differentials are stored with their source.

- **Confirmed data** (event values, central-bank statements) and **interpretation** (volatility implications, AI commentary) are different fields and are labelled differently in the API and UI.
- Event risk windows (for example 30 minutes before and 60 after high-importance events) are exposed to the scanner and risk engine; they raise the macro-event-risk component of the score and add a warning to trade setups.
- Geopolitical developments are not auto-classified as facts: they enter only as source-attributed items with timestamps.

## 7. Prediction engine

### 7.1 Framework

A `Forecaster` interface (`fit`, `predict_distribution`, `version`, `features_used`) with a registry. Model families: baselines (random walk, no-change, drift), ARIMA/SARIMA (statsmodels), gradient boosting (LightGBM, XGBoost), Random Forest, volatility models (GARCH-family or realised-volatility regressors), ensembles. LSTM/GRU/Transformer models are **research-only** (DEC-22): they run behind a flag, are never the default, and ship only if they beat the baselines out of sample and survive QG-15.

### 7.2 Outputs per pair and horizon (15m, 1h, 4h, 24h, 1w)

Probability up and down, predicted return distribution (quantiles), expected volatility, forecast price interval, calibration status and metrics, out-of-sample performance, data freshness (`as_of`), model version and feature-set hash.

### 7.3 Evaluation methodology (non-negotiable)

- **Time-series-aware splits only**: expanding or rolling-window walk-forward with a purge/embargo gap equal to the label horizon; no shuffled cross-validation.
- **No leakage**: features at time t use data with timestamp ≤ t; labels use t+h; a deliberately leaky test model must fail the leakage test.
- **Baselines always reported**: direction accuracy, log-loss, Brier score, pinball loss, CRPS, interval coverage and RMSE/MAE of return versus random walk and no-change, even when the baseline wins. If a model does not beat the baseline, it is shown as "no demonstrated edge".
- **Calibration**: reliability curves, expected calibration error, isotonic or Platt recalibration trained on a separate calibration window. A probability is labelled **Requires calibration** until ECE and reliability pass thresholds on held-out data. A model probability is never described as a success rate.
- **Intervals**: empirical coverage of the nominal interval is measured and reported (for example whether the 80% interval covers about 80%).
- **Drift monitoring**: rolling calibration and error versus baseline, feature distribution drift (PSI/KS); breach disables the model's forecasts for the pair and shows "forecast unavailable" until retraining is approved.
- **Reproducibility**: seeds, data snapshot hash, code version and hyper-parameters recorded with each model version.

## 8. Signal engine and Opportunity Ranking Dashboard

### 8.1 Setups

Trend continuation, breakout, reversal, range trading, momentum, mean reversion. Each setup is a named rule set (`rule_id`, version) over indicators and structure, with a defined invalidation level.

### 8.2 Transparent opportunity score

```text
score = Σ weight_i × component_i        (components normalised to 0..1, weights published)
components: trend_strength, momentum, volatility_suitability, spread_and_cost, liquidity,
            technical_confluence, macro_event_risk (penalty), forecast_calibration,
            strategy_history (out-of-sample), risk_reward
```

Weights and normalisation live in versioned configuration and are shown in the API response (`explanation.factors[]` with value, weight, contribution). The score ranks **research candidates**; it is not a probability of profit. A candidate with stale data, an unhealthy feed, a high-impact event window or an uncalibrated forecast is demoted or excluded and says why.

### 8.3 Ranking Dashboard

A list ranked by score showing pair, **market condition** (trending, consolidating, high volatility, momentum strengthening), **opportunity type** (trend continuation, breakout, range, momentum, mean reversion, reversal), **risk** (low, medium, medium-high, high from volatility, spread and event risk), score, data freshness and feed type. Filters: timeframe, setup type, risk, major/minor/emerging. Tap opens Trade Setup Details (levels, factors, risks, costs, forecast with calibration status, Simulate Trade, Add to Watchlist). The example table in the request (EUR/USD trending, GBP/JPY high volatility, and so on) is illustrative; no pair is shown as a current assessment unless it comes from live scored data, and DEMO fixtures carry the DEMO label.

### 8.4 Opportunity card contract

Pair, scenario ("Bullish scenario", "Potential buy setup"), timeframe, illustrative entry/stop/target generated from the rule and ATR with timestamps, risk and reward in pips, risk/reward, model up-probability **with calibration status**, supporting factors, key risks, estimated costs, data as-of, feed type, rule and model versions. Wording is "illustrative level", "scenario", "setup", never "buy now", "guaranteed" or "will".

## 9. Trade risk management engine

All arithmetic in `Decimal`, rounding per ADR-0006, explicit and tested.

**Inputs:** account balance and currency, risk percentage, pair, entry, stop, take-profit, contract specification (contract size, pip size/location, margin requirement, lot step, min/max), broker spread, commission, slippage assumption, leverage.

**Pip value** is derived, never a constant:

```text
pip_value_in_quote   = contract_size × pip_size                  (per 1.00 lot)
pip_value_in_account = pip_value_in_quote × rate(quote → account) (rate from the same timestamped feed;
                                                                   =1 when quote == account currency)
```

Examples to verify: EUR/USD with USD account (quote = account), USD/JPY with USD account (quote JPY, convert via USD/JPY, pip size 0.01), EUR/GBP with USD account (quote GBP, convert via GBP/USD), USD/KES (indicative rate, flagged).

**Position size:** `units = risk_amount / (stop_distance_in_pips × pip_value_per_unit + cost_per_unit)`, rounded **down** to the lot step so realised planned risk never exceeds the limit; rejected below minimum size.

**Outputs:** size, pip value, potential loss and profit (before and after costs), risk/reward (before and after costs), margin required (`notional / leverage`, margin-closeout warning levels), estimated transaction costs (spread + commission + slippage), exposure (net per currency and per pair across paper positions) and account impact (% of balance). Configurable limits: max risk per trade, max daily/weekly paper loss, max leverage, max exposure per currency; breaches return warnings, not silent clipping.

**Required disclosures in every response:** stop-loss orders do not guarantee the maximum realised loss (gaps, slippage, weekend risk); leverage amplifies losses; values are estimates from the configured specifications.

## 10. Backtesting

Event-driven engine on stored candles/quotes with a strictly advancing clock: the strategy sees only data up to the current bar close and orders fill at the next bar with modelled spread, commission and slippage.

- Metrics: total return, max drawdown, win rate, profit factor, Sharpe, Sortino, average trade, expectancy, longest losing streak, exposure, cost and slippage sensitivity.
- Walk-forward: optimise on window k, test on window k+1 only; report in-sample and out-of-sample separately; parameter-stability and benchmark (buy-and-hold, random-entry, no-trade) comparisons.
- Controls tested: look-ahead (a strategy that peeks must fail), leakage, survivorship of instruments, session/gap handling, cost inclusion, determinism (same inputs and seed produce the same report hash).
- Reports are stored with data snapshot hash, code version and parameters. **Backtested, paper-traded and live-observed performance are separate labelled series** and never summed.

## 11. Paper trading and journal

Virtual account (configurable starting balance and currency, default clearly marked), simulated market/limit entries filled at the feed's bid/ask (never mid) with the same cost model as backtests, virtual SL/TP evaluated on quote updates, positions, closed trades, realised/unrealised P/L, journal entries with notes and strategy tags, performance dashboard. Every API response and screen carries `PAPER TRADING`. Tables are separate from portfolio tables; there is no foreign key into holdings, transactions or net-worth views, and a test asserts no code path reads paper tables in real analytics. Paper results may feed *separate* simulated-performance analytics.

## 12. AI Forex Copilot

Extends the AI orchestrator (ADR/AI governance unchanged). New allow-listed, authorised, read-only tools:

`get_forex_quote`, `get_candles`, `get_indicators`, `get_market_structure`, `get_forecast`, `get_opportunities`, `get_economic_events`, `calculate_trade_risk`, `get_backtest_summary`, `get_paper_performance`, `explain_forecast_change`.

Rules: every number in an answer comes from a tool result carrying timestamp, source and (for forecasts) model version and calibration status; answers keep the four sections (observed data, calculated, assumptions, AI interpretation); stale or unavailable data produces a qualified or refused answer; the output guard blocks guaranteed-profit, "sure thing" and personalised-advice language and any request to place a trade ("I can't place trades; I can simulate one in your paper account"). The model cannot call a tool that mutates anything except creating a **paper** trade on explicit user confirmation.

## 13. API surface (proposed, OpenAPI-first)

`GET /forex/instruments`, `GET /forex/quotes`, `WS /forex/stream`, `GET /forex/candles`, `GET /forex/indicators`, `GET /forex/forecasts`, `GET /forex/opportunities` (ranking), `GET /forex/opportunities/{id}`, `GET /forex/calendar`, `POST /forex/risk/calculate`, `POST /forex/backtests`, `GET /forex/backtests/{id}`, `/forex/paper/accounts|orders|positions|journal`, `/forex/watchlist`, `/forex/alerts`. Monetary and price fields are strings; every response carries `as_of`, `data_type`, `feed_status` and versions where relevant.

## 14. Mobile UX

Entry from More → Forex Intelligence and a Home shortcut card; the five tabs are unchanged. Screens (design language unchanged: Midnight Navy `#102A43`, Emerald Teal `#0D9488`, Warm Gold `#F2B84B`, light/dark, 2.0x text, RTL):

Forex Overview · Live Currency Markets · Interactive Chart · AI Market Predictions · **Opportunity Ranking Dashboard** · Trade Opportunity Scanner · Trade Setup Details · Risk/Reward Calculator · Economic Calendar · Strategy Backtesting · Paper Trading · Trading Journal · Forex Copilot · Forex Alerts.

New shared widgets: `QuoteTile` (bid/ask, spread in pips, change, `FeedStatusChip`, as-of), `CandleChart` (fl_chart or custom painter, decimated for streaming, with indicator overlays and a "view as table" fallback), `OpportunityCard`, `RankingRow`, `PaperTradingBadge`, `CalibrationBadge` ("Requires calibration" / "Calibrated"), `RiskDisclosure`. Streaming performance rule: updates are coalesced (max ~4 repaints/s per chart) and chart data is bounded. A DEMO-first fixture pass lets screens be reviewed before the backend is live, as in P03.

## 15. Security, privacy and compliance

- Same OIDC authn/authz; per-user paper data; IDOR tests per endpoint; rate limits on stream subscriptions and risk/backtest endpoints.
- Provider and broker secrets only in the secret store; no trading-capable credentials are ever provisioned.
- Audit events for paper trades, alert rules, backtest runs and AI tool calls.
- Disclosures (risk, not advice, past performance, leverage) are reviewed in FX-14. Launch-market regulatory classification (DEC-20) and market-data licensing (DEC-19) are release blockers (QG-20, both CRITICAL).
- Notification preferences reuse the profile settings; alerts are informational, not trade instructions.

## 16. Observability

Metrics: stream lag, messages/s, reconnects, stale-quote ratio per provider, model drift/calibration, scan duration, backtest queue time. Alerts: feed disconnected beyond threshold, staleness SLO breach, drift breach. Logs never contain provider keys or full account balances.

## 17. Test strategy

| Area | Tests |
|---|---|
| Market data | recorded-fixture contract tests, stale/outage/reconnect with injected clock, timestamp/timezone, crossed-quote rejection |
| Indicators | independently computed reference vectors, property tests, gap handling |
| Forecast | leakage tests, walk-forward and calibration reports, baseline comparison, interval coverage |
| Risk | reference cases per quote/account currency, rounding, property tests (size × stop distance ≤ risk), margin cases |
| Backtest | look-ahead failure test, cost inclusion, determinism hash |
| Paper | isolation test (no reads from real analytics), IDOR, simulated fills at bid/ask |
| AI | evaluation set with stale data, adversarial prompts, guarantee-language guard |
| Mobile | widget/golden for new widgets in light/dark/2.0x/RTL, streaming resilience, lifecycle, integration tests |

## 18. Out of scope for P15

Live order execution, broker account linking for trading, automated or copy trading, leveraged position management on real accounts, tax advice, social/signal selling. Any of these needs a new approved phase.

## 19. Open decisions

DEC-19 provider and licence · DEC-20 launch markets and regulation · DEC-21 time-series storage · DEC-22 model scope · DEC-23 release strategy · DEC-24 contract-spec source. Recommendations: after-v1 release behind a feature flag (DEC-23); PostgreSQL partitioning first (DEC-21); boosting + statistical baselines in v1 with deep models research-only (DEC-22); a reviewed, versioned contract-spec table with provider verification (DEC-24).
