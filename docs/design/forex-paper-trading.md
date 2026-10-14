# Forex paper trading and the trade journal, as built (P13-T09)

This document covers what was built for paper trading: the code, how fills and money work, the limits, the API and the controls that keep paper money apart. The design is in [forex-technical-design.md](forex-technical-design.md) section 11. The formulas are in [financial-methods.md](../financial-methods.md) section 23, and the tests are rows E-01 to E-06 of the financial test matrix.

**Rules for this module:**
- **Simulated only.** Paper trading uses virtual money and simulated fills. Nothing reaches a broker, and no order path to one exists (hard rule 1; the paper routes live under `/api/v1/forex/paper/`).
- **Separate money.** Paper balances never enter net worth, holdings or a real portfolio's analytics.
- **A separate series.** Paper results are labelled `paper` and are never combined with backtested (P13-T08) or live-observed results.
- **Always marked.** Every response carries `"mode": "PAPER TRADING"` and the header `X-Trading-Mode: PAPER TRADING`.

## 1. Code

The code is in `backend/app/modules/forex/paper/`:

| File | Content |
|---|---|
| `models.py` | `forex_paper_accounts`, `forex_paper_orders`, `forex_paper_positions` and `forex_paper_journal` (migration 0025) |
| `book.py` | Fills at the bid or ask, limit fills, stop and target triggers, sizes, levels, P/L and costs (pure) |
| `quotes.py` | The latest usable quote, the quotes after a time, and the conversion rates as of a time |
| `service.py` | Accounts, orders, evaluation, positions and the journal, all scoped to the owner |
| `analytics.py` | Performance over closed positions (pure) |
| `api.py` | The API (section 5) |

The `forex_paper_evaluate` job runs every minute when forex is switched on. It evaluates every active account with an open position or a pending order. Each account is also evaluated whenever it is read, so results never wait for the job.

## 2. Fills and evaluation

**Fills.**
- A market order fills at once at the stored ask (a buy) or bid (a sell), with the contract specification's slippage. It needs a fresh quote.
- A limit order waits until the quote reaches its price, then fills at that price.
- Every position needs a stop-loss.
- A stop fills as a market order at the triggering quote. A gap therefore fills beyond the stop, and the disclosures say that stops can slip or gap.
- A target fills at its price.

**Evaluation.** Pending orders and open positions read only the quotes after the last one they checked, in time order, up to 20,000 per pass. The first trigger wins. A fill or exit records its quote time.

**Money.**
- P/L is earned in the quote currency and converted into the account currency at the rates of the triggering quote's time, through the P13-T07 conversion.
- Each position records its rate and the path used.
- Costs are reported in two parts: what each fill paid against the mid, and the commissions.

## 3. Accounts

- A user may have up to `forex_paper_max_accounts` (5) active accounts.
- The account currency must be one of the forex currencies.
- The starting balance can be from 100 to 10,000,000. When it is omitted, the default of 10,000 is used and the account is marked `starting_balance_is_default`.
- An account can be closed only when it has no open positions and no pending orders. A closed account takes no orders.

## 4. Limits

An order is refused only when it cannot be filled:
- there is no fresh quote;
- the size or the levels are invalid;
- there is not enough free paper margin.

Everything else is a warning, never a silent change:
- risk per trade, leverage across positions, and margin use, which are the P13-T07 limits;
- the realised paper loss today and this week;
- exposure to each currency across the open positions.

The per-day and per-week loss limits and the cross-position exposure limit were deferred from P13-T07 to here. The T07 document first named P13-T10 for them in error; it is corrected.

**Margin.**
- The account shows the margin level and warns when it falls below 100%.
- Paper positions are not closed automatically for margin; a real broker would close them at its own stop-out level.
- Margin is checked when an order is placed. A limit order that fills later is not checked again.

## 5. API

Every route needs sign-in and the forex flag; when the flag is off it answers 404.

| Method and path | Purpose |
|---|---|
| `POST /paper/accounts`, `GET /paper/accounts`, `GET /paper/accounts/{account_id}` | Open a paper account, list accounts, and read one: balance, equity, unrealised P/L, margin, exposure and warnings |
| `POST /paper/accounts/{account_id}/close` | Close an account |
| `POST /paper/accounts/{account_id}/orders`, `GET .../orders?status=` | Place and list orders. A placed order returns its warnings and the disclosures |
| `POST .../orders/{order_id}/cancel` | Cancel a pending order |
| `GET .../positions?status=` | Positions; open ones are valued at the current quote |
| `POST .../positions/{position_id}/close` | Close at the current bid or ask |
| `PUT .../positions/{position_id}/levels` | Move the stop and target |
| `GET`, `POST .../journal`, `DELETE .../journal/{entry_id}` | Notes with tags, optionally about one position |
| `GET .../analytics` | Performance of the paper series, overall, by strategy tag and by pair |

## 6. Separation and ownership (QG-20.4)

**Tables.** The paper tables have no foreign key into portfolios, holdings, transactions or net-worth tables, and none points at them. Every row carries its owner.

**Isolation tests:**
- No module outside the paper package imports it or names its tables. The only exceptions are the app and worker wiring, and the Copilot's `get_paper_performance` tool (P13-T10), which reads the caller's own paper series, labelled PAPER TRADING.
- A user's net worth is unchanged by paper trading.
- Paper account creation, order placement and cancellation, closes and level changes are written to the audit log as `forex.paper.*` events, without amounts.

**Ownership.** Every route starts from the caller's own rows. Another user's account, order, position or journal entry answers 404, indistinguishable from a missing one.
- Every id route is registered in the IDOR registry.
- The integrity suite's sweep now runs with forex switched on. It shows that another user can neither read nor change any paper resource.

## 7. Limits and open items

- **The simulated feed** is the only price source (DEC-19). Every position records the data type of the quote it used (`simulated`), and every order warns that the price is not a tradable quote.
- **Swaps and financing** are not charged.
- **Stop-out** is not simulated (section 4).
- **The mobile screens** for paper trading come in P13-T12.
