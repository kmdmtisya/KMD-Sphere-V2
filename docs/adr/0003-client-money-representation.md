# ADR-0003: Client money representation

Status: Accepted (user approval, 2026-10-09)

## Context
CLAUDE.md forbids binary floating point as the authoritative representation of money and states that the backend is authoritative for financial calculations.

## Decision
In Flutter, money is `Money(Decimal amount, String currencyCode)`. Amounts travel as **strings** in JSON and are parsed with `Decimal`. `double` appears only inside chart widgets, to plot coordinates. The client formats and rounds for display only (ADR-0006) and never derives totals, returns, allocations or projections.

## Consequences
- No precision loss across the API.
- A guard test forbids `double` money in domain and formatting code.
- Chart code converts to `double` at its own boundary.
