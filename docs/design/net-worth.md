# Net worth and liabilities

Status: Implemented in P06-T07.

- **Table:** `liabilities` (migration 0009).
- **Calculation:** pure functions in `backend/app/modules/networth/networth.py`, used by `service.py`.
- **API:** `/api/v1/liabilities` and `GET /api/v1/net-worth`.

**Net worth = total assets - total liabilities**, in one currency, with every FX rate used.

## 1. Liabilities

A liability is something the user owes. The user enters it with the date its balance applied:

| Field | Meaning |
|---|---|
| name | unique per user |
| liability_type | mortgage, personal_loan, car_loan, student_loan, business_loan, credit_card, other |
| balance | the outstanding amount (Money: 0 to 10,000,000,000, at most the currency's minor units) |
| balance_as_of | when the balance applied (today or earlier) |
| interest_rate_percent | optional, 0 to 100, for reference (not used in net worth) |
| asset_id | optional: the asset securing it (for example a mortgaged property); must be an asset the user can see |

**Changes:**
- Balances change by `PATCH` (for example the latest statement balance). A paid-off liability can be deleted or set to 0.
- Create, update and delete write audit events (type and changed fields, never amounts).
- A user has at most 100 liabilities.

**Balance history** is not kept yet. The historical net-worth series would need it, so it is future work.

## 2. Assets

Total assets are the `total_value` of all the user's **active** portfolios, consolidated in the net-worth currency (docs/design/portfolio-summary.md, section 7). That covers:
- investments, property and businesses, valued from their latest valuations;
- cash balances.

Archived portfolios are left out. Unpriced positions and amounts in currencies without a rate are not counted; the result says so.

`assets_by_class` is the allocation of those assets by asset class (docs/design/allocation.md). Shares are given to 2 decimals and add up to exactly 100, or are null when a negative cash balance makes them meaningless.

## 3. Conversion and FX provenance

**Liabilities** are converted to the net-worth currency at the latest rate (P05-T06 "latest" rule). A liability in a currency without a rate is listed with `value: null`, left out of the total, and named in `freshness.unconverted_currencies`.

**`fx_rates`** lists every conversion into the net-worth currency: each portfolio base currency and each liability currency. For each it gives the rate, its timestamp, provider, whether it is stale (older than a day) and whether it was inverted from the opposite pair. Conversions inside a portfolio (positions into its base currency) are reflected in `freshness.data_as_of` and `freshness.stale_fx`.

**`freshness`** gives:
- `computed_at`;
- `data_as_of`: the oldest valuation or rate used;
- `complete`: false when assets are unpriced or anything is unconverted;
- `unpriced_assets`;
- `unconverted_currencies` and `stale_fx`;
- `oldest_liability_balance`: the oldest user-entered balance date.

## 4. Rounding (ADR-0006)

- Each liability is converted at full precision and rounded half-up to the currency's minor units.
- Total liabilities and the totals by type are sums of those rounded values.
- Assets are rounded once.
- `net_worth` = rounded assets - rounded liabilities, so the three figures always reconcile exactly as shown.
- Net worth can be negative; it is shown as it is.

## 5. API

| Route | Purpose |
|---|---|
| `POST /api/v1/liabilities` | create (201) |
| `GET /api/v1/liabilities` | the user's liabilities, by name |
| `GET, PATCH, DELETE /api/v1/liabilities/{liability_id}` | one liability; 404 for another user's, exactly like a missing one |
| `GET /api/v1/net-worth?currency=XXX` | net worth (default currency: the user's base currency) |

The response's `assets`, `liabilities`, `net_worth` and `as_of` are the mobile `NetWorthSummary`.
