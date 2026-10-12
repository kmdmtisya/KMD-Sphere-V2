"""All consumers use the provider interface only (P08-T02 acceptance).

Code outside the providers package may import the interface (`base`), the value types (`models`),
the errors, the resilience wrappers and the registry that composes providers. It must never import
a vendor adapter or the fake: those are wired in at one composition point (`providers/registry.py`).
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
PACKAGE = APP / "modules" / "market_data" / "providers"
ROOT = "app.modules.market_data.providers"
# `registry` is the one place that names vendors; consumers ask it for MarketProviders.
# `batch` is the vendor-free helper that asks a provider for several FX quotes at once.
CONSUMER_SAFE = {"base", "models", "errors", "resilience", "registry", "batch"}
# Modules that are allowed to import concrete providers (composition points).
COMPOSITION = {PACKAGE / "registry.py"}


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
            if node.module == ROOT:
                found.extend(f"{ROOT}.{alias.name}" for alias in node.names)
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
    return found


def test_consumers_import_only_the_interface_modules() -> None:
    offenders: list[str] = []
    for path in APP.rglob("*.py"):
        if PACKAGE in path.parents or path in COMPOSITION:
            continue
        for module in _imports(path):
            if module.startswith(ROOT + "."):
                leaf = module.removeprefix(ROOT + ".").split(".")[0]
                if leaf not in CONSUMER_SAFE:
                    offenders.append(f"{path.relative_to(APP)} imports {module}")
    assert offenders == []


def test_the_guard_sees_a_bad_import(tmp_path: Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text(f"from {ROOT}.fake import FakeProvider\nfrom {ROOT} import fake\n")
    seen = _imports(bad)
    assert f"{ROOT}.fake" in seen


def test_the_interface_modules_have_no_vendor_imports() -> None:
    for name in CONSUMER_SAFE - {"registry"}:
        for module in _imports(PACKAGE / f"{name}.py"):
            assert not module.startswith(f"{ROOT}.fake"), name


def test_the_interface_modules_use_no_floats_for_money() -> None:
    # Money-bearing models are Decimal-only (ADR-0003): no `float` annotations.
    for name in ("models", "base"):
        tree = ast.parse((PACKAGE / f"{name}.py").read_text(encoding="utf-8"))
        floats = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "float"]
        assert floats == [], name
