# Forex module: reconciliation with the platform as built (P13-T01)

Status: approved by the user on 2026-10-13 ("with the proposals as written"). It complements the approved [forex-technical-design.md](forex-technical-design.md) and [ADR-0009](../adr/0009-forex-intelligence-module.md), which are unchanged except as listed in section 4.

## 1. What changed since the design was written (2026-10-09)

The design predates P08 to P12. These are the facts of the platform now that the module must respect:

| Area | Now | Consequence for Forex |
|---|---|---|
| Reporting-currency FX (P11) | `app/modules/fx`, `fx_rates` (daily and hourly rates, `rate_type`, `rate_path`), `fx_snapshots`, refresh windows and status | **A separate concern.** Reporting rates convert the user's own money and are indicative. Forex quotes are market data with bid/ask. The two never share tables, services or labels. The new module is `app/modules/forex` with `forex_*` tables; nothing in `fx` is changed |
| Market-data providers (P08) | `MarketDataProvider`, `ResilientProvider` (retry, breaker), `FakeProvider`, registry, throttle | Quote, candle and calendar interfaces are **added beside** the existing ones. The retry, breaker and throttle are reused, not copied |
| AI tools (P10 to P12) | Allow-list in `ai/tools/base.py`, mirrored in `docs/ai-governance.md` and checked by a test; owner-scoped tools; answer policy with number provenance; evaluation datasets | Forex tools join the allow-list and the governance table together. All forecast and signal figures in an answer must come from a tool result of the same turn. New evaluation sets are added (QG-17, QG-18) |
| Opportunity pipeline (P12) | Eligibility, scoring, compatibility, validated model explanations, runs stored unchanged | Forex signals reuse the pattern: deterministic facts, a model that only explains, refusal of figures, forecasts and instructions it was not given, a template fallback |
| Demo data | DEMO universe and research, labelled everywhere, loaded only with fake market data | Forex runs on a simulated provider the same way; **simulated quotes are labelled `simulated` end to end** and never shown as live |
| Quality gates | QG-13 to QG-20 defined; QG-13 to QG-19 are verified in P13-T12 | Unchanged |
| Process | One PR per task; evidence logged; user approval gates | Unchanged |

## 2. Decisions (DEC-19 to DEC-24)

| ID | Decision |
|---|---|
| DEC-19 | **Provider: fixture-only.** The provider abstraction, an OANDA-style adapter built from the vendor's public documentation, and the fake provider are built with synthetic fixtures. **No key, no live call, no real quote is shown to anyone.** The vendor choice and its streaming, display and redistribution licence stay open and block any real feed (QG-20.1, CRITICAL). The evaluation matrix in the design (coverage including USD/KES and USD/ZAR, bid/ask, update rate, history, calendar, display rights, cost, region, SLA) is filled in when a vendor is chosen |
| DEC-20 | **Launch markets: Kenya and the UAE, as for P12. Regulatory classification is open and goes to legal review in P13-T14.** Until a reviewer answers, the module is information and paper trading only, every screen carries the not-advice and not-a-broker wording, and the module cannot be enabled outside development. The same reviewer (Kelvin Mutisya David, DEC-10) is asked to cover Forex in the same way as P12 |
| DEC-21 | **PostgreSQL native monthly range partitioning with BRIN indexes** for quotes and candles. TimescaleDB only if measured volume (P13-T13) justifies it |
| DEC-22 | **v1 model scope:** random-walk, no-change and drift baselines, ARIMA/SARIMA (statsmodels), gradient boosting (LightGBM, XGBoost) and Random Forest (scikit-learn), and volatility models. **LSTM, GRU and Transformer models are research-only**, behind a flag and a separate gate, never the default. New libraries are added with a licence check and pass the dependency audit in CI |
| DEC-23 | **Ship after v1, behind a feature flag**, off by default. Turning it on in production needs core hardening (P16), the staging smoke tests (P15-T11), DEC-19 and DEC-20 |
| DEC-24 | **A reviewed, versioned contract-specification table** (pip location, lot size, margin rules) per instrument, with a check against the provider's data when one exists. A mismatch is reported, never silently corrected |

## 3. Hard rules written into the design (acceptance criteria)

These are stated in the design (sections 1, 9, 11, 15) and are now **tested rules for every P13 task**:

1. **Decision support and paper trading only.** No order-placement code path, no trading credentials, no broker connection. A test scans the module for order or execution endpoints.
2. **No guaranteed-return language.** The answer policy and the evaluation sets already refuse it; P13 adds forecast-specific sets.
3. **Paper balances never mix with real wealth.** Paper accounts, orders, positions and journal are separate tables and services, excluded from net worth, holdings, allocation and every analytics endpoint. A test creates paper activity and checks every real figure is unchanged.
4. **Prices are never invented, interpolated or shown as live when stale, indicative, delayed or simulated.**
5. **Probabilities say "requires calibration" until calibration passes**, and every model is reported against the random-walk and no-change baselines, including when a baseline wins.
6. **Money, pips, lots and position sizes are Decimal.** Indicators, pip values and sizes are deterministic with reference tests.

## 4. Amendments to existing documents

| Document | Change |
|---|---|
| `docs/SOLUTION_INTENT.md` section 34 and the implementation guide | Already present (2026-10-09). Confirmed; no change |
| ADR-0009 | Accepted; unchanged. Decisions above are recorded here and in the register |
| `forex-technical-design.md` section 19 | Open decisions updated to point here |
| `EXECUTION_PLAN.md` decision register | DEC-21, DEC-22, DEC-23, DEC-24 resolved; DEC-19 resolved as fixture-only with the licence still open; DEC-20 scheduled for P13-T14 (on 2026-10-14 the licence and regulatory reviews moved to P17-T09, Forex production enablement) |
| `reports/quality` | QG-13 to QG-20 evidence is written by P13-T12 and later |

## 5. Impact assessment (P13-T01.1)

- **Architecture:** a new module (`app/modules/forex`) with its own routers, services, tables and worker jobs. It depends on the platform (auth, audit, cache, provider resilience, AI tool layer) and nothing depends on it, so it can be switched off or removed without touching the core.
- **Security:** a new authenticated WebSocket; per-user subscription limits; no new secrets while the provider is fixture-only; paper-trading data is owner-scoped like all user data and covered by cross-user tests; no trading credentials exist.
- **Data and operations:** time-series volume drives partition and retention jobs; a scanner and backtests run in workers, not in requests; the soak (P13-T13) runs on the local stack with simulated feeds, outages and clocks.
- **Cost:** none while the provider is fixture-only. A real feed is a separate budget decision with DEC-19.
- **Mobile:** reached from More and a Home shortcut (ADR-0002 keeps five tabs); the feed-status chip and the DEMO or simulated labels are part of the design system.
