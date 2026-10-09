"""Generates assets/demo/*.json, the DEMO fixtures for the mobile app (P03-T01).

Run from mobile/wealthsphere_app:  python tool/generate_demo_fixtures.py

Everything here is **illustrative sample data**, not real or live. Every file carries "demo": true.
The numbers are produced with Decimal arithmetic and written as strings, so the app never sees a
binary float for money. The app does no financial maths on them: it only displays what these files
(standing in for the backend) say. The generator exists only so the files stay internally
consistent and reproducible.
"""
import json
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, getcontext
from pathlib import Path

getcontext().prec = 40
OUT = Path(__file__).resolve().parent.parent / "assets" / "demo"
AS_OF = "2026-10-09T08:00:00Z"
TODAY = date(2026, 10, 9)
CENT = Decimal("0.01")


def q(v, places="0.01"):
    return str(Decimal(v).quantize(Decimal(places), rounding=ROUND_HALF_UP))


def money(v, cur="USD"):
    return {"amount": q(v), "currency": cur}


def write(name, payload):
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"demo": True, **payload}
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ----------------------------------------------------------------------------- portfolios
PORTFOLIOS = [
    # id, name, invested, value
    ("p-retire", "Retirement", "78000.00", "90250.40"),
    ("p-growth", "Growth", "27500.00", "31940.15"),
    ("p-income", "Income", "17200.00", "17795.80"),
]
FX = {"AED": Decimal("3.6725"), "KES": Decimal("129.20")}  # units of foreign currency per 1 USD (illustrative)


def summary(pid, name, invested, value):
    inv, val = Decimal(invested), Decimal(value)
    pl = val - inv
    return {
        "portfolio_id": pid,
        "name": name,
        "base_currency": "USD",
        "value": money(val),
        "invested": money(inv),
        "profit_loss": money(pl),
        "return_percent": q(pl / inv * 100),
        "as_of": AS_OF,
    }


summaries = {pid: summary(pid, n, i, v) for pid, n, i, v in PORTFOLIOS}
tot_inv = sum(Decimal(i) for _, _, i, _ in PORTFOLIOS)
tot_val = sum(Decimal(v) for _, _, _, v in PORTFOLIOS)
summaries["consolidated"] = summary("consolidated", "All portfolios", tot_inv, tot_val)

write("portfolios.json", {
    "portfolios": [{"id": pid, "name": n, "base_currency": "USD"} for pid, n, _, _ in PORTFOLIOS],
    "summaries": summaries,
})

# ----------------------------------------------------------------------------- holdings
H = {  # portfolio -> [(symbol, name, class, base value, native currency)]
    "p-retire": [
        ("DEMO-GEQ", "Demo Global Equity Fund", "Equities", "42000.00", "USD", 1.8),
        ("DEMO-BND", "Demo Aggregate Bond Fund", "Bonds", "26500.40", "USD", -0.2),
        ("DEMO-EMR", "Demo Emirates Index Fund", "Equities", "14750.00", "AED", 2.4),
        ("DEMO-CSH", "Demo Cash Reserve", "Cash", "7000.00", "USD", 0.0),
    ],
    "p-growth": [
        ("DEMO-TEC", "Demo Technology ETF", "Equities", "15600.15", "USD", 3.1),
        ("DEMO-KEN", "Demo Nairobi Equity Fund", "Equities", "8340.00", "KES", -1.1),
        ("DEMO-CRY", "Demo Digital Asset Trust", "Alternatives", "8000.00", "USD", 5.6),
    ],
    "p-income": [
        ("DEMO-DIV", "Demo Dividend Aristocrats", "Equities", "9795.80", "USD", 0.7),
        ("DEMO-KTB", "Demo Kenya Treasury Fund", "Bonds", "5000.00", "KES", 0.3),
        ("DEMO-REI", "Demo Real Estate Trust", "Real estate", "3000.00", "AED", 0.9),
    ],
}


