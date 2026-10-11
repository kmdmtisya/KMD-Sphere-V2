# Goals: progress, gap, required contribution and status

Status: Implemented in P06-T06.

- **Tables:** `goals` and `goal_scenarios` (migration 0008).
- **Calculation:** pure functions in `backend/app/modules/goals/progress.py`, on the forecast engine's month-based horizons (docs/design/forecast-engine.md).
- **API:** `/api/v1/goals`.

A goal's status is an **estimate under the assumptions the user states**. It is never presented as certain, and every progress response carries the notice: "Goal status and dates are estimates based on the assumptions shown. They are not guaranteed."

## 1. A goal

| Field | Meaning |
|---|---|
| name, goal_type | wealth, retirement, education, house_deposit, business_capital or custom (a label only) |
| target | the value to reach (Money: 0.01 to 10,000,000,000, at most the currency's minor units) |
| target_date | after today, at most 60 years ahead |
| target_in_todays_money | false: the target is the nominal amount on the date. True: it is in today's money and is grown by inflation to the date. |
| portfolio_id | the portfolio whose value funds the goal; null means all the user's active portfolios |
| assumptions | contribution per period (in the target's currency) and its frequency, yearly contribution growth, inflation, annual fee, compounding frequency, and the annual return of each scenario |

**Scenarios:**
- `base` is required, and the status is measured against it.
- `conservative` and `growth` are optional, with conservative <= base <= growth.
- The user chooses every rate; nothing is suggested.

**Limits:** every assumption limit is a forecast limit (`app/modules/forecasting/limits.py`), the same as the mobile calculator.

**Ownership and records:**
- A user has at most 50 goals, with unique names.
- Goals are plans, not financial records, so they can be changed and deleted. Create, update and delete write audit events (the type and changed fields, no amounts).

## 2. Current value

The current value is the funding portfolios' `total_value` (docs/design/portfolio-summary.md), converted to the target's currency at the latest rates (the consolidated rules).
- The result carries `value_complete` (false when assets are unpriced or currencies unconverted, so the value is understated) and `value_as_of` (the oldest input).
- A negative value counts as 0 in projections and progress; it is still reported.

## 3. Figures (as of today)

| Figure | Definition |
|---|---|
| `progress_percent` | current value / target x 100, between 0 and 100, 2 decimals half-up |
| `gap` | target - current value, at least 0 |
| `reached` | current value >= target |
| `months_left` | whole months from today to the target date (a month counts once its day is reached; negative after the date) |
| scenario projections | each scenario's value on the target date: starting from the current value, contributions at the end of each period, stepping up yearly, using the scenario's return. Values are shown nominal and in today's money, and are compared with the target in the target's own terms. With no whole month left, the projection is the current value. |
| `status` | `on_track` when reached, or when the base projection meets the target with at least a month left; otherwise `behind` |
| `overdue` | the date has passed and the target is not reached |
| `required_contribution` | the first-year contribution per period that makes the base projection meet the target on the date (closed form; the value is linear in the contribution), rounded half-up. It is null when reached or overdue, when less than a month is left, or when no contribution falls before the date (for example yearly contributions with under a year left). |
| `estimated_completion` | the first month in which the base scenario, with the current contribution, meets the target (searched up to 100 years), on the same day of that month or its last day. It is today when already reached, and null when not reached within 100 years. |

With `target_in_todays_money`, the projection is compared in today's money: the nominal value is divided by `(1 + inflation)^(months / 12)`.

## 4. API

| Route | Purpose |
|---|---|
| `POST /api/v1/goals` | create (201) |
| `GET /api/v1/goals` | the user's goals, by target date |
| `GET /api/v1/goals/summary` | progress and status of every goal, and how many are on track (the mobile GoalsSummary) |
| `GET /api/v1/goals/{goal_id}` | one goal |
| `PATCH /api/v1/goals/{goal_id}` | change any part; `assumptions` replaces all of them |
| `DELETE /api/v1/goals/{goal_id}` | delete (204) |
| `GET /api/v1/goals/{goal_id}/progress` | the figures above, with the assumptions, value freshness and the notice |

**Ownership (ADR-0011):**
- Another user's goal answers 404, exactly like a missing one.
- A missing portfolio and another user's portfolio are refused alike (422, "no such portfolio"), so `portfolio_id` cannot be used to probe portfolios.

## 5. Not modelled

- Passive-income targets (a target expressed as income a month); for now a target is an amount.
- Withdrawals.
- Several goals sharing one portfolio's value (each goal sees the whole value).
- Probability of success.
