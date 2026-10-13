# Opportunity pipeline (P12-T06)

Status: implemented in P12-T06.
- **Code:** `backend/app/modules/opportunities/`:
  - `service.py`: the pipeline;
  - `explain.py`: the model's explanation and its checks;
  - `models.py` (migration 0019), `schemas.py` and `api.py`.
- **Product intent:** [SOLUTION_INTENT.md](../SOLUTION_INTENT.md) sections 16 and 17.
- **Governance:** [ai-governance.md](../ai-governance.md) section 5.

## 1. Pipeline

`POST /api/v1/ai/opportunities` with optional `portfolio_id`, `amount`, `asset_class` and `limit` (1–5, default 3). The steps:

1. **Universe and eligibility** (investment-universe.md): only instruments eligible for the user.
2. **Features and scores** (scoring.md): highest score first; unscored instruments are skipped.
3. **Portfolio compatibility**, when a portfolio is given (compatibility.md):
   - checked for `amount`, or 5% of the portfolio's value by default;
   - `not_suitable` candidates are left out and listed in `excluded` with the reasons.
4. **Research:** up to 3 evidence items per candidate (research.md).
5. **Explanation:** the model explains each candidate from these facts only (section 2).
6. **Storage and audit:** the run is stored and an `ai.opportunities.run` audit event is written.

Each opportunity has:
- rank, instrument, asset class, risk level;
- **facts**: the score with its factors and contributions, compatibility before and after, and evidence with source, licence status and dates;
- `prices_as_of`, `universe_as_of`, and a **research horizon**: an assumption, the longer of the liquidity minimum and a risk-level table (1→0, 2→1, 3→3, 4→5, 5→7 years), with its basis stated;
- the explanation: thesis, why it surfaced, key risks, assumptions and the evidence ids cited;
- actions Research, Compare and Simulate;
- `is_trade: false`.

The response notice says it is not advice and not a recommendation, and that no return is expected or promised.

## 2. The model explains, nothing more

**What it receives:**
- the candidates' facts as JSON;
- compatibility as shares and checks only: no user identity, no amounts of money.

The prompt asks for a JSON object per candidate and forbids new facts, figures, forecasts, expected returns or advice.

**What is checked** (`explain.review`, deterministic):

| Problem | Rule |
|---|---|
| `not_structured` | not the JSON object; unknown fields refused |
| `wrong_instruments` | not exactly one entry per candidate |
| `unknown_evidence` | cites evidence not given for that candidate |
| `unsupported_figure` | a figure that is not in the facts (the P10 number check) |
| `guarantee_language`, `certainty_language`, `link_in_answer` | the P10 guards |
| `return_forecast` | "expected return", "will rise", "target price" and similar |
| `missing_risks` | a candidate with no key risk |

**On failure:**
- A failing reply gets one correction, which contains fixed wording for the problem codes and never repeats the reply.
- If it fails again, the model is unavailable, or no model is configured, a **deterministic template** is used. It is built from the facts and passes the same checks (tested).
- The run records `explanation_source` (`model` or `template`), the provider and model, and the problem codes. It never stores rejected text.

## 3. Runs

`opportunity_runs` and `opportunities` hold the request, the investor facts eligibility used, the weights, the excluded candidates, each opportunity's facts and explanation, and the model used.

- **Unchanged:** the database refuses updates (`opportunities_reject_update`).
- **Deleted with the user:** retention and deletion follow P15-T05.
- **Portfolio reference:** the portfolio id is kept as a reference without a foreign key, so a run outlives an archived portfolio unchanged.

| Endpoint | Returns |
|---|---|
| `GET /api/v1/ai/opportunities/runs` | your runs, newest first |
| `GET /api/v1/ai/opportunities/runs/{run_id}` | one run exactly as produced; another user's run is not found (IDOR test) |

**Limits:** `AI_OPPORTUNITY_RUNS_PER_DAY` (10) runs per user per rolling 24 hours, answered with 429 and `Retry-After`.

## 4. Tests

- `tests/opportunities/test_explain.py`: each refusal code, one correction then the model's text, the template on two failures, no model or an outage, exactly the facts sent, and a template that is deterministic and passes the checks.
- `tests/opportunities/test_opportunities_api.py`: an end-to-end run with a scripted model; the template on unacceptable replies; stored runs equal the response; audit; privacy and no updates; an empty run when nothing is eligible; the daily limit; validation.
