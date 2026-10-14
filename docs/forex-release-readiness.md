# Forex release and regulatory readiness pack (P13-T14, DEC-19, DEC-20)

**Reviewer:** Kelvin Mutisya David (named for DEC-20; the same reviewer as P12, DEC-10). **Decision owner:** the user. **Prepared by:** Claude (engineering draft, 2026-10-14). **Status (2026-10-14): the disclosures (section 4) are approved by the user as drafted, and the release decision (section 6) is approved: not released. The licence review (section 2) and the regulatory review (section 3) have not been done.** By the user's plan change of 2026-10-14 they move to P17-T09 (Forex production enablement), which must pass before forex is switched on outside development (QG-20.1 and QG-20.2, both CRITICAL, still apply in full). Nothing in this pack is legal advice.

**What remains, in P17-T09, if forex is to be offered:**
1. Choose a market-data provider and answer the licence checklist in section 2 against its contract (QG-20.1).
2. The reviewer answers the regulatory questions in section 3 for Kenya and the UAE (QG-20.2) and reviews the section 4 disclosures for the real data, including the observations.
3. Sign the open lines of the table in section 7.

Any wording changes are then applied with the tests that pin the wording, and QG-20.1 and QG-20.2 are checked with the signed answers as evidence.

**Scope:** the Forex module of P13 in the API and the mobile app. That covers market data, indicators, the economic calendar, forecasts, the opportunity ranking, the risk calculator, backtests, paper trading and the Forex Copilot. The P12 wording, signed off in [compliance-review-p12.md](compliance-review-p12.md), is not repeated here.

## 1. Where the module stands (2026-10-14)

| Fact | Evidence |
|---|---|
| Every price comes from the **simulated** provider and is labelled `simulated` end to end. No real quote has been fetched or shown to anyone | `test_hard_rules.py`: `test_the_only_configurable_provider_is_simulated`, `test_the_built_provider_labels_every_price_simulated`; the soak report [p13-t13-forex-soak.md](../reports/quality/p13-t13-forex-soak.md) (0 mismatches, all simulated) |
| The module is **off by default** and **cannot be switched on** outside the `local` and `test` environments | `Settings._forex_only_in_development` in `backend/app/core/config.py`; `test_forex_is_off_by_default`, `test_forex_cannot_be_switched_on_outside_development` |
| **No live execution exists.** No route places orders, and no forex source outside paper trading names an order endpoint or call | `test_no_forex_route_places_orders`, `test_no_forex_source_names_an_order_endpoint_or_call` |
| Paper trading is **virtual and separate**. Paper money never enters net worth, holdings or real analytics, and no real-money module reads the paper tables | `test_paper_money_never_reaches_net_worth`, `test_no_real_money_module_reads_paper_tables` (`tests/forex/test_paper_api.py`); the paper tables are in the IDOR sweep of the integrity suite |
| The Copilot is **read-only**. It refuses to place trades and names the paper account instead | `refusal.py` (`trade_execution`), `tests/ai/test_forex_chat.py`, the `forex_safety` evaluation set (70 cases, zero tolerance) |
| Quality gates QG-13 to QG-19 are **passed** | [p13-forex-gates-summary.md](../reports/quality/p13-forex-gates-summary.md) |

## 2. Market-data licence checklist (P13-T14.1, DEC-19, QG-20.1)

No provider has been chosen. The adapter in `marketdata/oanda.py` was built from the vendor's public documentation, with synthetic fixtures, and holds no key. Before any real feed reaches a user, the chosen provider's contract must allow each use below. Answer per provider, quoting the clause.

