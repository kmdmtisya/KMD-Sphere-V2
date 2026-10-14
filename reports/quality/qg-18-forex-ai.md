# QG-18 (QG-FX-06): AI Trading Intelligence — P13-T12, 2026-10-14

The method is in [docs/design/forex-copilot.md](../../docs/design/forex-copilot.md) and [docs/ai-evaluation.md](../../docs/ai-evaluation.md) under "P13". The evaluation datasets run in CI with no model and no database. The regression meta-tests show that each dataset fails when its defence is removed.

| Criterion | Evidence | Result |
|---|---|---|
| 18.1 Market facts are source-backed with timestamps (CRITICAL) | `forex_figures` 40/40 at zero tolerance: every price, indicator, forecast and risk figure must come from a forex tool of the turn, and invented ones are refused. The server-built `sources` give each tool's time and data types (`forex_stale`; `tests/ai/test_forex_chat.py::test_a_quote_answer_carries_sources_and_the_simulated_caveat`). Every tool result carries `as_of` (`tests/ai/test_forex_tools.py`). The model may not write `sources` | Pass |
| 18.2 Prediction timestamps and model versions are included | The forecast source carries the model name and version, calibration status and generated time (`forex_stale`; `test_the_rendered_answer_lists_the_sources_with_time_and_model`). The forecast tool returns them (`test_forecasts_carry_the_model_version_and_calibration`). The app shows them as Source lines (`forex_data_test.dart`) | Pass |
| 18.3 No guaranteed-profit language passes the output guard (CRITICAL) | `forex_safety` 70/70 at zero tolerance: guarantee, certainty and trade-instruction wording is refused (`personal_advice`), and honest qualifications are kept. Trade requests are declined before any model runs, naming the paper account. The zero-tolerance scan covers every accepted forex output. `test_without_the_advice_check_trade_instructions_get_through` shows the dataset fails without the check | Pass |
| 18.4 Structured AI output is validated | The structured answer schema; the model cannot write `caveats` or `sources` (`not_structured`); a rejected answer is sent back once with fixed corrections and a clean one accepted (`test_a_trade_instruction_is_sent_back_and_a_clean_answer_accepted`); tool arguments refuse unknown fields (`smuggled` case in `test_forex_tools.py`) | Pass |
| 18.5 Stale-data conditions are handled | `forex_stale` 26/26: stale, incomplete and failed tools are qualified by the server, along with simulated, uncalibrated, research, backtest, paper and DEMO data. Stale quotes are `complete: false` (`test_quotes_fresh_stale_and_missing`) | Pass |

**Limits:**
- **Not measured yet:** routing questions to the forex tools with a real model. It is measured in the pre-release live run, which waits for the provider terms review (ADR-0017).
- **A wording rule:** the advice check matches phrasing. The other layers are the prompt, the absence of any trading tool, and the refusal rules.

Run: `cd backend && uv run pytest tests/ai_eval tests/ai/test_forex_tools.py tests/ai/test_forex_chat.py -q` (part of the 753-test run of 2026-10-14; all passed).
