"""The evaluation datasets themselves (P10-T09.5): approved sizes, valid content, and committed
files identical to what the builder produces."""

import json
from pathlib import Path

import pytest

from app.ai.tools.base import ALLOWED_TOOLS
from app.ai.tools.factory import build_tool_registry
from app.core.config import Settings
from tests.ai_eval import build_datasets
from tests.ai_eval.harness import THRESHOLDS, load

pytestmark = pytest.mark.security


@pytest.mark.parametrize("name", sorted(THRESHOLDS))
def test_each_dataset_meets_its_approved_minimum_size_and_has_unique_ids(name: str) -> None:
    rows = load(name)
    assert len(rows) >= THRESHOLDS[name].minimum_size
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)) and all(i.startswith(f"{name}-") for i in ids)


def test_the_committed_datasets_are_what_the_builder_produces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(build_datasets, "DATASETS", tmp_path)
    build_datasets.main()
    for name in THRESHOLDS:
        built = (tmp_path / f"{name}.jsonl").read_text(encoding="utf-8")
        committed = (Path(__file__).parent / "datasets" / f"{name}.jsonl").read_text(
            encoding="utf-8"
        )
        assert built == committed, (
            f"{name}.jsonl is stale: run python -m tests.ai_eval.build_datasets"
        )


def test_the_routing_dataset_only_names_tools_that_exist_and_covers_every_one_it_can() -> None:
    rows = load("routing")
    registered = {s.name for s in build_tool_registry(Settings()).specs()}
    used: set[str] = set()
    for row in rows:
        assert set(row["expected_tools"]) <= registered <= ALLOWED_TOOLS, row["id"]
        assert row["expected_tools"] == sorted(row["expected_tools"])
        used |= set(row["expected_tools"])
    assert used == registered, f"no routing case for {sorted(registered - used)}"
    kinds = {r["kind"] for r in rows}
    assert {
        "portfolio",
        "allocation",
        "performance",
        "net_worth",
        "goal",
        "forecast",
        "multi",
        "ambiguous",
        "out_of_scope",
    } <= kinds
    assert all(
        r["expected_tools"] == [] for r in rows if r["kind"] in ("ambiguous", "out_of_scope")
    )


def test_every_row_is_one_line_of_valid_json_and_the_files_end_with_a_newline() -> None:
    for name in THRESHOLDS:
        text = (Path(__file__).parent / "datasets" / f"{name}.jsonl").read_text(encoding="utf-8")
        assert text.endswith("\n") and "\r" not in text
        for line in text.splitlines():
            json.loads(line)


def test_the_attack_and_payload_lists_cover_every_attack_kind() -> None:
    rows = load("injection")
    assert {r["vector"] for r in rows} == {"user_text", "portfolio_name", "goal_name"}
    assert {r["attack"] for r in rows} == set(range(len(build_datasets.ATTACKS)))
    cross = {r["case"] for r in load("cross_user")}
    assert {
        "scope_foreign_portfolio",
        "tool_foreign_id",
        "foreign_conversation",
        "smuggled_identity",
        "indirect_by_name",
    } <= cross
