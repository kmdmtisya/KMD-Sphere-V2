import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "coverage_by_module.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("coverage_by_module", SCRIPT)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


def _xml(tmp_path: Path, files: dict[str, tuple[int, int]]) -> Path:
    """files: filename -> (total lines, covered lines)"""
    classes = []
    for filename, (total, covered) in files.items():
        lines = "".join(
            f'<line number="{i}" hits="{1 if i <= covered else 0}"/>' for i in range(1, total + 1)
        )
        classes.append(f'<class filename="{filename}"><lines>{lines}</lines></class>')
    path = tmp_path / "coverage.xml"
    body = "".join(classes)
    path.write_text(
        f'<coverage><packages><package name="p"><classes>{body}</classes>'
        "</package></packages></coverage>",
        encoding="utf-8",
    )
    return path


def _policy(tmp_path: Path, critical: list[str], threshold: int = 85) -> Path:
    path = tmp_path / "policy.toml"
    items = ", ".join(f'"{c}"' for c in critical)
    path.write_text(f"threshold = {threshold}\ncritical = [{items}]\n", encoding="utf-8")
    return path


def _run(xml: Path, policy: Path, summary: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPT), str(xml), "--policy", str(policy)]
    if summary:
        cmd += ["--summary", str(summary)]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603


def test_module_grouping() -> None:
    m = _load()
    assert m.module_of("core/redaction.py") == "core"
    assert m.module_of("app/core/redaction.py") == "core"
    assert m.module_of("app\\api\\health.py") == "api"
    assert m.module_of("modules/forecasting/engine.py") == "modules/forecasting"
    assert m.module_of("app/modules/goals/service.py") == "modules/goals"
    assert m.module_of("main.py") == "(app root)"


def test_collect_merges_files_per_module(tmp_path: Path) -> None:
    m = _load()
    xml = _xml(tmp_path, {"core/a.py": (10, 10), "core/b.py": (10, 5), "api/c.py": (4, 4)})
    modules = m.collect(xml)
    assert modules["core"].lines == 20
    assert modules["core"].covered == 15
    assert round(modules["core"].percent, 1) == 75.0
    assert modules["api"].percent == 100.0


def test_critical_module_below_threshold_fails(tmp_path: Path) -> None:
    xml = _xml(tmp_path, {"modules/forecasting/engine.py": (100, 80), "core/a.py": (10, 10)})
    result = _run(xml, _policy(tmp_path, ["modules/forecasting"]))
    assert result.returncode == 1
    assert "modules/forecasting: 80.0% < 85%" in result.stdout


def test_critical_module_at_threshold_passes(tmp_path: Path) -> None:
    xml = _xml(tmp_path, {"modules/forecasting/engine.py": (100, 85)})
    result = _run(xml, _policy(tmp_path, ["modules/forecasting"]))
    assert result.returncode == 0
    assert "Policy: OK" in result.stdout


def test_missing_critical_modules_are_reported_not_failed(tmp_path: Path) -> None:
    xml = _xml(tmp_path, {"core/a.py": (10, 1)})  # low coverage, but not a critical module
    result = _run(xml, _policy(tmp_path, ["modules/analytics"]))
    assert result.returncode == 0
    assert "not yet present" in result.stdout
    assert "modules/analytics" in result.stdout


def test_summary_file_receives_the_table(tmp_path: Path) -> None:
    xml = _xml(tmp_path, {"core/a.py": (10, 9)})
    summary = tmp_path / "summary.md"
    _run(xml, _policy(tmp_path, []), summary)
    text = summary.read_text(encoding="utf-8")
    assert "Backend coverage by module" in text
    assert "`core`" in text


def test_the_real_policy_file_is_valid_and_lists_modules() -> None:
    import tomllib

    policy = tomllib.loads((ROOT / "backend" / "coverage-policy.toml").read_text(encoding="utf-8"))
    assert policy["threshold"] >= 85
    assert "modules/forecasting" in policy["critical"]
    assert len(set(policy["critical"])) == len(policy["critical"])
