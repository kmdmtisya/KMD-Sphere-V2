"""Rules for the analysis layer (P13-T03): no language model touches an indicator value or a
pattern, the indicator request parser is bounded, and the candle sync is scheduled."""

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.errors import InvalidValueError
from app.modules.forex.analysis import registry
from app.worker.schedule import build_schedule

APP = Path(__file__).resolve().parents[2] / "app"
FOREX = APP / "modules" / "forex"
ANALYSIS_PACKAGES = [FOREX / "analysis", FOREX / "candles"]
FORBIDDEN_PREFIXES = ("app.ai", "openai", "anthropic")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
        elif isinstance(node, ast.Import):
            found.extend(a.name for a in node.names)
    return found


def test_no_analysis_code_imports_the_ai_layer_or_a_model_client() -> None:
    files = [p for pkg in ANALYSIS_PACKAGES for p in pkg.rglob("*.py")]
    assert len(files) >= 8
    for path in files:
        for module in _imports(path):
            assert not module.startswith(FORBIDDEN_PREFIXES), f"{path.name} imports {module}"


def test_no_ai_tool_can_produce_or_edit_an_indicator_yet() -> None:
    """The AI tool layer has no forex analysis tool. The Forex Copilot (P13-T10) may only read
    results through allow-listed, authorised tools, never compute or edit them."""
    from app.ai.tools.base import ALLOWED_TOOLS

    for name in ALLOWED_TOOLS:
        assert not any(
            w in name for w in ("indicator", "candle", "forex", "pattern", "structure")
        ), name


def test_the_candle_sync_job_is_scheduled_every_five_minutes() -> None:
    entry = build_schedule()["forex-candle-sync"]
    assert entry["task"] == "app.worker.tasks.forex_candle_sync"
    assert "*/5" in repr(entry["schedule"]) or "5" in repr(entry["schedule"])


# ----------------------------------------------------------------------------- parser
def test_specs_parse_with_defaults_and_explicit_parameters() -> None:
    assert registry.parse("rsi").label == "rsi:14"
    assert registry.parse("macd").label == "macd:12,26,9"
    r = registry.parse("bollinger:20,2.5")
    assert r.label == "bollinger:20,2.5" and r.params == (Decimal(20), Decimal("2.5"))
    assert registry.parse("sma:20").warmup() == 19
    assert registry.parse("rsi:14").warmup() == 14
    assert registry.parse("macd:12,26,9").warmup() == 25
    assert registry.parse("adx:14").warmup() == 14
    assert registry.parse("stochastic").warmup() == 13


def test_every_spec_runs_on_a_short_series_and_matches_its_declared_outputs() -> None:
    d = [Decimal(1) + Decimal(i % 7) / 10 for i in range(60)]
    bars = registry.Bars([v + Decimal("0.05") for v in d], [v - Decimal("0.05") for v in d], d)
    for name, spec in registry.SPECS.items():
        out = registry.compute(registry.parse(name), bars)
        assert tuple(out) == spec.outputs, name
        assert all(len(v) == 60 for v in out.values()), name


@pytest.mark.parametrize(
    "text",
    [
        "",
        "unknown",
        "sma:0",
        "sma:501",
        "sma:1.5",
        "sma:abc",
        "sma:1,2",
        "macd:26,12,9",
        "macd:12,26",
        "bollinger:20,0",
        "bollinger:20,11",
        "bollinger:20,NaN",
        "rsi:Infinity",
        "stochastic:14,3",
    ],
)
def test_bad_specs_are_refused(text: str) -> None:
    with pytest.raises(InvalidValueError):
        registry.parse(text)


def test_parse_all_deduplicates_and_limits() -> None:
    assert [r.label for r in registry.parse_all(["sma:5", "sma:5", "rsi"])] == ["sma:5", "rsi:14"]
    with pytest.raises(InvalidValueError):
        registry.parse_all([])
    with pytest.raises(InvalidValueError):
        registry.parse_all([f"sma:{n}" for n in range(2, 20)])