def holding(pid, row):
    sym, name, cls, base, cur, chg = row
    base_d = Decimal(base)
    native = base_d if cur == "USD" else base_d * FX[cur]
    return {
        "symbol": sym,
        "name": name,
        "asset_class": cls,
        "value": money(base_d),
        "native_value": money(native, cur),
        "change_percent": q(Decimal(str(chg))),
        "as_of": AS_OF,
    }


holdings = {pid: [holding(pid, r) for r in rows] for pid, rows in H.items()}
holdings["consolidated"] = [h for pid in H for h in holdings[pid]]
# make the holdings sum equal the portfolio value exactly (display data must agree with the totals)
for pid in H:
    total = sum(Decimal(h["value"]["amount"]) for h in holdings[pid])
    assert total == Decimal(summaries[pid]["value"]["amount"]), (pid, total)
write("holdings.json", {"holdings": {k: {"items": v} for k, v in holdings.items()}})

# ----------------------------------------------------------------------------- allocation
def allocation(rows):
    by = {}
    for h in rows:
        by[h["asset_class"]] = by.get(h["asset_class"], Decimal(0)) + Decimal(h["value"]["amount"])
    total = sum(by.values())
    weights = {k: (v / total * 100).quantize(CENT, rounding=ROUND_HALF_UP) for k, v in by.items()}
    drift = Decimal(100) - sum(weights.values())  # server-side largest-remainder style fix-up
    top = max(weights, key=weights.get)
    weights[top] += drift
    return [{"label": k, "value": money(by[k]), "weight_percent": str(weights[k])} for k in sorted(by, key=lambda x: -by[x])]


allocs = {pid: allocation(holdings[pid]) for pid in holdings}
write("allocation.json", {"allocation": {k: {"items": v} for k, v in allocs.items()}})

# ----------------------------------------------------------------------------- metrics
write("metrics.json", {"metrics": {
    "p-retire": {"total_return_percent": "15.71", "cagr_percent": "6.12", "dividend_yield_percent": "2.10", "volatility_percent": "9.40"},
    "p-growth": {"total_return_percent": "16.14", "cagr_percent": "8.30", "dividend_yield_percent": "0.60", "volatility_percent": "17.80"},
    "p-income": {"total_return_percent": "3.46", "cagr_percent": "2.90", "dividend_yield_percent": "4.80", "volatility_percent": "5.20"},
    "consolidated": {"total_return_percent": "14.09", "cagr_percent": "6.35", "dividend_yield_percent": "2.30", "volatility_percent": "10.10"},
}, "as_of": AS_OF})

# ----------------------------------------------------------------------------- performance series
PERIODS = {  # period -> (days back, points)
    "week": (7, 8),
    "month": (30, 16),
    "threeMonths": (91, 14),
    "sixMonths": (182, 14),
    "yearToDate": (282, 20),
    "year": (365, 13),
    "all": (1460, 17),
}


def series_for(end_value, drift_bias, seed):
    """Deterministic illustrative path ending exactly at end_value."""
    out = {}
    for period, (days, n) in PERIODS.items():
        pts = []
        state = (seed * 7919 + days) % 1000
        level = Decimal(1)
        raw = []
        for i in range(n):
            state = (state * 1103515245 + 12345) % 2147483648
            wiggle = (Decimal(state % 1000) / 1000 - Decimal("0.5")) * Decimal("0.03")
            level = level * (1 + Decimal(drift_bias) * Decimal(days) / Decimal(365) / n + wiggle / 4)
            raw.append(level)
        scale = Decimal(end_value) / raw[-1]
        for i in range(n):
            d = TODAY - timedelta(days=round(days * (n - 1 - i) / (n - 1)))
            pts.append({"date": d.isoformat(), "value": q(raw[i] * scale)})
        out[period] = pts
    return out


performance = {}
for k, (pid, _, _, val) in enumerate(PORTFOLIOS):
    performance[pid] = series_for(val, "0.07", k + 1)
performance["consolidated"] = series_for(tot_val, "0.07", 9)
write("performance.json", {"currency": "USD", "performance": performance, "as_of": AS_OF})

