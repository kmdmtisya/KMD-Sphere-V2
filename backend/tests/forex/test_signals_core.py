"""Signals without a database (P13-T06): every setup rule on hand-built indicator values,
illustrative levels on the right side of the entry, the published score (golden values), the
market condition and risk level, demotions and exclusions, and the wording guard: research
candidates, never advice, trade instructions or guarantees."""

import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.ai.orchestrator.guards import guarantee_problems
from app.modules.forex.analysis import indicators as ind
from app.modules.forex.analysis import patterns as pat
from app.modules.forex.analysis import structure as st
from app.modules.forex.calendar.risk import RiskWindow
from app.modules.forex.signals import ranking
from app.modules.forex.signals import scoring as sc
from app.modules.forex.signals import setups as su

D = Decimal
T0 = datetime(2026, 10, 7, 0, 0, tzinfo=UTC)
N = 80


SPREAD = D("0.0003")


def bars(closes: list[Decimal], spread: Decimal = SPREAD) -> su.Bars:
    ts = [T0 + timedelta(hours=k) for k in range(len(closes))]
    opens = [closes[0], *closes[:-1]]
    return su.Bars(
        ts,
        opens,
        [max(o, c) + spread for o, c in zip(opens, closes, strict=True)],
        [min(o, c) - spread for o, c in zip(opens, closes, strict=True)],
        closes,
    )


def rising(n: int = N, step: str = "0.0006") -> list[Decimal]:
    return [D("1.1000") + D(step) * k + (D("0.0002") if k % 3 == 0 else 0) for k in range(n)]


def falling(n: int = N) -> list[Decimal]:
    return [D("1.2000") - D("0.0006") * k - (D("0.0002") if k % 3 == 0 else 0) for k in range(n)]


def hand(**values: object) -> su.Context:
    """A context whose indicators are given by hand (last values matter), on flat bars at 1.1."""
    b = bars([D("1.1")] * N)
    none: list[Decimal | None] = [None] * N
    base: dict[str, object] = {
        "bars": b,
        "ema20": none,
        "ema50": none,
        "rsi": none,
        "atr": [D("0.001")] * N,
        "adx": ind.Adx(none, none, none),
        "macd": ind.Macd(none, none, none),
        "bollinger": ind.Bollinger(none, none, none, none),
        "swings": [],
        "levels": [],
        "breakouts": [],
        "patterns": [],
    }
    base.update(values)
    return su.Context(**base)  # type: ignore[arg-type]


def last(value: Decimal | None) -> list[Decimal | None]:
    return [None] * (N - 1) + [value]


# --------------------------------------------------------------------- setup rules (T06.1)
def test_trend_continuation_on_a_real_rising_series_and_its_mirror() -> None:
    up = su.detect(su.context(bars(rising())))
    trend = next(s for s in up if s.rule == "trend_continuation")
    assert trend.direction == "bullish" and trend.stop < trend.entry < trend.target
    assert trend.target - trend.entry == 2 * (trend.entry - trend.stop)
    assert trend.as_of == T0 + timedelta(hours=N - 1) and trend.version == su.RULE_VERSION
    down = su.detect(su.context(bars(falling())))
    mirror = next(s for s in down if s.rule == "trend_continuation")
    assert mirror.direction == "bearish" and mirror.target < mirror.entry < mirror.stop


def test_trend_needs_every_condition() -> None:
    ok = {
        "ema20": last(D("1.099")),
        "ema50": last(D("1.098")),
        "adx": ind.Adx(last(D(30)), last(D(10)), last(D(30))),
    }
    assert su.trend_continuation(hand(**ok)) is not None
    weak = {**ok, "adx": ind.Adx(last(D(30)), last(D(10)), last(D(24)))}
    assert su.trend_continuation(hand(**weak)) is None  # ADX below 25
    against = {**ok, "adx": ind.Adx(last(D(10)), last(D(30)), last(D(30)))}
    assert su.trend_continuation(hand(**against)) is None  # -DI above +DI
    assert su.trend_continuation(hand()) is None  # indicators undefined


