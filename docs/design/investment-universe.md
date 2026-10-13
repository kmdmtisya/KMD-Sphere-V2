# Investment universe and eligibility (P12-T02)

Status: implemented in P12-T02.
- **Code:** `backend/app/modules/universe/`:
  - `models.py`: the `universe_instruments` table (migration 0017);
  - `ingestion.py`: sources and loading;
  - `eligibility.py`: the rules; pure;
  - `service.py`, `schemas.py` and `api.py`.
- **Job:** `ingest_universe`, daily at 02:45 UTC.
- **Product intent:** [SOLUTION_INTENT.md](../SOLUTION_INTENT.md) sections 6 and 17.
- **Decisions:** the P12 advance approval in EXECUTION_LOG.md, 2026-10-13.

## 1. What it is

The instruments that opportunity analysis (P12-T03 onwards) may consider. Each one is a **public catalogue asset**: no owner, referenced by source and symbol, so it can be priced, held and researched like any other asset. It also gets one `universe_instruments` row with what eligibility needs.

| Column | Meaning |
|---|---|
| `source` | where the list came from (`demo` today) |
| `is_demo`, `licence_status` | `demo` (synthetic), `unconfirmed` (real data, licence not confirmed) or `licensed` |
| `risk_level` | the source's classification, 1 (lowest) to 5 |
| `liquidity` | from the asset class ([portfolio-doctor.md](portfolio-doctor.md) section 3, `app/modules/assets/liquidity.py`) |
| `jurisdictions` | ISO countries where the source says it is offered |
| `minimum_investment` | in the asset's currency, when stated |
| `data_as_of`, `is_active` | the list's time; inactive instruments stay (they may be held or priced) but are out of the universe |

The universe is reference data: no row belongs to a user.

## 2. Sources and ingestion

**DEMO source.** Only the synthetic DEMO universe exists for now. No licensed universe has been approved; see ADR-0014 and DEC-04. It is `demo_universe.json`:
- 15 fictional instruments, each named "... (DEMO)" with a `DEMO-` symbol;
- they cover Kenya, the UAE and global listings across stocks, a REIT, bonds, money market funds, a fixed deposit, property, ETFs and crypto;
- risk levels, jurisdictions and minimums are illustrative;
- the listed ones are priced only by the fake market-data provider.

**Ingestion** (`ingest(session, source)`):
- **Idempotent:** an instrument is one asset per (source, symbol), created once and updated in place. A second run reports every instrument as unchanged.
- **Deactivation, never deletion:** an instrument the source no longer lists is deactivated, and it comes back if listed again.
- **Skipped entries:** an entry with an unknown asset class or risk level, or whose currency changed, is skipped and reported.
- **Metadata:** an entry's metadata is stored only where the asset class defines the field (sector for stocks and REITs; expense ratio for ETFs and mutual funds, P12-T03). Values are validated like any other metadata. Holding-specific fields, such as a deposit's maturity date, are not required for a listing.

**Fictional symbols never reach a real provider.** The daily job loads the DEMO universe only when `MARKET_DATA_MODE=fake`. With real market data it deactivates any DEMO instruments instead, which also takes them out of price ingestion.

## 3. Eligibility

`GET /api/v1/universe` (optional `asset_class`, `eligible_only`) returns every active instrument with the outcome of each rule for the signed-in user. The `investor` block shows the facts that were used.

An instrument is **eligible only when every rule passes**. Each rule gives its reason, so an exclusion is never silent.

| Rule | Passes when |
|---|---|
| `jurisdiction` | the user's country of residence (`residence_country`, set with `PATCH /api/v1/me/preferences`) is a launch jurisdiction (**Kenya, UAE**), the source offers the instrument there, and the class is not excluded there (no class is excluded today) |
| `risk` | the instrument's risk level is at most the ceiling for the latest risk profile's tolerance: conservative 2, balanced 3, growth 4, aggressive 5 |
| `liquidity` | immediate and market liquidity always; money locked until maturity (fixed deposits, SACCO, pension) needs a stated horizon of 1 year or more; illiquid or unknown liquidity needs 5 years or more |
| `active` | the instrument is in the universe |

**Missing facts:**
- With no country of residence, or no risk profile, nothing is eligible, and the reasons say so.
- With no stated horizon, nothing locked or illiquid is eligible.

**Jurisdiction rules are not legally reviewed.** Every jurisdiction outcome carries `legally_reviewed: false`, and the response has a `jurisdiction_notice`, until the disclosure and compliance review (P12-T10, DEC-10).

Eligibility is a filter for analysis, not a recommendation. The response says so in its `notice`.

## 4. Tests

- `tests/universe/test_eligibility.py`: every rule at its boundaries, all-rules-pass, fixed order, determinism.
- `tests/universe/test_universe_api.py`:
  - ingestion: idempotent, deactivation, one asset per symbol, skipped entries;
  - the API for an investor with no facts, a balanced Kenyan investor and a growth UAE investor;
  - residence validation, authentication and filter validation;
  - the job in both market-data modes, and its schedule.
