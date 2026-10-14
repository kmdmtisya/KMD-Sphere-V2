# QG-20 (QG-FX-08) Forex release and regulatory readiness: 2026-10-14

**Gate status: blocked.** Two of five criteria are verified. The three others wait for decisions the user has deferred: DEC-19 (market-data licence) and DEC-20 (regulatory review for Kenya and the UAE). Nothing is marked reviewed that has not been. The review pack is [docs/forex-release-readiness.md](../../docs/forex-release-readiness.md).

| Criterion | Status | Evidence or what is missing |
|---|---|---|
| QG-20.1 Market-data licensing is reviewed (CRITICAL) | **Open** | No provider has been chosen (DEC-19 is fixture-only). The licence checklist (pack, section 2) covers display, storage, derived data, AI use, redistribution, fan-out caching, attribution and price type. It is unanswered. Only the simulated provider can be configured (`test_the_only_configurable_provider_is_simulated`) |
| QG-20.2 Launch-market financial-advice and trading regulations are reviewed (CRITICAL) | **Open** | The questions for Kenya and the UAE (onshore, DIFC, ADGM) are in the pack, section 3. They are unanswered, and no regulator's requirement has been stated or assumed |
| QG-20.3 Risk disclosures are reviewed | **Open** | 29 statements are listed in the pack, section 4, with their sources and 7 engineering observations. The reviewer has not decided on them yet |
| QG-20.4 Paper trading remains separate from real holdings (CRITICAL) | **Verified** | `test_paper_money_never_reaches_net_worth` and `test_no_real_money_module_reads_paper_tables` (`tests/forex/test_paper_api.py`). The paper tables are in the integrity suite's IDOR sweep and snapshot. Every paper response carries the PAPER TRADING notice and the `X-Trading-Mode` header. Design: [forex-paper-trading.md](../../docs/design/forex-paper-trading.md) |
| QG-20.5 No live execution is enabled without explicit approval (CRITICAL) | **Verified** | `tests/forex/test_hard_rules.py`: no route places orders; no forex source outside `paper/` names an order endpoint or call; only the simulated provider can be configured; the module is off by default and refused outside `local` and `test`. The 11 Copilot forex tools are read-only and allow-listed. The Copilot refuses trade instructions (`tests/ai/test_forex_chat.py`, the `forex_safety` set with zero tolerance). Pack, section 5 |

**Release decision (pack, section 6):** not released. The module stays off outside development until QG-20.1 to QG-20.3 are signed, P16-GATE and the P15-T11 staging smoke tests pass, and the hands-on acceptance and device pass are recorded.

**Command:** `cd backend && .venv/Scripts/python.exe -m pytest tests/forex/test_hard_rules.py tests/forex/test_paper_api.py tests/forex/test_paper_core.py tests/ai/test_forex_chat.py tests/ai/test_forex_tools.py -q` gave 39 passed (2026-10-14). The same tests run in the required `backend gate` check.