def test_breakout_uses_a_recent_break_and_the_level_as_invalidation() -> None:
    ctx = hand(breakouts=[st.Breakout(N - 2, D("1.0995"), "up")])
    s = su.breakout(ctx)
    assert s is not None and s.direction == "bullish" and s.stop == D("1.0995") - D("0.0005")
    assert su.breakout(hand(breakouts=[st.Breakout(N - 5, D("1.0995"), "up")])) is None  # too old
    down = su.breakout(hand(breakouts=[st.Breakout(N - 1, D("1.1005"), "down")]))
    assert (
        down is not None and down.direction == "bearish" and down.stop == D("1.1005") + D("0.0005")
    )
    # A break whose level sits on the wrong side of the entry gives no setup.
    assert su.breakout(hand(breakouts=[st.Breakout(N - 1, D("1.2"), "up")])) is None


def test_reversal_needs_a_pattern_near_a_level() -> None:
    level = st.Level(D("1.0998"), 2, 10, 40, 42, (10, 40))
    above = st.Level(D("1.1050"), 2, 12, 44, 46, (12, 44))
    hit = pat.PatternHit("hammer", "reversal", "bullish", (N - 1,))
    s = su.reversal(hand(levels=[level, above], patterns=[hit]))
    assert s is not None and s.direction == "bullish" and s.target == D("1.1050")
    assert s.stop == D("1.1") - D("0.0003") - D("0.00025")  # the pattern's low - 0.25 ATR
    far = st.Level(D("1.0900"), 2, 10, 40, 42, (10, 40))
    assert su.reversal(hand(levels=[far], patterns=[hit])) is None  # not near a level
    assert su.reversal(hand(levels=[level], patterns=[])) is None


def test_range_mean_reversion_and_momentum() -> None:
    # Close 1.1 sits at %b 0.067 between the bands 1.0998 and 1.1028.
    band = ind.Bollinger(last(D("1.1028")), last(D("1.1013")), last(D("1.0998")), last(D("0.003")))
    ranged = su.range_setup(
        hand(adx=ind.Adx(last(D(10)), last(D(10)), last(D(15))), bollinger=band)
    )
    assert ranged is not None and ranged.direction == "bullish" and ranged.target == D("1.1013")
    trending = su.range_setup(
        hand(adx=ind.Adx(last(D(10)), last(D(10)), last(D(25))), bollinger=band)
    )
    assert trending is None  # ADX 20 or more is not a range
    below = ind.Bollinger(last(D("1.1100")), last(D("1.1050")), last(D("1.1010")), last(D("0.01")))
    mr = su.mean_reversion(hand(rsi=last(D(25)), bollinger=below))
    assert mr is not None and mr.direction == "bullish" and mr.target == D("1.1050")
    assert su.mean_reversion(hand(rsi=last(D(35)), bollinger=below)) is None
    hist = [None] * (N - 3) + [D("0.0001"), D("0.0002"), D("0.0003")]
    mom = su.momentum(hand(rsi=last(D(60)), macd=ind.Macd(last(None), last(None), hist)))
    assert mom is not None and mom.direction == "bullish"
    flat_hist = [None] * (N - 3) + [D("0.0003"), D("0.0002"), D("0.0003")]
    assert (
        su.momentum(hand(rsi=last(D(60)), macd=ind.Macd(last(None), last(None), flat_hist))) is None
    )
    assert su.momentum(hand(rsi=last(D(75)), macd=ind.Macd(last(None), last(None), hist))) is None


def test_too_few_bars_are_refused() -> None:
    with pytest.raises(ValueError):
        su.context(bars(rising(30)))


# ----------------------------------------------------------------------- score (T06.2)
def test_weights_are_validated() -> None:
    sc.validate_weights(sc.DEFAULT_WEIGHTS)
    with pytest.raises(ValueError):
        sc.validate_weights({**sc.DEFAULT_WEIGHTS, "macro_event_risk": D("0.1")})
    with pytest.raises(ValueError):
        sc.validate_weights({**sc.DEFAULT_WEIGHTS, "liquidity": D("0.2")})  # positives sum to 1.1
    without = dict(sc.DEFAULT_WEIGHTS)
    without.pop("liquidity")
    with pytest.raises(ValueError):
        sc.validate_weights(without)


def test_golden_scores() -> None:
    w = sc.DEFAULT_WEIGHTS
    every_one = [sc.Factor(k, D(1), w[k], "") for k in sc.COMPONENTS if k != "macro_event_risk"]
    assert sc.score(
        [*every_one, sc.Factor("macro_event_risk", D(0), w["macro_event_risk"], "")]
    ) == D("100.0")
    assert sc.score(
        [*every_one, sc.Factor("macro_event_risk", D(1), w["macro_event_risk"], "")]
    ) == D("80.0")
    half = [sc.Factor(k, D("0.5"), w[k], "") for k in sc.COMPONENTS if k != "macro_event_risk"]
    assert sc.score(half) == D("50.0")
    assert sc.score([sc.Factor("macro_event_risk", D(1), w["macro_event_risk"], "")]) == D(
        "0.0"
    )  # clipped
    mixed = [
        sc.Factor("trend_strength", D("0.6"), w["trend_strength"], ""),
        sc.Factor("risk_reward", D("0.6667"), w["risk_reward"], ""),
    ]
    assert sc.score(mixed) == D("19.0")  # 100 x (0.09 + 0.100005), half up


