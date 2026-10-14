"""QG-03.4: every financial method and edge case maps to real tests, and every public function of
the financial modules is covered by a requirement. The matrix is
docs/contracts/financial-test-matrix.json (rendered to docs/financial-test-matrix.md)."""

import ast
import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
MATRIX = json.loads((ROOT / "docs" / "contracts" / "financial-test-matrix.json").read_text("utf-8"))
ROWS: list[dict[str, Any]] = MATRIX["requirements"]
METHODS = (ROOT / "docs" / "financial-methods.md").read_text("utf-8")

# The modules whose public functions produce financial figures.
FINANCIAL_MODULES = [
    "core.money",
    "modules.forecasting.engine",
    "modules.goals.progress",
    "modules.analytics.performance",
    "modules.analytics.allocation",
    "modules.analytics.risk",
    "modules.networth.income",
    "modules.networth.networth",
    "modules.portfolio.history",
    "modules.portfolio.assumed",
    "modules.portfolio.summary",
    "modules.transactions.holdings",
    "modules.market_data.fx",
    "modules.doctor.rules",
    "modules.scoring.features",
    "modules.scoring.scoring",
    "modules.compatibility.impact",
    "modules.forex.analysis.indicators",
    "modules.forex.analysis.structure",
    "modules.forex.analysis.patterns",
    "modules.forex.candles.sessions",
    "modules.forex.candles.aggregate",
    "modules.forex.signals.scoring",
    "modules.forex.signals.setups",
    "modules.forex.signals.ranking",
]
# Sections of financial-methods.md that state formulas (1 to 12): each needs a requirement.
FORMULA_SECTIONS = range(1, 13)


def _functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text("utf-8"))
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}


def _public(module: str) -> set[str]:
    tree = ast.parse((BACKEND / "app" / (module.replace(".", "/") + ".py")).read_text("utf-8"))
    return {
        f"{module.removeprefix('modules.')}.{n.name}"
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")
    }


def test_requirement_ids_are_unique_and_complete() -> None:
    ids = [r["id"] for r in ROWS]
    assert len(ids) == len(set(ids))
    for r in ROWS:
        assert re.fullmatch(r"[A-Z]-\d\d", r["id"]), r["id"]
        assert r["text"].strip() and r["tests"], f"{r['id']} needs text and at least one test"
        assert len(r["tests"]) == len(set(r["tests"])), f"{r['id']} lists a test twice"


@pytest.mark.parametrize("row", ROWS, ids=[r["id"] for r in ROWS])
def test_every_listed_test_exists(row: dict[str, Any]) -> None:
    for ref in row["tests"]:
        file, _, name = ref.partition("::")
        path = BACKEND / file
        assert path.is_file(), f"{row['id']}: no file {file}"
        assert name in _functions(path), f"{row['id']}: no test {name} in {file}"
        assert name.startswith("test_"), ref


def test_every_formula_section_has_requirements() -> None:
    headings = {int(m.group(1)) for m in re.finditer(r"^## (\d+)\. ", METHODS, re.M)}
    sections = {r["section"] for r in ROWS}
    assert sections <= headings, f"sections not in financial-methods.md: {sections - headings}"
    missing = [s for s in FORMULA_SECTIONS if s not in sections]
    assert not missing, f"formula sections without a requirement: {missing}"


def test_every_public_function_of_the_financial_modules_is_covered() -> None:
    public = set().union(*(_public(m) for m in FINANCIAL_MODULES))
    covered = {c for r in ROWS for c in r["covers"]}
    assert not public - covered, f"functions covered by no requirement: {sorted(public - covered)}"
    assert not covered - public, f"covers names a function that does not exist: {covered - public}"


def test_the_markdown_is_generated_from_the_json() -> None:
    spec = importlib.util.spec_from_file_location(
        "test_matrix", ROOT / "scripts" / "test_matrix.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    committed = (ROOT / "docs" / "financial-test-matrix.md").read_text("utf-8")
    assert committed == module.render(MATRIX), "run: python scripts/test_matrix.py"


def test_the_checker_catches_what_it_should() -> None:
    """The checks above are not vacuous: a missing test or an uncovered function is found."""
    assert "test_no_such_thing" not in _functions(BACKEND / "tests" / "test_money.py")
    assert "core.money.round_half_up" in _public("core.money")
    assert "core.money._parse" not in _public("core.money")  # private helpers are not required
