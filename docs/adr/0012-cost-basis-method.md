# ADR-0012: Cost-basis method for holdings

Status: Proposed (P05-T05, 2026-10-10; for user approval at P05-GATE)

## Context
Holdings, realised profit and unrealised profit all depend on how the cost of units sold is measured. The ledger (P05-T04) is append-only, multi-currency, and corrected by reversal entries. Common methods: weighted average cost (WAC), first-in-first-out (FIFO), specific identification. Tax rules differ by country; WealthSphere is a tracking and planning tool, not a tax calculator (a tax-lot method can be added later without changing the ledger).

## Decision
1. **Weighted average cost**, per asset per portfolio, in the **portfolio's base currency**.
   - BUY: quantity += q; cost += (gross + fees + taxes) x fx.
   - SELL: average = cost / quantity; cost removed = average x q; proceeds = (gross - fees - taxes) x fx; realised += proceeds - cost removed; cost -= cost removed; quantity -= q. When quantity reaches zero, cost is exactly zero.
   - TRANSFER_IN: quantity += q; cost += (gross + fees + taxes) x fx (the value brought in becomes its cost).
   - TRANSFER_OUT: like a SELL for quantity and cost, but no profit is realised (the units moved elsewhere).
   - DIVIDEND, COUPON, RENT, DISTRIBUTION, and INTEREST with an asset: gross is income for that asset, and their fees and taxes (such as withholding tax) are expenses (x fx). FEE and TAX with an asset: expenses for that asset. None of these change cost basis.
   - VALUATION_ADJUSTMENT does not change quantity or cost; it is a valuation input (P05-T07, P05-T08).
2. **FX:** each posting is converted with its own stored rate (`fx_rate_to_portfolio_currency`, the rate on the day). Cost basis is therefore historical cost in the portfolio currency; later rate moves show up in unrealised profit, not in cost.
3. **Reversals:** an entry that has been reversed, and its reversal, are both left out of the calculation, as if the entry had never been posted. (Applying the reversal as a negative entry at a later point would give a different average.)
4. **Order:** entries are applied by trade date, then entry time, then id.
5. **Splits:** a forward split is posted as TRANSFER_IN of the new units with a gross value of 0 (quantity rises, cost unchanged, so the average falls). Reverse splits and other corporate actions need a dedicated entry type (future work).
6. **Precision:** full precision inside the calculation (a 50-digit decimal context); stored holdings are rounded half-up to 8 decimals; API figures to the currency's minor units (ADR-0006).
7. **The ledger is the source of truth.** The `holdings` table is a cache rebuilt from the ledger in the same database transaction as every posting.

## Consequences
- Simple, explainable figures ("your average cost is ..."), stable under partial sells.
- Results differ from FIFO for realised profit; a FIFO or tax-lot view can be added later from the same ledger.
- Reverse splits cannot be expressed yet.
