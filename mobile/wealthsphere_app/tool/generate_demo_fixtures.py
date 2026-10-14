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
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    # LF on every platform, so the files are identical wherever they are generated.
    (OUT / name).write_text(text, encoding="utf-8", newline="\n")


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
# --------------------------------------------------------------------- reporting currency (P11-T07)
CURRENCIES = [
    ("AED", "UAE dirham", "AED", 2), ("AUD", "Australian dollar", "A$", 2),
    ("CAD", "Canadian dollar", "CA$", 2), ("CHF", "Swiss franc", "CHF", 2),
    ("EUR", "Euro", "€", 2), ("GBP", "Pound sterling", "£", 2),
    ("JPY", "Japanese yen", "¥", 0), ("KES", "Kenyan shilling", "KSh", 2),
    ("USD", "US dollar", "$", 2), ("ZAR", "South African rand", "R", 2),
]
USD_RATES = {
    "AED": "3.6725", "AUD": "1.5112", "CAD": "1.3705", "CHF": "0.8634", "EUR": "0.9216",
    "GBP": "0.7712", "JPY": "149.83", "KES": "129.15", "ZAR": "17.8421",
}


def usd_rate(base, quote):
    """1 base = ? quote through USD (demo data only; the live app never computes this)."""
    to_usd = Decimal(1) if base == "USD" else 1 / Decimal(USD_RATES[base])
    from_usd = Decimal(1) if quote == "USD" else Decimal(USD_RATES[quote])
    return to_usd * from_usd


def example(amount, source, target):
    rate = usd_rate(source, target)
    places = "1" if target == "JPY" else "0.01"
    path = None if "USD" in (source, target) else [source, "USD", target]
    return {
        "source": {"amount": amount, "currency": source},
        "converted": {"amount": q(Decimal(amount) * rate, places), "currency": target},
        "rate": str(rate.quantize(Decimal("0.000000000001"), rounding=ROUND_HALF_UP)),
        "path": path,
        "status": "current",
        "rate_timestamp": AS_OF,
        "providers": ["demo"],
    }


write("currency.json", {
    "currencies": [
        {"code": c, "name": n, "symbol": s, "decimal_places": d} for c, n, s, d in CURRENCIES
    ],
    "preferences": {"reporting_currency": "USD", "recent_currencies": [], "is_default": True},
    "status": {
        "pivot_currency": "USD",
        "checked_at": AS_OF,
        "rates": [
            {"currency": c, "status": "current", "rate": r, "provider": "demo",
             "rate_type": "indicative", "rate_timestamp": AS_OF, "retrieved_at": AS_OF}
            for c, r in sorted(USD_RATES.items())
        ],
    },
    "examples": [
        example("500000.00", "AED", "USD"),
        example("1000.00", "USD", "KES"),
        example("250.00", "EUR", "GBP"),
        example("100.00", "USD", "JPY"),
    ],
    "notice": "Demo rates, not live. The demo converts the examples only.",
})


# ---------------------------------------------------------------------------------- forex (P13-T11)
# Illustrative forex data for the DEMO app: simulated prices, a DEMO calendar, a worked risk
# example, backtest summaries and a PAPER TRADING account. Shapes follow the forex API.
FX_AS_OF = "2026-10-09T08:00:00Z"
FX_PAIRS = [
    # code, mid, pip location, display precision, tier, half spread in pips
    ("EUR_USD", "1.08616", -4, 5, "major", "0.6"),
    ("GBP_USD", "1.26420", -4, 5, "major", "0.6"),
    ("USD_JPY", "149.874", -2, 3, "major", "0.6"),
    ("AUD_USD", "0.65512", -4, 5, "major", "0.6"),
    ("EUR_GBP", "0.85918", -4, 5, "minor", "1.0"),
    ("USD_KES", "129.150", -2, 3, "exotic", "20"),
]


def fx_quote(code, mid, loc, prec, tier, half, age=3, freshness="fresh"):
    pip = Decimal(1).scaleb(loc)
    m = Decimal(mid)
    h = Decimal(half) * pip
    places = "1e-%d" % prec
    return {
        "instrument": code,
        "provider": "demo",
        "bid": q(m - h, places),
        "ask": q(m + h, places),
        "mid": q(m, places),
        "mid_derived": True,
        "ts_provider": "2026-10-09T07:59:57Z",
        "ts_received": "2026-10-09T07:59:57Z",
        "age_seconds": age,
        "data_type": "simulated",
        "quality": "ok" if freshness == "fresh" else "stale",
        "freshness": freshness,
        "feed_status": "connected",
    }