# ----------------------------------------------------------------------------- dashboard
write("dashboard.json", {
    "greeting": {"name": "Alex"},
    "net_worth": {
        "assets": money(tot_val + Decimal("46500.00")),
        "liabilities": money("18200.00"),
        "net_worth": money(tot_val + Decimal("46500.00") - Decimal("18200.00")),
        "as_of": AS_OF,
    },
    "income": {"monthly": money("1245.30"), "yearly": money("14943.60"), "as_of": AS_OF},
    "goals": {
        "on_track": 3,
        "total": 4,
        "items": [
            {"id": "g-home", "name": "Home deposit", "progress_percent": "62.50", "status": "on_track"},
            {"id": "g-edu", "name": "Education fund", "progress_percent": "41.00", "status": "on_track"},
            {"id": "g-ret", "name": "Retirement at 60", "progress_percent": "28.30", "status": "on_track"},
            {"id": "g-trip", "name": "Family travel", "progress_percent": "18.00", "status": "behind"},
        ],
        "as_of": AS_OF,
    },
    "insight": {
        "text": "Your portfolios are up 14.09% since you started investing. Equities make up most of the growth, and about a fifth of your holdings are in AED and KES.",
        "as_of": AS_OF,
        "sources": [
            {"label": "Portfolio valuation (demo)", "provider": "Demo Data Co.", "as_of": AS_OF},
            {"label": "FX rates (demo)", "provider": "Demo Data Co.", "as_of": "2026-10-09T07:55:00Z"},
        ],
    },
})

# ----------------------------------------------------------------------------- forecast (canned)
REQ = {
    "initial_investment": money("10000.00"),
    "monthly_contribution": money("500.00"),
    "annual_return_percent": "8.00",
    "years": 20,
    "contribution_growth_percent": "0.00",
    "inflation_percent": "2.50",
    "annual_fee_percent": "0.50",
    "compounding_frequency": "monthly",
    "contribution_frequency": "monthly",
    "conservative_return_percent": "5.00",
    "growth_return_percent": "12.00",
}


def project(rate_pct):
    net = (Decimal(rate_pct) - Decimal(REQ["annual_fee_percent"])) / 100
    m = (1 + net) ** (Decimal(1) / 12) - 1
    bal = Decimal(REQ["initial_investment"]["amount"])
    contrib = Decimal(REQ["monthly_contribution"]["amount"])
    infl = Decimal(1) + Decimal(REQ["inflation_percent"]) / 100
    nominal, real = [{"year": 0, "value": q(bal)}], [{"year": 0, "value": q(bal)}]
    paid = bal
    for month in range(1, REQ["years"] * 12 + 1):
        bal = bal * (1 + m) + contrib
        paid += contrib
        if month % 12 == 0:
            y = month // 12
            nominal.append({"year": y, "value": q(bal)})
            real.append({"year": y, "value": q(bal / infl**y)})
    return {
        "annual_return_percent": q(rate_pct),
        "nominal": nominal,
        "real": real,
        "final_nominal": money(bal),
        "final_real": money(bal / infl ** REQ["years"]),
        "total_contributions": money(paid),
        "total_growth": money(bal - paid),
    }


write("forecast.json", {
    "request": REQ,
    "response": {
        "currency": "USD",
        "scenarios": {
            "conservative": project(REQ["conservative_return_percent"]),
            "base": project(REQ["annual_return_percent"]),
            "growth": project(REQ["growth_return_percent"]),
        },
        "assumptions": REQ,
        "as_of": AS_OF,
        "notice": "Projections are illustrative scenarios based on the assumptions shown. They are not guaranteed.",
    },
})

# ----------------------------------------------------------------------------- copilot scripts
SRC_PORT = {"label": "Portfolio valuation (demo)", "provider": "Demo Data Co.", "as_of": AS_OF}
SRC_FX = {"label": "FX rates (demo)", "provider": "Demo Data Co.", "as_of": "2026-10-09T07:55:00Z"}
DISCLAIMER = "This is a demonstration reply from sample data."