def test_market_condition_priority() -> None:
    assert sc.condition(D(40), D(30), D(1), D(0), D("1.6")) == "high_volatility"
    assert sc.condition(D(30), D(20), D(1), D(0), D(1)) == "trending"
    assert sc.condition(D(22), D(20), D(2), D(1), D(1)) == "momentum_strengthening"
    assert sc.condition(D(15), D(16), D(1), D(2), D(1)) == "consolidating"
    assert sc.condition(D(22), D(23), D(1), D(2), D(1)) == "mixed"
    assert sc.condition(None, None, None, None, None) == "mixed"


@pytest.mark.parametrize(
    ("ratio", "spread", "penalty", "level"),
    [
        (D(1), D("0.05"), D(0), "low"),
        (D("1.3"), D("0.05"), D(0), "medium"),
        (D(1), None, D("0.5"), "medium_high"),
        (D("1.6"), D("0.05"), D(0), "medium_high"),
        (D("1.6"), D("0.2"), D(1), "high"),
    ],
)
def test_risk_level(ratio: Decimal, spread: Decimal | None, penalty: Decimal, level: str) -> None:
    assert sc.risk_level(ratio, spread, penalty) == level


# --------------------------------------------------------------- ranking (T06.3, T06.4)
NOW = T0 + timedelta(hours=N)  # the last bar closed right now


def pair(**overrides: object) -> ranking.PairInput:
    values: dict[str, object] = {
        "instrument": "EUR_USD",
        "pip_location": -4,
        "display_precision": 5,
        "liquidity_tier": "major",
        "bars": bars(rising()),
        "bar_step": timedelta(hours=1),
        "data_types": ["simulated"],
        "spread": D("0.00012"),
        "quote_age": timedelta(seconds=5),
        "windows": [],
        "forecast": None,
        "now": NOW,
    }
    values.update(overrides)
    return ranking.PairInput(**values)  # type: ignore[arg-type]


def test_every_candidate_explains_every_factor_and_its_contribution() -> None:
    found = ranking.candidates(pair(), sc.DEFAULT_WEIGHTS)
    assert found and found == sorted(found, key=lambda c: (-c.score, c.setup.rule))
    c = found[0]
    assert [f.name for f in c.factors] == list(sc.COMPONENTS)
    assert sc.score(c.factors) == c.score  # nothing hidden: the factors give the score
    hist = next(f for f in c.factors if f.name == "strategy_history")
    assert hist.value == 0 and "no out-of-sample backtest" in hist.detail
    assert c.spread_pips == D("1.2") and c.levels_pips["risk_reward"] > 0
    assert c.adjustments == [] and c.excluded is False
    assert any("simulated" in r for r in c.risks) and len(c.assumptions) == 3


def test_strategy_history_counts_only_with_enough_out_of_sample_trades() -> None:
    def hist(history: dict[str, ranking.StrategyHistory]) -> list[sc.Factor]:
        base = ranking.candidates(pair(), sc.DEFAULT_WEIGHTS)[0]
        found = ranking.candidates(pair(history=history), sc.DEFAULT_WEIGHTS)
        same = next(c for c in found if c.setup.rule == base.setup.rule)
        return [f for f in same.factors if f.name == "strategy_history"]

    rule = ranking.candidates(pair(), sc.DEFAULT_WEIGHTS)[0].setup.rule
    few = hist({rule: ranking.StrategyHistory(12, D("2.5"), ("simulated",))})[0]
    assert few.value == 0 and "fewer than 30" in few.detail and "simulated" in few.detail
    good = hist({rule: ranking.StrategyHistory(40, D("1.6"), ("simulated",))})[0]
    assert good.value == D("0.6") and "profit factor 1.6 over 40" in good.detail
    capped = hist({rule: ranking.StrategyHistory(40, D("3.1"), ())})[0]
    assert capped.value == 1
    poor = hist({rule: ranking.StrategyHistory(40, D("0.8"), ())})[0]
    assert poor.value == 0
    flawless = hist({rule: ranking.StrategyHistory(35, None, ())})[0]
    assert flawless.value == 1 and "no losing trade" in flawless.detail
    other = hist({"no_such_rule": ranking.StrategyHistory(40, D(2), ())})[0]
    assert other.value == 0


