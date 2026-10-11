# ADR-0014: Market-data providers and licensing (DEC-04)

Status: Accepted (proposed in P08-T01, 2026-10-12; approved by the user on 2026-10-12 by approving task P08-T01 and the plan to run P08-T01 to P08-T09, which adopts the recommendation below). **Production use of each provider is conditional on the licence checks in section 4.**

## Context
P08 brings prices, FX and research into the platform with provenance, freshness and caching (docs/SOLUTION_INTENT.md section 21: provider abstractions, no hard dependency on one provider). The app shows and stores this data, so a provider's licence must allow in-app display to end users and storage (history, valuation snapshots). The comparison matrix is in `docs/market-data-providers.md`.

What was checked in this session (public pricing and terms pages, fetched 2026-10-12):
- **CoinGecko**: Demo plan (free) lists "Attribution required" and is not offered as a commercial licence; paid plans from Basic (USD 35 a month) are commercial and require showing "Data provided by CoinGecko" with a link; reselling or redistributing the API is not allowed. The pricing page states no storage restriction; the API terms page was not read.
- **Twelve Data**: every Individual plan, including the free Basic, is described as "personal, internal, and non-commercial". The page does not grant in-app display or redistribution rights for a commercial product.
- **ECB euro reference rates**: published "for information purposes only", and use "for transaction purposes is strongly discouraged". The reuse and copyright terms are on a separate page that was not read.

What was **not** verified: any equities/ETF provider's commercial display and storage terms, the ECB copyright page, the CoinGecko API terms, bonds, macro and research providers. No contract or key has been signed or created.

## Decision
1. **Provider abstraction first (P08-T02).** Every consumer uses the interface, never a vendor. Adapters are replaceable and a provider can be swapped without a schema change. Each stored price carries provider, as-of and ingestion timestamps (P08-T05).
2. **Selected for implementation (P08-T03), each behind the interface:**
   - **FX, reporting-currency conversion:** ECB euro reference rates (daily, EUR base, other pairs crossed through EUR), labelled "indicative, not for transactions". Fallback: a commercial FX API chosen under DEC-25 (P11).
   - **Crypto:** CoinGecko. Development on the Demo plan only against recorded fixtures; production needs a paid commercial plan and the attribution line.
   - **Equities and ETFs:** Twelve Data adapter, built against its documented API and recorded fixtures, because it is a common, simple shape that the abstraction can also satisfy with other vendors. **It cannot go to production on an Individual plan.** A commercial or display licence (or another vendor with one) is a blocking condition.
   - **Out of scope for P08:** bonds, macro and research providers. The AI opportunities research stays DEMO until P12 selects its evidence sources; this is stated in the app.
3. **No provider is used in production until its licence for in-app display and storage is confirmed in writing** (section 4). Until then the app uses the deterministic fake provider and manual valuations (P05), and shows data as of its source time, never as live.
4. **Keys** are environment or secret-manager values only, never in source, logs or responses (P08-T03, P08-T09).
5. **Prices are never invented.** If a provider is down or a licence is missing, values are stale-flagged or fall back to the user's manual valuation (P08-T06), never filled from a model.

## Consequences
- P08 can be built and fully tested offline with fakes and recorded fixtures; nothing in it depends on a signed contract.
- The acceptance criterion "licence permits the intended in-app display and storage" is **not yet met for any provider**. It becomes a production-readiness item (carried to P08-GATE and P12), not something this ADR claims to have satisfied.
- A user decision is still needed before launch: which equities vendor and plan, and the monthly budget (CoinGecko Basic is USD 35 a month at the time of writing; equities licences are materially more).
- ECB rates mean FX is daily, not live; acceptable for reporting-currency conversion (ADR-0010), not for trading.