def answer(sid, question, tools, sections, sources):
    return {
        "id": sid,
        "kind": "answer",
        "question": question,
        "events": (
            [{"type": "tool", "text": t} for t in tools]
            + [{"type": "section", "kind": k, "text": t} for k, t in sections]
            + [{"type": "source", **s} for s in sources]
            + [{"type": "done"}]
        ),
    }


scripts = [
    answer(
        "performance",
        "How is my portfolio performing?",
        ["Fetching portfolio summary…", "Fetching performance metrics…"],
        [
            ("observed", "Across your three portfolios the value is $139,986.35 against $122,700.00 invested, as of 9 Oct 2026."),
            ("calculated", "That is a total return of 14.09% (CAGR 6.35%), with volatility of 10.10%. Figures come from the portfolio engine, not the AI."),
            ("assumption", "Returns are shown in USD, your base currency, and include price changes and income, before any tax."),
            ("interpretation", "Growth has come mostly from equities. The income portfolio has been steadier but has contributed less. Past performance does not indicate future results."),
        ],
        [SRC_PORT, SRC_FX],
    ),
    answer(
        "risk",
        "What are the biggest risks in my portfolio?",
        ["Fetching allocation…", "Running portfolio checks…"],
        [
            ("observed", "Equities are about 64.65% of your holdings, bonds 22.50%, alternatives 5.71%, cash 5.00% and real estate 2.14%. About 22% is held in AED and KES."),
            ("calculated", "Estimated annual volatility is 10.10%, driven mainly by the growth portfolio at 17.80%."),
            ("assumption", "Volatility is estimated from historical monthly returns and may not repeat."),
            ("interpretation", "The main things to watch are concentration in equities and currency moves in AED and KES holdings. This is not personalised advice."),
        ],
        [SRC_PORT],
    ),
    answer(
        "forecast",
        "How much could I have in 20 years?",
        ["Fetching forecast scenarios…"],
        [
            ("observed", "You invest $10,000 now and $500 each month."),
            ("calculated", "With the base assumption of 8% a year, 0.5% fees and 2.5% inflation, the projection after 20 years is about $311,122 before inflation (about $189,868 in today's money) (conservative and growth scenarios are shown on the Forecast screen)."),
            ("assumption", "Returns are assumed constant and are not guaranteed. Real markets move up and down."),
            ("interpretation", "Regular contributions drive most of the result over this period. Try the calculator to see how different assumptions change the outcome."),
        ],
        [SRC_PORT],
    ),
    answer(
        "currency",
        "Which of my holdings are in foreign currencies?",
        ["Fetching holdings…", "Fetching FX rates…"],
        [
            ("observed", "Four holdings are priced in AED or KES: the Emirates Index Fund, the Nairobi Equity Fund, the Kenya Treasury Fund and the Real Estate Trust."),
            ("calculated", "Together they are worth about $31,090 in USD, using the FX rates shown in the sources."),
            ("assumption", "Conversions use the latest available rate, which can change during the day."),
            ("interpretation", "Moves in AED and KES against USD will change the USD value of these holdings even if their local prices do not move."),
        ],
        [SRC_PORT, SRC_FX],
    ),
    {
        "id": "refusal",
        "kind": "refusal",
        "question": "Guarantee me a 20% return",
        "events": [{"type": "refusal", "text": "I can't guarantee returns. No one can, and investment values can fall as well as rise. I can show you scenarios with clearly stated assumptions instead."}],
    },
    {
        "id": "failure",
        "kind": "failure",
        "question": "Show me a failing request (demo)",
        "events": [{"type": "tool", "text": "Fetching portfolio summary…"}, {"type": "error", "text": "The assistant could not complete this request. Please try again."}],
    },
]
write("copilot.json", {
    "intro": "Ask about your portfolio, risks, goals and forecasts.",
    "notice": "Demo responses, not connected to your data.",
    "suggested": [s["question"] for s in scripts if s["kind"] == "answer"],
    "unsupported_reply": "Demo mode can answer the suggested questions only.",
    "scripts": scripts,
})
print("wrote", sorted(p.name for p in OUT.glob("*.json")))
