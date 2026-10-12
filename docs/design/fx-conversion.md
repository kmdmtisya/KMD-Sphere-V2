# Reporting conversion engine and snapshots (P11-T04)

Extends the P05-T06 FX service ([financial-methods.md](../financial-methods.md)) and the P11-T03 rates ([fx-refresh.md](fx-refresh.md)). Decisions: ADR-0006 (rounding), DEC-27 (USD pivot, per-currency precision).

## Rates

- **Direction.** A stored rate means 1 base = rate quote. A lookup uses the pair as stored, or exactly the opposite pair inverted (1 / rate at 50 significant digits); any other match is refused.
- **Cross rates.** When neither direction is stored, the rate goes through the pivot: 1 A = (A→pivot) × (pivot→B). It is as old as its older leg, stale when either leg is, and carries the path, e.g. AED→USD→KES. The existing FX service (`FxService.quote`) now does this for every consumer; **ledger postings do not** (`rate_for_posting` keeps the pair's own rate, so a transaction rate is never derived through a third currency).

## Snapshots

A snapshot is the latest stored rate of every active currency against the pivot, frozen (`fx_snapshots`, migration 0016). Inside a snapshot: pivot→X = r(X); X→pivot = 1/r(X); A→B = r(B)/r(A) with path A→pivot→B. Every figure of one view, report or AI answer uses one snapshot, so a total equals the sum of its converted parts.

- **Content-addressed:** the id is derived from the rates, so the same rates are one snapshot no matter how many requests ask; a report keeps its id and can be re-read with exactly its rates.
- **Immutable:** database triggers refuse UPDATE and DELETE.
- **Status** is not frozen: it is computed per read from the clock (the worst status of the legs used).

## Conversion

`converted = round_half_up(amount × rate, decimal places of the target)`, computed at 50 significant digits and rounded once at the end. Decimal places come from the `currencies` table (JPY 0, most 2). Inputs are never modified; conversions are read-only views.

## API

| Route | Purpose |
|---|---|
| `GET /api/v1/currencies` | Supported currencies: code, name, symbol, decimal places |
| `GET /api/v1/fx/rates?base=&quotes=&snapshot_id=` | Rates from one snapshot (id returned), with paths and status; pairs without a rate listed as unavailable |
| `GET /api/v1/fx/rates/{base}/{quote}` | One rate, direct or derived; 404 `fx-rate-unavailable` when there is none |
| `POST /api/v1/fx/convert` | `{amount: Money, to, snapshot_id?}` → source, converted, rate, path, snapshot, status, providers and the indicative-rate notice. Recorded in `fx_conversion_audit` as `converter` (DEC-28) |

Unknown or inactive currencies are 422 (`unsupported currency`). Amounts and rates travel as strings.

## Tests

Reference cases (AED 500,000 → USD = 136,147.04; JPY with no decimals; half-up at the midpoint; liabilities), an independent computation in exact fractions, and property tests (cross rate equals the exact ratio to 45 digits, there-and-back is the identity, rounding error at most half a unit).

## Historical rates (P11-T05)

Three rate concepts are kept apart (`RateConcept`):

| Concept | Used for | Source |
|---|---|---|
| `transaction` | the rate recorded on a ledger posting | chosen once at posting (trade date, the pair's own rate); never recomputed |
| `historical_valuation` | past valuations and income, value series, conversion `on` a past day | the rate valid at the end of that day (UTC), at most 7 × 24 hours old, possibly through the pivot |
| `current_reporting` | today's figures in the reporting currency | the latest snapshot |

- `GET /api/v1/fx/history?base=&quote=&start=&end=` (up to 366 days): one point per day with rate, provider, timestamp and path; a day without a usable rate is `rate_missing` and has no rate (nothing is substituted); a rate carried from an earlier day inside the window (weekend, holiday) is `from_earlier_day`.
- `POST /api/v1/fx/convert` with `on`: the historical rate of that day (`concept: historical_valuation`, no snapshot); 404 when that day has no usable rate. A past figure is never converted with today's rate.
