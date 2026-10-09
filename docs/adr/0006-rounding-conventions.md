# ADR-0006: Rounding conventions

Status: Proposed (DEC-06; the user delegated the choice and the recommendation was adopted)

## Context
Money must be exact and reproducible across Flutter, Python and PostgreSQL. Python's `Decimal` defaults to half-even, while PostgreSQL `round(numeric)`, spreadsheets and bank statements round ties away from zero.

## Decision
1. **Rounding mode is ROUND_HALF_UP** (ties away from zero) everywhere: Python `Decimal.quantize(..., ROUND_HALF_UP)`, an explicit half-up helper for Dart `Decimal`, and SQL `round()`.
2. **Full precision internally.** Intermediate results are never rounded; use a 28-digit decimal context in Python. Rates, percentages and FX are stored unrounded (`NUMERIC` with at least 12 fractional digits for rates).
3. **Round only at boundaries:**
   - display;
   - a posted ledger amount, to the currency's ISO 4217 minor units (USD, AED and KES have 2; JPY has 0; KWD and BHD have 3);
   - published API figures, at the documented precision of each field.

   A rounded value is never fed back into a later calculation.
4. **Allocation** (splitting an amount into parts that must sum to the total) uses the largest-remainder method.
5. Percent displays use 2 decimals. Quantities keep their natural precision (crypto up to 8).
6. Every rounding point has a unit test with tie cases (x.005, x.5, negatives).

## Consequences
The database, API and UI agree on ties. The small statistical bias of half-up is avoided on large sums because sums use unrounded values. Deviations require a new ADR.