| # | What WealthSphere does with the data | Where in the code | Licence question | Answer (clause) |
|---|---|---|---|---|
| 2.1 | Streams bid and ask quotes into the backend continuously for the configured universe (12 pairs in the soak) | `marketdata/feed.py`, `stream.py` | Is streaming to a server (not a desktop terminal) allowed, and for how many instruments? | |
| 2.2 | **Displays** quotes to signed-in users in the app, each with its type and age | `/api/v1/forex/quotes`, the WebSocket `/api/v1/forex/stream`, the app's forex screens | Is display to retail end users allowed? Per-user fees, exchange fees or non-professional declarations? Must the display be delayed? | |
| 2.3 | **Stores** every quote and one-minute to daily candles, kept for history (partitioned by month) | `forex_quotes`, `forex_candles` | Is storage allowed, for how long, and must it be deleted when the contract ends? | |
| 2.4 | **Derived data**: indicators, patterns, forecasts, signal rankings, backtests and paper fills are computed from the stored prices and shown to users | `analysis`, `forecast`, `signals`, `backtest`, `paper` | Are derived values (not the raw prices) free to display and keep? Do they remain ours after the contract ends? | |
| 2.5 | **AI use**: the Copilot's tools return quotes and derived values to an external model provider, which writes the explanation (ADR-0017) | `app/ai/tools/forex.py` | May the data be sent to a third-party AI service for processing? Is it a redistribution? Is training on it excluded? | |
| 2.6 | **Redistribution**: none outside our own authenticated users. There is no public or partner API, and no export of raw prices | Every forex endpoint requires sign-in | Confirm that showing data to our own users is not redistribution under the contract | |
| 2.7 | **Caching**: the latest quote per pair is held in memory and fanned out to every subscriber | `marketdata/gateway.py` (`QuoteHub`) | Is one upstream connection serving many users allowed (fan-out), or is a per-user entitlement required? | |
| 2.8 | **Attribution**: each price carries its provider name and type | `QuoteOut.provider`, `QuoteOut.data_type` | What attribution or logo must be shown, and where? | |
| 2.9 | **Tradable or indicative**: we label each price `tradable_quote`, `indicative_rate`, `delayed` or `simulated` and never call it executable | `marketdata/types.py` `DataType`; the app's "Not an executable quote" label | Which label applies to the provider's prices under the contract? | |
| 2.10 | **Economic calendar**: DEMO events today | `calendar/` | A licence for a calendar source (if one is wired) | |
| 2.11 | **Cost and limits**: rate limits, connection limits, cost per month | `forex_*` settings | Do our settings fit within the plan's limits? | |

**Until 2.1 to 2.9 are answered for a named provider, QG-20.1 stays open (P17-T09.1).** The configuration also refuses any provider other than the simulated one (`test_the_only_configurable_provider_is_simulated`).

## 3. Regulatory questions per launch market (P13-T14.2, DEC-20, QG-20.2)

The launch markets are **Kenya and the UAE** (DEC-20). I have not stated any regulator's requirements, because I cannot verify them. The regulators named below are where a reviewer might start, not findings. Answer each question per market: Kenya; UAE onshore; DIFC; ADGM.

