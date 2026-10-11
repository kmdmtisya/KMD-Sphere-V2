# Market-data providers: requirements and comparison (P08-T01)

Decision record: [ADR-0014](adr/0014-market-data-providers.md). Facts below come from public pricing and terms pages fetched on 2026-10-12 unless marked **Not verified**. Prices change; check before contracting.

## 1. Requirements

| # | Requirement | Why |
|---|---|---|
| R1 | Licence allows showing the data to end users in the mobile app | The product displays prices and valuations |
| R2 | Licence allows storing it (history, valuation snapshots, caching) | Valuations and performance use stored history |
| R3 | Every value has provider, as-of and ingestion time | Provenance and freshness (CLAUDE.md financial data rules) |
| R4 | Rate limits and quota fit a scheduled worker (not per-user calls) | Ingestion runs on a schedule and is cached |
| R5 | Terms allow caching and attribution as required | Redis and database caching |
| R6 | Swappable without schema changes | No hard dependency on one provider |
| R7 | Cost fits a small-team budget at launch | Budget is a user decision (DEC-04) |

## 2. Candidates

| Asset class | Candidate | Plan and cost seen | R1 display | R2 storage | Verdict |
|---|---|---|---|---|---|
| FX | ECB euro reference rates | Free; daily, EUR base | "For information purposes only"; transaction use discouraged. Reuse terms on a separate page: **Not verified** | **Not verified** | Selected for reporting conversion (indicative, labelled). Confirm copyright page before launch |
| FX | Commercial FX API (Open Exchange Rates, ExchangeRate-API, Currencylayer, OANDA) | **Not verified** | **Not verified** | **Not verified** | Fallback; chosen under DEC-25 in P11 |
| Crypto | CoinGecko Demo | Free; 10k credits a month, 100 calls a minute | "Attribution required"; not offered as a commercial licence | Page states no restriction; API terms **not read** | Development and fixtures only |
| Crypto | CoinGecko Basic | USD 35 a month (29 yearly-billed); 100k credits, 300 calls a minute | Commercial; must show "Data provided by CoinGecko" with a link | As above | Selected for production; no resale or redistribution of the API |
| Equities, ETFs | Twelve Data Individual (Basic free, Grow USD 79, Pro 229, Ultra 999 a month) | Credit limits stated; page figures inconsistent | Plans are "personal, internal, and non-commercial"; no in-app display grant | Not stated | Adapter built for development; **blocked for production** on these plans |
| Equities, ETFs | Other vendors (Polygon, Finnhub, Tiingo, others) | **Not verified** | **Not verified** | **Not verified** | Candidates if Twelve Data's commercial terms do not fit; evaluate under DEC-04 |
| Not allowed | Unofficial scrapers or undocumented endpoints | n/a | Violates terms | Violates terms | Excluded |
| Bonds, macro, research | FRED, SEC EDGAR, others | **Not verified** | **Not verified** | **Not verified** | Out of scope for P08; DEMO until P12 |

## 3. Selected for implementation

| Asset class | Adapter | Production condition |
|---|---|---|
| FX | ECB daily reference rates | ECB copyright page read; shown as indicative |
| Crypto | CoinGecko | Paid commercial plan; attribution line |
| Equities, ETFs | Twelve Data | Commercial or display licence, or switch vendor |

## 4. Open items before any production use

1. A written licence statement per provider covering in-app display and storage (R1, R2).
2. User decision on the equities vendor, plan and monthly budget.
3. ECB copyright page and CoinGecko API terms read and recorded here.
4. Attribution text added to the app where required (CoinGecko).
