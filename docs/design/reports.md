# Reports and exports (P14-T15, DEC-33)

The backend generates files of the signed-in user's own figures. The browser only asks for a file and saves it; nothing is calculated in `web/`.

## Endpoints

- `GET /api/v1/reports` lists the reports and formats.
- `GET /api/v1/reports/{kind}?format=pdf|xlsx|csv&portfolio_id=&currency=` returns the file (`Content-Disposition: attachment`, `Cache-Control: no-store`).
- Owner-scoped: a portfolio that is not the caller's is "not found" (404), like every other route. A missing `portfolio_id` for a report that needs one is 422; an unknown report is 404.
- Each generated file writes an audit event `reports.generated` (kind, format, currency, portfolio id; never the figures).

## Reports (v1)

| Kind | Needs portfolio | Contents |
|---|---|---|
| `portfolio` | yes | Totals (value, cash, cost basis, unrealised and realised result, income, expenses, net contributions) and the open holdings |
| `performance` | yes | Return, money-weighted return, profit and loss, contributions, and allocation by class, currency, country and sector |
| `net-worth` | no | Assets, liabilities, assets by class, each liability, and the exchange rates used |
| `income` | optional | All portfolios: monthly and yearly, by portfolio. One portfolio: last 12 months, by month, by type |
| `goals` | no | Each goal's status, target, progress, estimate and projected outcomes |

Not in v1: a standalone forecast report (the calculator is interactive and its inputs are not stored; goals reports carry the projected outcomes), FX-exposure as its own report (currency allocation is in `performance`) and the forex strategy report (arrives with the forex workspace, P14-T24).

## Formats

- **PDF**: landscape A4; title, as-of and currency block, one table per section, notes. Text from user data is escaped so it cannot use the PDF markup.
- **XLSX**: a Summary sheet (header block and notes) and one sheet per table; numeric columns are written as numbers.
- **CSV**: UTF-8 with a byte-order mark; header block, then each table under its title, then the notes.

Text that a spreadsheet could run as a formula (it starts with `=`, `+`, `-`, `@` or a control character) is prefixed with an apostrophe in CSV and XLSX, so an asset name cannot inject a formula. Numeric columns are not altered.

## Every file carries

When it was generated, the currency, the data as-of time, report-specific caveats (unpriced assets, currencies without a rate, assumed deposits) and the standing disclosures: not investment, tax or legal advice; past performance does not predict future results; projections are illustrations, never guaranteed returns.

## Consistency with the screens

Reports call the same services and output builders as the screens (for example `performance_out`, `allocation_out`, `NetWorthService`, `portfolio_income_out`), and money is written exactly as the API writes it. Tests compare the files' figures with the API's responses for the same request.
