"""The committed backend/openapi.json is the API contract. These tests fail when the application
and the contract drift apart, and enforce conventions from docs/api-conventions.md."""

import importlib.util
import json
import re
from pathlib import Path
from types import ModuleType
from typing import Any

from app.main import create_app
from tests.conftest import make_settings

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "backend" / "openapi.json"
_MONEY_NAME = re.compile(
    r"^(amount|balance|price|quantity|rate|value|fee|fees|tax|taxes|net_worth|principal"
    r"|contribution|income)$|_(amount|balance|price|quantity|rate|value|fee|fees|tax|taxes|net_worth)$",
    re.IGNORECASE,
)


def _exporter() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "export_openapi", ROOT / "scripts" / "export_openapi.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _spec() -> dict[str, Any]:
    app = create_app(make_settings(), readiness_checks={})
    spec: dict[str, Any] = app.openapi()
    return spec


def test_committed_contract_matches_the_application() -> None:
    generated = _exporter().generate()
    committed = CONTRACT.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert committed == generated, (
        "backend/openapi.json is stale. Regenerate: cd backend && "
        "uv run python ../scripts/export_openapi.py"
    )


def test_export_is_deterministic() -> None:
    exporter = _exporter()
    assert exporter.generate() == exporter.generate()


def test_contract_is_valid_json_with_openapi_31() -> None:
    spec = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert spec["openapi"].startswith("3.1")
    assert spec["info"]["title"] == "WealthSphere API"


def test_paths_are_versioned_or_health() -> None:
    for path in _spec()["paths"]:
        assert path.startswith(("/api/v1/", "/health/")), path


def test_operation_ids_are_unique_and_every_operation_has_a_summary() -> None:
    seen: set[str] = set()
    for path, item in _spec()["paths"].items():
        for method, op in item.items():
            assert op.get("summary"), f"{method.upper()} {path} has no summary"
            op_id = op["operationId"]
            assert op_id not in seen, f"duplicate operationId {op_id}"
            seen.add(op_id)


def test_money_like_fields_are_strings_never_numbers() -> None:
    def walk(node: Any, trail: str) -> None:
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict):
                for name, schema in props.items():
                    if _MONEY_NAME.search(name) and isinstance(schema, dict):
                        assert schema.get("type") not in ("number", "integer"), (
                            f"{trail}.{name} must be a string (ADR-0003)"
                        )
            for key, value in node.items():
                walk(value, f"{trail}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{trail}[{i}]")

    walk(_spec(), "$")


def test_internal_endpoints_are_not_in_the_public_contract() -> None:
    assert "/metrics" not in _spec()["paths"]