fx_quotes = [fx_quote(*p) for p in FX_PAIRS[:-1]] + [fx_quote(*FX_PAIRS[-1], age=900, freshness="stale")]


def fx_candles(mid, loc, prec, n=60):
    """A gentle rise with a regular wiggle: illustrative only."""
    places = "1e-%d" % prec
    pip = Decimal(1).scaleb(loc)
    start = Decimal(mid) - pip * 40
    rows = []
    for k in range(n):
        close = start + pip * (Decimal(k) * Decimal("0.7") + Decimal((k * 7) % 11) - 5)
        open_ = close - pip * Decimal((k * 3) % 5 - 2)
        high = max(open_, close) + pip * 3
        low = min(open_, close) - pip * 3
        hour = 8 + k  # hourly bars ending at the as-of time
        day = 7 + hour // 24
        rows.append({
            "ts": "2026-10-%02dT%02d:00:00Z" % (day, hour % 24),
            "open": q(open_, places),
            "high": q(high, places),
            "low": q(low, places),
            "close": q(close, places),
            "volume": None,
            "data_type": "simulated",
        })
    return rows


FOREX_NOTICE = (
    "DEMO: illustrative simulated prices and research for exploring the app. Not live market data, "
    "not advice, and nothing is traded."
)

write("forex.json", {
    "as_of": FX_AS_OF,
    "notice": FOREX_NOTICE,
    "quotes": {"as_of": FX_AS_OF, "provider": "demo", "feed_status": "connected", "items": fx_quotes,
               "notice": FOREX_NOTICE},
    "candles": {p[0]: fx_candles(p[1], p[2], p[3]) for p in FX_PAIRS[:4]},
    "indicators": {
        "EUR_USD": [
            {"name": "rsi", "value": "61.42"},
            {"name": "atr", "value": "0.00087"},
            {"name": "adx", "value": "27.9"},
            {"name": "ema:20", "value": "1.08544"},
            {"name": "ema:50", "value": "1.08391"},
            {"name": "macd.histogram", "value": "0.00012"},
        ],
    },
    "levels": {
        "EUR_USD": [
            {"price": "1.08950", "role": "resistance", "touches": 3, "first_ts": FX_AS_OF,
             "last_ts": FX_AS_OF, "established_ts": FX_AS_OF},
            {"price": "1.08320", "role": "support", "touches": 4, "first_ts": FX_AS_OF,
             "last_ts": FX_AS_OF, "established_ts": FX_AS_OF},
        ],
    },
    "forecast_notice": "A model forecast with its uncertainty, not a prediction and not advice.",
    "forecasts": {
        "EUR_USD:4h": {
            "instrument": "EUR_USD", "horizon": "4h", "timeframe": "1H", "bars_ahead": 4,
            "status": "available", "reason": None,
            "notice": "A model forecast with its uncertainty, not a prediction and not advice.",
            "model": {"name": "lightgbm", "version": "demo-1", "family": "tree",
                      "trained_at": FX_AS_OF, "calibration_status": "calibrated",
                      "drift_status": "ok", "edge": False, "data_types": ["simulated"],
                      "statement": "no demonstrated edge: the random-walk baseline is shown (on simulated data: not evidence about real markets)",
                      "probability_source": "raw", "feature_set_hash": "demo", "data_snapshot_hash": "demo",
                      "code_version": "demo", "seed": 7},
            "forecast": {"as_of": FX_AS_OF, "generated_at": FX_AS_OF, "age_seconds": 0, "fresh": True,
                         "last_close": "1.08616", "prob_up": "0.5612", "prob_down": "0.4388",
                         "probability_label": "Calibrated",
                         "probability_note": "Calibrated on out-of-sample windows.",
                         "return_quantiles": {"q10": "-0.0032", "q25": "-0.0014", "q50": "0.0008", "q75": "0.0029", "q90": "0.0047"},
                         "price_median": "1.08702", "price_interval_50": {"low": "1.08465", "high": "1.08931"},
                         "price_interval_80": {"low": "1.08311", "high": "1.09087"},
                         "expected_volatility": "0.00214", "volatility_model": "ewma",
                         "data_types": ["simulated"]},
        },
        "EUR_USD:24h": {
            "instrument": "EUR_USD", "horizon": "24h", "timeframe": "4H", "bars_ahead": 6,
            "status": "available", "reason": None,
            "notice": "A model forecast with its uncertainty, not a prediction and not advice.",
            "model": {"name": "arima", "version": "demo-1", "family": "statistical",
                      "trained_at": FX_AS_OF, "calibration_status": "requires_calibration",
                      "drift_status": "ok", "edge": False, "data_types": ["simulated"],
                      "statement": "no demonstrated edge: the random-walk baseline is shown (on simulated data: not evidence about real markets)",
                      "probability_source": "raw", "feature_set_hash": "demo", "data_snapshot_hash": "demo",
                      "code_version": "demo", "seed": 7},
            "forecast": {"as_of": FX_AS_OF, "generated_at": FX_AS_OF, "age_seconds": 0, "fresh": True,
                         "last_close": "1.08616", "prob_up": "0.5310", "prob_down": "0.4690",
                         "probability_label": "Requires calibration",
                         "probability_note": "Not reliable as a probability until calibrated.",
                         "return_quantiles": {"q10": "-0.0071", "q25": "-0.0031", "q50": "0.0004", "q75": "0.0042", "q90": "0.0079"},
                         "price_median": "1.08659", "price_interval_50": {"low": "1.08279", "high": "1.09072"},
                         "price_interval_80": {"low": "1.07845", "high": "1.09474"},
                         "expected_volatility": "0.00511", "volatility_model": "har",
                         "data_types": ["simulated"]},
        },
    },
    "ranking": {
        "as_of": FX_AS_OF, "timeframe": "1H", "weights_version": 1, "weights": {},
        "notice": "Research candidates ranked by a published formula from stored prices. Not advice, not a recommendation to buy or sell, and not a probability of profit.",
        "excluded": [],
        "items": [
            {
                "rank": 1, "instrument": "EUR_USD", "tier": "major", "label": "Research candidate",
                "market_condition": "trending", "opportunity_type": "trend_continuation",
                "scenario": "Bullish scenario", "risk": "medium", "score": "68.4",
                "levels": {"as_of": FX_AS_OF, "entry": "1.08616", "stop": "1.08320", "target": "1.09208",
                           "risk_pips": "29.6", "reward_pips": "59.2", "risk_reward": "2.00"},
                "factors": [
                    {"name": "trend_strength", "value": "0.558", "weight": "0.15", "contribution": "0.0837", "detail": "ADX 27.9, directional indicators agree"},
                    {"name": "momentum", "value": "0.381", "weight": "0.10", "contribution": "0.0381", "detail": "RSI 61.4"},
                    {"name": "risk_reward", "value": "0.667", "weight": "0.15", "contribution": "0.1000", "detail": "reward / risk 2.00"},
                    {"name": "macro_event_risk", "value": "0", "weight": "-0.20", "contribution": "0", "detail": "no event window"},
                ],
                "adjustments": [], "assumptions": ["Levels come from the last closed bar and the rule definition."],
                "risks": ["Simulated prices: says nothing about real markets.", "Prices can move past any level."],
                "evidence": ["EMA(20) above EMA(50)"],
                "costs": {"spread_pips": "1.2", "spread_share_of_risk": "0.04", "note": "Spread only."},
                "freshness": {"bar_as_of": FX_AS_OF, "bar_age_seconds": 120, "quote_age_seconds": 3, "data_types": ["simulated"]},
                "forecast": {"horizon": "4h", "prob_up": "0.5612", "calibration": "Calibrated", "model": "lightgbm", "model_version": "demo-1"},
                "rule": "trend_continuation", "rule_version": 1,
            },
            {
                "rank": 2, "instrument": "AUD_USD", "tier": "major", "label": "Research candidate",
                "market_condition": "consolidating", "opportunity_type": "range",
                "scenario": "Bearish scenario", "risk": "low", "score": "52.1",
                "levels": {"as_of": FX_AS_OF, "entry": "0.65512", "stop": "0.65790", "target": "0.65250",
                           "risk_pips": "27.8", "reward_pips": "26.2", "risk_reward": "0.94"},
                "factors": [
                    {"name": "volatility_suitability", "value": "0.910", "weight": "0.10", "contribution": "0.0910", "detail": "ATR is 0.91 x its median"},
                    {"name": "liquidity", "value": "1", "weight": "0.10", "contribution": "0.1000", "detail": "major pair"},
                ],
                "adjustments": [], "assumptions": ["Levels come from the last closed bar and the rule definition."],
                "risks": ["Simulated prices: says nothing about real markets."],
                "evidence": ["ADX below 20"],
                "costs": {"spread_pips": "1.2", "spread_share_of_risk": "0.04", "note": "Spread only."},
                "freshness": {"bar_as_of": FX_AS_OF, "bar_age_seconds": 120, "quote_age_seconds": 3, "data_types": ["simulated"]},
                "forecast": None, "rule": "range", "rule_version": 1,
            },
        ],
    },
    "calendar": [
        {"id": "demo-ev-1", "name": "US Non-Farm Payrolls", "kind": "employment", "currencies": ["USD"],
         "importance": "high", "scheduled_at": "2026-10-09T12:30:00Z", "scheduled_local": "2026-10-09T12:30:00Z",
         "is_demo": True, "licence_status": "demo", "source": "demo", "source_url": None, "retrieved_at": FX_AS_OF,
         "actual_seen_at": None, "commentary": None,
         "confirmed": {"actual": None, "previous": "142", "unit": "k", "released": False},
         "expectation": {"forecast": "155"},
         "risk_window": {"name": "US Non-Farm Payrolls", "currencies": ["USD"], "importance": "high",
                         "scheduled_at": "2026-10-09T12:30:00Z", "starts": "2026-10-09T12:00:00Z", "ends": "2026-10-09T13:30:00Z"}},
        {"id": "demo-ev-2", "name": "ECB Interest Rate Decision", "kind": "policy_rate", "currencies": ["EUR"],
         "importance": "high", "scheduled_at": "2026-10-10T12:15:00Z", "scheduled_local": "2026-10-10T12:15:00Z",
         "is_demo": True, "licence_status": "demo", "source": "demo", "source_url": None, "retrieved_at": FX_AS_OF,
         "actual_seen_at": None, "commentary": None,
         "confirmed": {"actual": None, "previous": "2.25", "unit": "%", "released": False},
         "expectation": {"forecast": "2.25"}, "risk_window": None},
        {"id": "demo-ev-3", "name": "UK Retail Sales", "kind": "consumption", "currencies": ["GBP"],
         "importance": "medium", "scheduled_at": "2026-10-08T06:00:00Z", "scheduled_local": "2026-10-08T06:00:00Z",
         "is_demo": True, "licence_status": "demo", "source": "demo", "source_url": None, "retrieved_at": FX_AS_OF,
         "actual_seen_at": FX_AS_OF, "commentary": None,
         "confirmed": {"actual": "0.4", "previous": "0.1", "unit": "%", "released": True},
         "expectation": {"forecast": "0.2"}, "risk_window": None},
    ],
    "risk_example": {
        "instrument": "EUR_USD", "direction": "long", "account_currency": "USD",
        "size": {"units": "19000", "lots": "0.19", "status": "sized"},
        "pip_value": {"pip_size": "0.0001", "per_lot_quote_currency": "10", "per_lot_account_currency": "10", "quote_currency": "USD"},
        "outcome": {"risk_amount": "100", "stop_pips": "50", "target_pips": "100", "loss_before_costs": "95",
                    "loss_after_costs": "98.04", "profit_before_costs": "190", "profit_after_costs": "186.96",
                    "risk_reward_before_costs": "2", "risk_reward_after_costs": "1.91"},
        "costs": {"spread": "2.28", "slippage": "0.76", "commission": "0", "total": "3.04", "note": "Spread, slippage and commission for entry and exit."},
        "margin": {"notional": "20900", "margin": "695.97", "margin_use_percent": "6.96", "position_leverage": "2.09", "max_leverage": "30.03"},
        "account_impact_percent": "0.98", "exposure": [], "exposure_percent": "209",
        "conversion": {"rate": "1", "path": "same currency", "as_of": None, "data_types": [], "stale": False},
        "specification": {"version": 1, "review_status": "unreviewed", "reviewed_by": None, "reviewed_at": None},
        "limits": {"max_risk_percent": "2", "max_leverage": "30", "max_margin_use_percent": "50"},
        "warnings": ["The contract specifications are unreviewed defaults, not a broker's terms."],
        "disclosures": [
            "A stop-loss does not guarantee the maximum loss: prices can gap or slip past it, for example over a weekend or around news.",
            "Leverage amplifies losses as well as gains; a loss can exceed the margin placed.",
            "All values are estimates from the configured contract specifications and the stated rates and costs. This is a calculator for study and paper trading, not advice; nothing is placed.",
        ],
        "notice": "DEMO: one worked example.",
    },
    "backtests": [
        {"instrument": "EUR_USD", "rule": "trend_continuation", "out_of_sample_trades": 42, "out_of_sample_return": "0.0371",
         "out_of_sample_profit_factor": "1.32", "leakage_audit_passed": True, "period_start": "2026-07-01T00:00:00Z",
         "period_end": "2026-10-08T00:00:00Z", "data_types": ["simulated"]},
        {"instrument": "EUR_USD", "rule": "breakout", "out_of_sample_trades": 18, "out_of_sample_return": "-0.0124",
         "out_of_sample_profit_factor": "0.81", "leakage_audit_passed": True, "period_start": "2026-07-01T00:00:00Z",
         "period_end": "2026-10-08T00:00:00Z", "data_types": ["simulated"]},
    ],
    "paper_accounts": [
        {"mode": "PAPER TRADING", "id": "demo-paper-1", "name": "Practice", "currency": "USD", "status": "active",
         "starting_balance": "10000", "starting_balance_is_default": True, "balance": "10086.4",
         "unrealised_pnl": "12.6", "equity": "10099", "used_margin": "361.71", "free_margin": "9737.29",
         "margin_level_percent": "2792.02", "open_positions": 1, "pending_orders": 0,
         "realised_today": "0", "realised_this_week": "86.4", "exposure": [], "warnings": [],
         "created_at": "2026-10-01T09:00:00Z", "notice": "PAPER TRADING"},
    ],
    "paper_positions": [
        {"mode": "PAPER TRADING", "id": "demo-pos-1", "account_id": "demo-paper-1", "order_id": "demo-ord-1",
         "instrument": "EUR_USD", "side": "long", "lots": "0.1", "units": "10000", "status": "open",
         "entry_price": "1.08490", "entry_at": "2026-10-08T14:00:00Z", "data_type": "simulated",
         "stop": "1.08200", "target": "1.09100", "margin": "361.71", "strategy_tag": "trend",
         "current_price": "1.08616", "unrealised_pnl": "12.6", "exit_price": None, "exit_at": None,
         "exit_reason": None, "exit_rate": None, "exit_rate_path": None, "realised_pnl": None, "costs": None},
        {"mode": "PAPER TRADING", "id": "demo-pos-0", "account_id": "demo-paper-1", "order_id": "demo-ord-0",
         "instrument": "GBP_USD", "side": "short", "lots": "0.1", "units": "10000", "status": "closed",
         "entry_price": "1.27290", "entry_at": "2026-10-06T10:00:00Z", "data_type": "simulated",
         "stop": "1.27800", "target": "1.26400", "margin": "423.88", "strategy_tag": "range",
         "current_price": None, "unrealised_pnl": None, "exit_price": "1.26400", "exit_at": "2026-10-07T16:00:00Z",
         "exit_reason": "target", "exit_rate": "1", "exit_rate_path": "same currency", "realised_pnl": "86.4",
         "costs": "2.6"},
    ],
    "journal": [
        {"mode": "PAPER TRADING", "id": "demo-note-0", "account_id": "demo-paper-1", "position_id": "demo-pos-0",
         "note": "Took the range rule's short at the top of the band; target hit the next day.",
         "tags": ["range", "review"], "created_at": "2026-10-07T17:00:00Z"},
    ],
    "paper_performance": {
        "mode": "PAPER TRADING", "label": "paper", "account_id": "demo-paper-1", "currency": "USD",
        "series_note": "Paper results only: a separate, labelled series, never combined with backtested or live-observed results and never part of a real portfolio's analytics.",
        "starting_balance": "10000",
        "overall": {"trades": 1, "wins": 1, "win_rate": "1", "net_pnl": "86.4", "gross_profit": "86.4",
                    "gross_loss": "0", "profit_factor": None, "average_pnl": "86.4", "best": "86.4",
                    "worst": "86.4", "costs": "2.6"},
        "max_drawdown": "0", "return_on_starting_balance": "0.00864", "longest_losing_streak": 0,
        "by_strategy_tag": [], "by_instrument": [], "open_positions": 1,
    },
    # Frames the DEMO stream replays in a loop, so the live-markets list moves (simulated).
    "stream_frames": [
        {"type": "quote", **fx_quote("EUR_USD", "1.08621", -4, 5, "major", "0.6")},
        {"type": "quote", **fx_quote("GBP_USD", "1.26411", -4, 5, "major", "0.6")},
        {"type": "quote", **fx_quote("USD_JPY", "149.881", -2, 3, "major", "0.6")},
        {"type": "quote", **fx_quote("EUR_USD", "1.08609", -4, 5, "major", "0.6")},
        {"type": "quote", **fx_quote("AUD_USD", "0.65518", -4, 5, "major", "0.6")},
    ],
})


print("wrote", sorted(p.name for p in OUT.glob("*.json")))
