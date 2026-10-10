"""The DTO mapping (P05-T10) stays true: every API field it names exists in openapi.json, every
DTO key exists in the Dart source, every difference has a resolution and a real owning task,
and the generated Markdown is current."""

import importlib.util
import json
import re
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAPPING = json.loads((ROOT / "docs" / "contracts" / "dto-mapping.json").read_text("utf-8"))
SPEC = json.loads((ROOT / "backend" / "openapi.json").read_text("utf-8"))
PLAN = (ROOT / "EXECUTION_PLAN.md").read_text("utf-8")
MOBILE = ROOT / "mobile" / "wealthsphere_app"
STATUSES = {"same", "renamed", "dto-only", "api-only"}


def _schema(name: str) -> dict[str, Any]:
    schemas = SPEC["components"]["schemas"]
    assert name in schemas, f"no schema {name} in openapi.json"
    return schemas[name]  # type: ignore[no-any-return]


def _resolve(schema: dict[str, Any]) -> dict[str, Any]:
    """Follows $ref, including `anyOf: [$ref, null]` for nullable objects."""
    if "$ref" in schema:
        return _schema(schema["$ref"].rsplit("/", 1)[-1])
    for option in schema.get("anyOf", []):
        if "$ref" in option:
            return _schema(option["$ref"].rsplit("/", 1)[-1])
    return schema


def _has_field(schema_name: str, path: str) -> bool:
    schema = _schema(schema_name)
    for part in path.split("."):
        properties = _resolve(schema).get("properties", {})
        if part not in properties:
            return False
        schema = properties[part]
    return True


def _dart_keys(dart: str) -> set[str]:
    source = (MOBILE / dart).read_text("utf-8")
    return set(re.findall(r"'([a-z][a-z0-9_]*)'", source))


def _read_by(dart: str, dto: str) -> set[str]:
    """The JSON keys one Dart class reads through its JsonReader (`r.string('key')`, ...)."""
    source = (MOBILE / dart).read_text("utf-8")
    match = re.search(rf"^class {dto}\b(.*?)(?=^class |\Z)", source, re.M | re.S)
    assert match, f"no class {dto} in {dart}"
    return set(re.findall(r"\br\.\w+\(\s*'([a-z][a-z0-9_]*)'", match.group(1)))


def _task_exists(task: str) -> bool:
    return f"#### {task} " in PLAN


@pytest.mark.parametrize("entry", MAPPING["live"], ids=lambda e: e["dto"])
def test_live_mappings_match_the_api_and_the_dart_dtos(entry: dict[str, Any]) -> None:
    keys = _dart_keys(entry["dart"])
    method, path = entry["api"].split(" ", 1)
    assert method.lower() in SPEC["paths"].get(path, {}), f"{entry['api']} not in openapi.json"
    for f in entry["fields"]:
        assert f["status"] in STATUSES, f
        if f["api"]:
            assert _has_field(entry["schema"], f["api"]), f"{entry['schema']} has no {f['api']}"
        if f["dto"]:
            assert f["dto"] in keys, f"{entry['dart']} does not read {f['dto']}"
        if f["status"] != "same" or f.get("resolution"):
            assert f.get("resolution") and f.get("owner"), f"{f}: needs a resolution and owner"
        if f.get("owner"):
            assert _task_exists(f["owner"]), f"{f['owner']} is not a task in EXECUTION_PLAN.md"
        if f["status"] == "same":
            assert f["api"] == f["dto"], f
        if f["status"] == "dto-only":
            assert f["api"] is None, f
        if f["status"] == "api-only":
            assert f["dto"] is None, f


@pytest.mark.parametrize("entry", MAPPING["live"], ids=lambda e: e["dto"])
def test_every_key_a_live_dto_reads_is_mapped(entry: dict[str, Any]) -> None:
    """A field added to (or removed from) a live DTO must be added to (or removed from) the
    mapping too."""
    mapped = {f["dto"] for f in entry["fields"] if f["dto"]}
    assert _read_by(entry["dart"], entry["dto"]) == mapped


@pytest.mark.parametrize("entry", MAPPING["pending"], ids=lambda e: e["dto"])
def test_pending_mappings_name_real_keys_and_tasks(entry: dict[str, Any]) -> None:
    keys = _dart_keys(entry["dart"])
    assert set(entry["keys"]) <= keys, f"{entry['dto']}: {set(entry['keys']) - keys} not in Dart"
    assert _task_exists(entry["owner"]), entry["owner"]
    assert entry["resolution"]


def test_the_markdown_is_generated_from_the_json() -> None:
    spec = importlib.util.spec_from_file_location(
        "dto_mapping", ROOT / "scripts" / "dto_mapping.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    committed = (ROOT / "docs" / "contracts" / "dto-mapping.md").read_text("utf-8")
    assert committed == module.render(MAPPING), "run: python scripts/dto_mapping.py"
