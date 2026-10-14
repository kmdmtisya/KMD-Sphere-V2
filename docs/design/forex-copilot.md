# AI Forex Copilot, as built (P13-T10)

This document covers the forex tools the AI orchestrator can call and the server-side checks on forex answers. The design is in [forex-technical-design.md](forex-technical-design.md) section 12, the tool contract and allow-list are in [ai-governance.md](../ai-governance.md) section 1, and the evaluation is in [ai-evaluation.md](../ai-evaluation.md) under "P13".

The approved pattern is unchanged:

`User -> AI Orchestrator -> Authorization -> Allow-Listed Tool -> Deterministic result -> LLM -> Validated Response`

**Rules for the Copilot:**
- **Read-only tools.** No tool places, changes or closes a trade, real or paper. For a trade, the user is pointed to their paper account.
- **Tools only when forex is on.** The 11 forex tools are registered only when `forex_enabled` is set (DEC-23). With it off, the model sees no forex tool and no forex prompt.
- **Figures from tools.** Every forex figure in an answer must come from a forex tool of the same turn.
- **The server qualifies and cites.** The server adds the qualifications and the sources itself; neither depends on the model.

## 1. Tools

The tools are in `backend/app/ai/tools/forex.py`. Each one reads through the same code as the forex API.

| Tool | Reads | Notes |
|---|---|---|
| `get_forex_quote` | the quote board | A stale or missing price is `complete: false` and is never filled in |
| `get_candles` | closed bars, up to 100 | Mid prices, with data types |
| `get_indicators` | the indicator library on the live 200-bar window | The latest values with the bar's close time |
| `get_market_structure` | levels, breakouts and patterns | As found by the published rules |
| `get_forecast` | the latest forecast and its model version | Includes the calibration label, edge and generated time |
| `explain_forecast_change` | the two latest forecasts | What changed, and whether the model version changed |
| `get_opportunities` | the Opportunity Ranking | Research candidates, labelled as not recommendations |
| `get_economic_events` | the calendar and its risk windows | Includes the DEMO flag |
| `calculate_trade_risk` | `risk.service.calculate_trade`, which the API also uses | Same figures as the API; nothing is placed |
| `get_backtest_summary` | stored backtest reports | Out-of-sample results and the leakage audit status |
| `get_paper_performance` | the caller's own paper accounts only | Another user's account id answers `not_found` |

The calculator moved from the risk API into `risk/service.py`, and its schemas into `risk/schemas.py`, so the API and the tool share one implementation. The OpenAPI document did not change.

**Common safeguards.** Every call goes through the registry's single door: the user context is taken from the request, arguments are validated with unknown fields refused, a call budget applies, and each call is audited. The model never supplies who is asking.

## 2. What the server adds to a forex answer

**Sources.** The structured answer gains a `sources` list, built from the tool results. Each source carries:
- the tool;
- its time (`as_of`);
- its data types;
- for a forecast, the model and version, the calibration status and the generated time.

The rendered text lists the sources at the end. The model may not write `sources` (or `caveats`): a reply that does is refused.

**Caveats,** added from the tool results whatever the model wrote:

| When | Caveat |
|---|---|
| Stale or incomplete data | The existing stale or incomplete notice |
| A failed tool | The existing "could not be retrieved" notice |
| Simulated data | Prices come from the simulated development feed, not a live market |
| A forecast that requires calibration | Its probability is not reliable |
| Research candidates | Not recommendations, not probabilities of profit |
| Backtested results | A study, not a forecast |
| Paper results | Virtual money, a separate series; the Copilot cannot trade |
| DEMO calendar events | Not a real calendar |
| Any forecast | The existing forecast notice |

## 3. Output and request checks

**Personal advice** (`advice_problems`). When a forex tool ran, an answer that tells the user to trade is refused with `personal_advice` and sent back once for correction, with fixed wording. Examples: "you should buy", "I recommend selling", "go long now", "open a short now". A negated sentence such as "I cannot tell you to buy" is allowed.

**Guarantees and certainty.** The existing guarantee and certainty checks apply to forex answers as to all others. "Forecast" here also covers `get_forecast` and `explain_forecast_change`, so an unhedged "will reach" is refused.

**Trade requests** are declined before any model runs. The `trade_execution` refusal now also catches:
- "buy 1 lot";
- "open a short for me";
- "go long for me";
- "close my trade right now".

Its message names the paper account. Questions about trading, such as "Should I go long EUR/USD?", are still answered.

**The system prompt** gains forex rules, but only when forex tools are offered:
- quote times;
- the forecast's calibration label and model version;
- research candidates are not recommendations;
- never instruct a trade;
- say when data is simulated.

## 4. Tests

| Test | What it covers |
|---|---|
| `tests/ai/test_forex_tools.py` | Every tool on the real database, through the registry. Fresh, stale and missing quotes; candles, indicators, structure and the ranking on a stored trend; forecasts with model version and calibration; the calendar with the DEMO flag; the risk tool giving the API's figure; backtests; paper performance for the caller only (another user's account is `not_found`); the audit event; smuggled arguments refused |
| `tests/ai/test_forex_chat.py` | The chat endpoint with a scripted model: sources and the simulated caveat on a quote answer; a trade instruction sent back and a clean answer accepted; a trade request declined naming the paper account; no forex prompt or tools with the flag off |
| `tests/ai_eval/test_forex_datasets.py` | `forex_figures`, `forex_safety` and `forex_stale`, all at zero tolerance, plus regression meta-tests showing each fails without its defence |
| `tests/forex/test_analysis_rules.py` | The forex tool module writes nothing, and the tools exist only with the flag on. This replaces the T03 placeholder that allowed no forex tool "yet" |

## 5. Limits

- **The advice check is a wording rule.** A paraphrase it does not know can pass it. The other layers are the system prompt, the absence of any trading tool, and the refusal rules.
- **No live-model run yet.** Routing questions to the forex tools has not been measured with a real provider; it is part of the pre-release live run, which waits for ADR-0017's provider terms. The routing dataset is built with forex off, so it has no forex cases yet.
- **No real market data.** All data is simulated or DEMO until DEC-19 (data licence) and DEC-20 (regulatory review) allow real data. Every answer says so.
