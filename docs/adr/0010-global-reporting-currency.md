# ADR-0010: Global reporting currency and FX management (FXCUR)

Status: Accepted (user approval, 2026-10-10; phase P11 approved)

## Context
A request (2026-10-10) adds real-time multi-currency conversion: users switch every financial figure between currencies (for example AED 500,000 shown in USD, KES, EUR or GBP) using current provider rates, with historical rates for past figures and AI tools for currency questions. SOLUTION_INTENT section 8 already says each investment keeps its native currency and the user selects a reporting currency, and the plan already builds the foundations: the fx_rates table and FX service with base-currency conversion (P05-T01, P05-T06) and FX ingestion with history (P08-T05). What is missing is the reporting-currency layer across the whole app.

## Decision
1. Add workstream **P11 (FXCUR-01…FXCUR-12)** with gates **QG-21…QG-25 (QG-FXCUR-01…05)**, placed after P10 and before P12. That is the first point where everything it builds on exists (P05 FX service, P06 analytics, P08 FX ingestion and provider abstraction, P09 live screens, P10 AI tool framework), and the latest point before AI Intelligence (P12), Forex (P13) and hardening (P15) need it. Later phases are renumbered (P11…P15 become P12…P16).
2. The reporting currency is a **global user setting** (server-side, synced across devices), reachable from Settings and from Total Wealth on Home; not a calculator feature.
3. Conversion is **presentation only** and done by the backend in Decimal with one **rate snapshot** per view, report or AI answer. Originals, transaction rates, portfolio base currencies, goal target currencies and forecast assumptions are never changed.
4. FXCUR **extends** P05-T06, P08-T02/T05, P04-T05 and P07-T08 rather than creating parallel modules.
5. FXCUR gates are **core** release gates: QG-12.1 (release readiness) requires QG-21…QG-25, while the Forex gates QG-13…QG-20 stay optional.

## Consequences
- The plan grows to 17 phases, 185 tasks and 25 gates. Hardening (P15) now also depends on P11.
- Provider choice and licence (DEC-25), refresh cadence (DEC-26), pivot currency (DEC-27), audit retention (DEC-28) and FX scenarios (DEC-29) are decided at P11-T01.
- Screens built in P09 are retrofitted once, centrally (repositories and CurrencyAmount), rather than per screen.

Design: [docs/design/multi-currency-design.md](../design/multi-currency-design.md).
