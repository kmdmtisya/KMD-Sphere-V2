# ADR-0009: Forex Trading Intelligence module (decision support and paper trading only)

Status: Accepted (user approval, 2026-10-09; phase P13 approved)

## Context
A request (2026-10-09) adds a Forex Market Intelligence, Prediction and Trade Opportunity Analysis module: live quotes, indicators, probabilistic forecasts, an opportunity ranking dashboard, risk management, backtesting, paper trading and an AI Forex Copilot. SOLUTION_INTENT section 30 lists "not a bank, broker, exchange, high-frequency trading system or autonomous robo-adviser" as initial non-goals, and CLAUDE.md forbids automatic trade execution without an approved requirement. Forex is leveraged, short-horizon and heavily regulated, so the module carries risks the wealth-tracking core does not (user harm from leverage, regulatory classification, data licensing, false confidence from overfitted models).

## Decision
1. Add the module as workstream **P13 (FX-01…FX-14)** with eight additional quality gates **QG-13…QG-20 (QG-FX-01…08)**, placed after the AI phases (P12) and before cloud infrastructure (P14). It needs P08-P12 only; enabling its feature flag in production additionally waits for core hardening (P15) and the module's staging smoke tests (P14-T11).
2. The module is **decision support and paper trading only**. The build contains no order-placement path and no trading credentials. Live execution needs a separate, explicitly approved phase with regulatory review and dedicated trading risk controls.
3. Amend SOLUTION_INTENT: section 30 is clarified (the module does not make WealthSphere a broker or robo-adviser) and a new section 34 defines the extension and its boundaries.
4. Keep the approved five-tab navigation (ADR-0002): Forex is reached from More and a Home shortcut.
5. Reuse, not duplicate: the P08 provider abstraction, the P10 AI tool layer and output guard, the P04 authorisation harness, ADR-0003/0006 money rules and the design system.
6. Probabilities are labelled "Requires calibration" until calibration passes; every model is reported against random-walk and no-change baselines, including when the baseline wins.
7. Paper-trading data is stored and queried separately and never enters net worth, holdings or real analytics.

## Consequences
- The plan grows to 16 phases, 172 tasks and 20 gates; the core product path (P00-P12 and P14-P16) is unaffected and can ship without P13 (DEC-23 proposes an after-v1, feature-flagged release).
- Market-data licensing (DEC-19) and regulatory classification (DEC-20) are release blockers, and both are CRITICAL criteria (QG-20.1, QG-20.2).
- Time-series storage, ML libraries and contract-spec sourcing are decided in DEC-21, DEC-22 and DEC-24 rather than assumed.
- If the user declines the extension, P13 and QG-13…QG-20 are removed by a recorded plan change; nothing else depends on them.

Design: [docs/design/forex-technical-design.md](../design/forex-technical-design.md).