| # | Question for the reviewer | Kenya | UAE (onshore, DIFC, ADGM) |
|---|---|---|---|
| 3.1 | Is showing forex quotes, indicators, forecasts and a ranked list of pairs to retail users "investment advice", "arranging deals" or another regulated activity? Does it need a licence (for example with the Capital Markets Authority in Kenya, or the SCA, DFSA or FSRA in the UAE)? | | |
| 3.2 | Does the opportunity ranking with entry, stop and target levels count as a personal recommendation, given that it is the same for every user and not based on their circumstances? | | |
| 3.3 | Does the risk calculator (position size from the user's own balance and risk percentage) count as personalised advice? | | |
| 3.4 | Is paper trading with virtual money regulated? Does it need any wording, such as a statement that paper results do not predict real results? | | |
| 3.5 | Are there mandatory **leveraged-product risk warnings** for retail forex (for example a percentage of retail accounts that lose money), and must they appear even with no execution? | | |
| 3.6 | Does the Forex Copilot (an AI that explains these figures and refuses trading instructions) raise any additional obligation? | | |
| 3.7 | Is any marketing restriction triggered by a "forex" section in the app (promotion of leveraged products to retail users)? | | |
| 3.8 | Is residence the right test (the app stores the user's residence country), and must the module be hidden in other countries? | | |
| 3.9 | Must the disclosures be shown in Swahili or Arabic? | | |
| 3.10 | Data protection: forex questions and paper positions are user data sent to the model provider as tool results (ADR-0017). Is a disclosure needed? | | |

**Until each market's column is answered and signed, QG-20.2 stays open (P17-T09.2).**

## 4. Disclosure inventory (P13-T14.3, QG-20.3)

All statements are English only. The server sends notices with every response, and the app shows them. The app's own strings are in `lib/l10n/app_en.arb`.

| # | Where the user sees it | Wording | Source |
|---|---|---|---|
| 1 | Quotes and the stream, every response | Forex information only, not advice. WealthSphere is not a broker and places no trades. Each price shows its type (tradable, indicative, delayed or simulated) and its age; a stale price is never shown as current, and a missing one is never filled in. | `marketdata/schemas.py` NOTICE |
| 2 | Candles | Candles as the provider published them. A period with no candle is absent, never filled in. Forming candles are not stored. | `marketdata/schemas.py` CANDLE_NOTICE |
| 3 | Indicators and patterns | Computed by the backend from stored candles with fixed, documented formulas. Descriptive only: an indicator or pattern is not a forecast, a probability or advice. | `analysis/schemas.py` NOTICE |
| 4 | Economic calendar | Scheduled releases with their source and time. Confirmed values (actual, previous) are facts as published; the consensus forecast is an expectation; commentary is not data. A risk window marks when prices often move around a release; it is not a prediction. DEMO items are fictional. | `calendar/api.py` NOTICE |
| 5 | Forecasts | A statistical estimate from past prices: not a prediction of what will happen, not advice, and never a guaranteed return. Probabilities are model outputs, not success rates; intervals can be wrong. | `forecast/api.py` NOTICE |
| 6 | Opportunity ranking | Research candidates ranked by a published formula from stored prices. Not advice, not a recommendation to buy or sell, and not a probability of profit. Levels are illustrative: markets can move past any level, and stops do not cap a loss. WealthSphere places no trades. | `signals/api.py` NOTICE |
| 7 | Risk calculator | A position-size and risk calculator for study and paper trading. Not advice and not a recommendation; WealthSphere places no trades. Values are estimates. | `risk/schemas.py` NOTICE |
| 8 | Risk calculator, always | A stop-loss does not guarantee the maximum loss: prices can gap or slip past it, for example over a weekend or around news. | `risk/engine.py` DISCLOSURES |
| 9 | Risk calculator, always | Leverage amplifies losses as well as gains; a loss can exceed the margin placed. | `risk/engine.py` DISCLOSURES |
| 10 | Risk calculator, always | All values are estimates from the configured contract specifications and the stated rates and costs. This is a calculator for study and paper trading, not advice; nothing is placed. | `risk/engine.py` DISCLOSURES |
| 11 | Risk calculator, when they apply | Warnings for: risk above the limit; leverage above the limit; insufficient margin; margin use above the limit ("a small move could lead to a margin call"); a non-tradable or stale conversion rate; unknown spread ("costs are understated"); unreviewed contract specifications ("not a broker's terms"); a less liquid pair ("spreads, slippage and gaps can be much larger than assumed"). | `risk/engine.py` warnings |
| 12 | Backtests | Backtested on stored bars with modelled spread, slippage and commission. A backtest is a study of how a published rule would have behaved, not a forecast: it does not show what will happen, and results on simulated data say nothing about real markets. Backtested, paper and live results are separate series and are never combined. | `backtest/report.py` NOTICE |
| 13 | Paper trading, every response, plus the `X-Trading-Mode: PAPER TRADING` header | PAPER TRADING: virtual money and simulated fills at the stored bid and ask, with modelled slippage and commission. Nothing is sent to a broker. Paper results are a separate series: they never enter net worth, holdings or the analytics of a real portfolio, and are never combined with backtested or live-observed results. | `paper/api.py` NOTICE |
| 14 | Forex Copilot, when the answer uses simulated prices | Forex prices in this answer come from the simulated development feed, not a live market. | `guards.py` SIMULATED_NOTICE |
| 15 | Forex Copilot, uncalibrated forecasts | The forecast probability used here requires calibration and is not reliable as a probability. | `guards.py` CALIBRATION_NOTICE |
| 16 | Forex Copilot, rankings | Research candidates are ranked by a published formula; they are not recommendations to buy or sell and not probabilities of profit. | `guards.py` RESEARCH_NOTICE |
| 17 | Forex Copilot, paper results | Paper results are virtual money and simulated fills, never combined with backtested or real results. I cannot place or manage trades; you can simulate one in a paper account. | `guards.py` PAPER_NOTICE |
| 18 | Forex Copilot, backtests | Backtested results are a study of a rule on past bars, not a forecast. | `guards.py` BACKTEST_NOTICE |
| 19 | Forex Copilot, calendar | Economic events in this answer are DEMO data, not a real calendar. | `guards.py` DEMO_NOTICE |
| 20 | Forex Copilot, stale data and forecasts (shared with P10) | Some of the data behind this answer is stale or incomplete ({tools}); figures may not reflect current values. / Forecasts and goal estimates are illustrations under the stated assumptions, not predictions or guaranteed returns. | `guards.py` STALE_NOTICE, FORECAST_NOTICE |
| 21 | Copilot refusal of a trade instruction | I can explain and compare, but I cannot place orders or move money. Trades must be made with your broker. For forex, you can simulate a trade in a paper account (PAPER TRADING). | `refusal.py` `trade_execution` |
| 22 | Forex home screen | Simulated and research data for study and paper trading. Not advice; nothing is traded. | `fxNotice` |
| 23 | More menu entry | Simulated markets, research and paper trading | `fxEntrySubtitle` |
| 24 | Paper trading screens | PAPER TRADING / Virtual money and simulated fills. Never part of your net worth. | `fxPaperTrading`, `fxPaperTradingNote` |
| 25 | Every price | Simulated (or the price's type) / Not an executable quote / Stale | `fxKindSimulated`, `fxNotExecutable`, `fxStale` |
| 26 | Forecast screen | Requires calibration: not reliable | `fxRequiresCalibration` |
| 27 | Opportunity screen, backtest line | Backtested results on stored bars, net of costs: a study, not a forecast. | `fxBacktestNote` |
| 28 | Copilot entry | Explains prices, forecasts and risk; never trades | `fxCopilotSubtitle` |
| 29 | Calendar | Consensus (not a fact) {value} / DEMO event | `fxConsensus`, `fxDemoEvent` |

### Observations from the engineering side (for you to accept or reject)

1. **No general loss-of-money line on the forex home screen.** Items 8 and 9 state it in the risk calculator only. A retail forex warning usually appears where the section is entered. See question 3.5.
2. **"Not a broker" appears in item 1, but no statement says WealthSphere is not a licensed adviser.** This is the same open point as P12 observation 2.1.
3. **"Guaranteed" appears in denials** (items 5, 8, 20). The answer guard accepts negated uses only.
4. **The ranking shows entry, stop and target levels** (item 6). They are illustrative, but they look like a trade idea. Question 3.2 asks whether that matters.
5. **Paper results are shown as money amounts** in the account currency. Item 13 says they are virtual. Consider adding "past paper results do not predict real results" (question 3.4).
6. **Language:** English only, as for P12 (question 3.9).
7. **The wording is pinned by tests.** Any change is made in the backend constants and `app_en.arb`, and the tests that pin it are updated in the same change.

## 5. Execution-disabled verification (P13-T14.4, QG-20.5)

The build has no live execution capability, and enabling one would need a separate approved phase (CLAUDE.md: "Do not implement automatic trade execution unless a future approved requirement explicitly introduces it").

| Check | How it is enforced | Result (2026-10-14) |
|---|---|---|
| No API route places, modifies or cancels a real order | `test_no_forex_route_places_orders` walks every route of the app with forex on | Pass |
| No forex source outside `paper/` names an order endpoint or broker call | `test_no_forex_source_names_an_order_endpoint_or_call` scans the package | Pass |
| The only configurable provider is the simulated one, so no broker connection exists | `test_the_only_configurable_provider_is_simulated` | Pass |
| The module cannot be switched on outside `local` and `test` | `Settings._forex_only_in_development`; `test_forex_cannot_be_switched_on_outside_development` (each environment) | Pass |
| The Copilot has no write tool for forex; all 11 forex tools are read-only and allow-listed | `ALLOWED_TOOLS` in `app/ai/tools/base.py`, mirrored in `docs/ai-governance.md` and checked by a test; `tests/ai/test_forex_tools.py` | Pass |
| The Copilot refuses trade instructions | `refusal.py`; `tests/ai/test_forex_chat.py`; the `forex_safety` evaluation set, zero tolerance | Pass |
| Paper orders never leave the server | `paper/` fills against stored quotes only; the `X-Trading-Mode: PAPER TRADING` header on every paper response | Pass |

Command: `cd backend && .venv/Scripts/python.exe -m pytest tests/forex/test_hard_rules.py tests/forex/test_paper_api.py tests/forex/test_paper_core.py tests/ai/test_forex_chat.py tests/ai/test_forex_tools.py -q` gave **39 passed**. The same tests run in the required `backend gate` check on every pull request.

## 6. Release decision (P13-T14.5)

**Decision recorded: not released.** The Forex module stays behind `forex_enabled`, which is off by default and refused outside `local` and `test`. No user outside development can reach it.

The module may be offered to users only when **all** of these hold:

1. **DEC-19:** a provider is chosen and section 2 is answered and signed (QG-20.1).
2. **DEC-20:** section 3 is answered and signed for each launch market (QG-20.2).
3. The disclosures in section 4 are approved, with any changes applied and tested (QG-20.3).
4. The core hardening gate (P16-GATE) and the staging smoke tests (P15-T11) pass (DEC-23).
5. The hands-on user acceptance of the forex screens and the manual device pass (QG-19, P13-T13.4) are recorded.
6. The configuration guard in `config.py` is relaxed by an approved change, never by an environment variable alone.

Live execution is not part of this decision. It would need its own approved phase.

## 7. Sign-off

A blank line means "not yet reviewed". The open lines belong to P17-T09.

| Item | Role | Name | Date | Decision |
|---|---|---|---|---|
| Section 2: licence (QG-20.1) | User (DEC-19) | | | |
| Section 3: Kenya (QG-20.2) | Reviewer | | | |
| Section 3: UAE (QG-20.2) | Reviewer | | | |
| Section 4: disclosures (QG-20.3) | User (decision owner) | user (mtisya@gmail.com) | 2026-10-14 | **Approved as drafted** (recorded on the user's answer in the session). The 7 observations are carried as follow-ups. The named reviewer's legal review of the wording is part of P17-T09.3 |
| Section 6: release decision | User | user (mtisya@gmail.com) | 2026-10-14 | **Approved: not released.** Licence and regulatory reviews moved to P17-T09 by plan change |
