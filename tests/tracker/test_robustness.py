"""Robustness: line endings, missing files, utility functions and the real tracking files."""

import re
import subprocess
import sys
from types import ModuleType

import pytest
from conftest import ISO_TZ, REPO, TRACK, Workspace

FILES = ("TASK_CHECKLIST.md", "QUALITY_GATES.md", "PROGRESS_DASHBOARD.md", "EXECUTION_LOG.md")


def test_crlf_checkouts_are_read_correctly_and_rewritten_as_lf(ws: Workspace) -> None:
    for name in FILES:
        ws.write(name, ws.read(name).replace("\n", "\r\n"))
    assert "OK" in ws.ok("validate")
    ws.ok("status")
    ws.ok("start", "P00-T01")
    assert "`IN_PROGRESS`" in ws.task_block("P00-T01")
    for name in FILES:
        assert b"\r\n" not in (ws.root / name).read_bytes(), name


def test_deleting_the_register_does_not_switch_gate_enforcement_off(ws: Workspace) -> None:
    (ws.root / "QUALITY_GATES.md").unlink()
    out = ws.fail("validate")
    assert "QUALITY_GATES.md is missing but tasks reference quality gates" in out
    ws.ok("start", "P00-T01")  # tasks without gates still work
    ws.ok("check", "P00-T01.1", "P00-T01.2")
    ws.ok("complete", "P00-T01", "--evidence", "e")
    ws.ok("start", "P00-T02")
    ws.ok("check", "P00-T02.1")
    ws.ok("verify", "P00-T02", "--evidence", "v")
    ws.ok("complete", "P00-T02", "--evidence", "c", "--approved-by", "t")
    out = ws.fail("start", "P00-GATE")  # carries Gates-done: cannot be verified without the register
    assert "QUALITY_GATES.md is missing" in out
    assert "`NOT_STARTED`" in ws.task_block("P00-GATE")


def test_qg_commands_fail_clearly_without_a_register(ws: Workspace) -> None:
    (ws.root / "QUALITY_GATES.md").unlink()
    assert "QUALITY_GATES.md not found" in ws.fail("qg", "status")


def test_the_real_tracking_files_of_this_repository_are_valid() -> None:
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(TRACK), "--root", str(REPO), "validate"],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )  # fmt: skip
    assert result.returncode == 0, result.stdout + result.stderr
    assert "quality gates" in result.stdout


def test_status_and_next_do_not_modify_any_file(ws: Workspace) -> None:
    before = {n: ws.read(n) for n in FILES}
    ws.ok("status")
    ws.ok("next")
    ws.ok("qg", "status")
    assert {n: ws.read(n) for n in FILES} == before


# ------------------------------------------------------------------------------ utilities
def test_duration_formatting(track: ModuleType) -> None:
    f = track.fmt_duration
    assert f("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:03+00:00") == "0m 03s"
    assert f("2026-01-01T00:00:00+00:00", "2026-01-01T00:12:05+00:00") == "12m 05s"
    assert f("2026-01-01T00:00:00+00:00", "2026-01-01T01:02:03+00:00") == "1h 02m 03s"
    assert f("2026-01-01T00:00:00+00:00", "2025-12-31T23:59:59+00:00") == "n/a"
    assert f("2026-01-01T00:00:00+04:00", "2025-12-31T20:00:05+00:00") == "0m 05s"  # offsets honoured


def test_now_is_iso8601_with_a_utc_offset(track: ModuleType) -> None:
    assert ISO_TZ.match(track.now())


def test_clean_neutralises_table_and_field_separators(track: ModuleType) -> None:
    assert track.clean("a · b | c\n  d") == "a; b / c d"


def test_short_truncates_long_lists(track: ModuleType) -> None:
    ids = [f"QG-01.{i}" for i in range(1, 30)]
    text = track.short(ids)
    assert text.count("QG-01.") == 12
    assert "(+17 more" in text
    assert track.short(["a", "b"]) == "a, b"


def test_register_token_expansion(ws: Workspace, track: ModuleType) -> None:
    reg = track.Register(ws.root)
    assert [c.id for c in reg.expand("QG-03.1")] == ["QG-03.1"]
    assert [c.id for c in reg.expand("QG-03")] == ["QG-03.1"]
    due_p00 = {c.id for c in reg.expand("QG-all@P00")}
    assert due_p00 == {f"QG-{n:02d}.1" for n in range(1, 7)}
    assert "QG-12.1" not in {c.id for c in reg.expand("QG-all@P99")}  # QG-12 is never part of QG-all
    with pytest.raises(KeyError):
        reg.expand("QG-99.1")
    assert reg.unsatisfied(["QG-01.1", "QG-77"]) == ["QG-01.1", "QG-77 (unknown)"]


def test_dashboard_completion_percentage_is_computed_from_tasks(ws: Workspace) -> None:
    ws.finish("P00-T01")
    text = ws.read("PROGRESS_DASHBOARD.md")
    m = re.search(r"\*\*Overall completion \(tasks\)\*\* \| \*\*([\d.]+)%\*\*", text)
    assert m
    assert float(m.group(1)) == pytest.approx(100 / 6, abs=0.1)