def test_demotions_and_exclusions_say_why() -> None:
    base = ranking.candidates(pair(), sc.DEFAULT_WEIGHTS)[0]
    window = RiskWindow(
        "Release",
        ("USD",),
        "high",
        NOW + timedelta(minutes=20),
        NOW - timedelta(minutes=10),
        NOW + timedelta(minutes=80),
    )
    evented = ranking.candidates(pair(windows=[window]), sc.DEFAULT_WEIGHTS)[0]
    assert any("demoted x 0.5" in a for a in evented.adjustments) and evented.score < base.score
    assert next(f for f in evented.factors if f.name == "macro_event_risk").value == 1
    no_quote = ranking.candidates(pair(spread=None, quote_age=None), sc.DEFAULT_WEIGHTS)[0]
    assert any("x 0.75" in a for a in no_quote.adjustments) and no_quote.spread_pips is None
    assert next(f for f in no_quote.factors if f.name == "spread_and_cost").value == 0
    stale = ranking.candidates(pair(now=NOW + timedelta(hours=5)), sc.DEFAULT_WEIGHTS)[0]
    assert stale.excluded and any("excluded" in a for a in stale.adjustments)
    ranked, excluded = ranking.rank([[stale], [base]])
    assert ranked == [base] and excluded == [stale]


def test_forecasts_count_only_when_calibrated_and_agreeing() -> None:
    def fc(p: str, calibrated: bool) -> ranking.ForecastInput:
        return ranking.ForecastInput("4h", D(p), calibrated, "abcd", "lightgbm")

    def value(f: ranking.ForecastInput) -> Decimal:
        c = next(
            x
            for x in ranking.candidates(pair(forecast=f), sc.DEFAULT_WEIGHTS)
            if x.setup.direction == "bullish"
        )
        return next(x for x in c.factors if x.name == "forecast_calibration").value

    assert value(fc("0.70", True)) == D("0.4")
    assert value(fc("0.30", True)) == 0  # disagrees with a bullish setup
    assert value(fc("0.70", False)) == 0  # requires calibration: not used
    c = ranking.candidates(pair(forecast=fc("0.70", False)), sc.DEFAULT_WEIGHTS)[0]
    assert (
        "requires calibration"
        in next(x for x in c.factors if x.name == "forecast_calibration").detail
    )


def test_golden_candidate_is_reproducible() -> None:
    a = ranking.candidates(pair(), sc.DEFAULT_WEIGHTS)
    b = ranking.candidates(pair(), sc.DEFAULT_WEIGHTS)
    assert [(c.setup.rule, c.score) for c in a] == [(c.setup.rule, c.score) for c in b]
    assert ranking.candidates(pair(bars=bars([D("1.1")] * N)), sc.DEFAULT_WEIGHTS) == []


def test_ties_rank_by_pair() -> None:
    c = ranking.candidates(pair(), sc.DEFAULT_WEIGHTS)[0]
    other = replace(c, instrument="AUD_USD")
    ranked, _ = ranking.rank([[c], [other]])
    assert [x.instrument for x in ranked] == ["AUD_USD", "EUR_USD"]


# ---------------------------------------------------------------------- wording guard
TRADE_WORDS = re.compile(r"\b(buy|sell|will|guarantee\w*|certain|sure)\b", re.IGNORECASE)


def test_no_text_is_advice_an_instruction_or_a_guarantee() -> None:
    window = RiskWindow(
        "Release", ("USD",), "high", NOW, NOW - timedelta(minutes=30), NOW + timedelta(minutes=60)
    )
    texts: list[str] = []
    for p in (
        pair(),
        pair(windows=[window]),
        pair(spread=None, quote_age=None),
        pair(bars=bars(falling())),
    ):
        for c in ranking.candidates(p, sc.DEFAULT_WEIGHTS):
            texts += (
                c.assumptions
                + c.risks
                + c.adjustments
                + c.setup.evidence
                + [f.detail for f in c.factors]
            )
    assert texts
    assert guarantee_problems(texts, forecast_used=True) == []
    for t in texts:
        assert not TRADE_WORDS.search(t), t
