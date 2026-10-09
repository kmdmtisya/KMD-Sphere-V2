"""`validate` must catch corrupted, inconsistent or forged tracking state."""

from datetime import date, timedelta

import pytest
from conftest import Workspace


def _bad(ws: Workspace) -> str:
    out = ws.fail("validate")
    assert "VALIDATION FAILED" in out
    return out


def test_pristine_roadmap_is_valid(ws: Workspace) -> None:
    assert "OK: 6 tasks, 2 phases, 12 quality gates / 12 criteria" in ws.ok("validate")


def test_pre_tracking_start_marker_is_accepted(ws: Workspace) -> None:
    ws.edit("TASK_CHECKLIST.md", "- [ ] **P00-T01** · First task · `NOT_STARTED` ⬜", "- [ ] **P00-T01** · First task · `AWAITING_VERIFICATION` 🔎")
    ws.edit("TASK_CHECKLIST.md", "  - Started: — · Completed: — · Duration: — · Blocker: —\n  - Evidence: —\n  - [ ] P00-T01.1", "  - Started: not recorded (pre-tracking) · Completed: — · Duration: — · Blocker: —\n  - Evidence: —\n  - [ ] P00-T01.1")  # fmt: skip
    assert "OK" in ws.ok("validate")


# ----------------------------------------------------------------------------- dependency graph
def test_unknown_dependency(ws: Workspace) -> None:
    ws.edit("TASK_CHECKLIST.md", "Deps: P00-T01 · Wave: W2", "Deps: P00-T99 · Wave: W2")
    assert "unknown dependency P00-T99" in _bad(ws)


def test_dependency_cycle(ws: Workspace) -> None:
    ws.edit("TASK_CHECKLIST.md", "Deps: — · Wave: W1 · Track: DOC · Size: S · Approval: no\n  - Started: — · Completed: — · Duration: — · Blocker: —\n  - Evidence: —\n  - [ ] P00-T01.1", "Deps: P00-T02 · Wave: W1 · Track: DOC · Size: S · Approval: no\n  - Started: — · Completed: — · Duration: — · Blocker: —\n  - Evidence: —\n  - [ ] P00-T01.1")  # fmt: skip
    assert "dependency cycle" in _bad(ws)


def test_dependency_must_be_in_an_earlier_wave(ws: Workspace) -> None:
    ws.edit("TASK_CHECKLIST.md", "Deps: P00-T01 · Wave: W2", "Deps: P00-T01 · Wave: W1")
    assert "not in an earlier wave" in _bad(ws)


# ----------------------------------------------------------------------------- status / checkbox / timestamps
def test_checkbox_without_completed_status(ws: Workspace) -> None:
    ws.edit("TASK_CHECKLIST.md", "- [ ] **P00-T01**", "- [x] **P00-T01**")
    assert "checkbox/status mismatch" in _bad(ws)


def test_unknown_status_token(ws: Workspace) -> None:
    ws.edit("TASK_CHECKLIST.md", "· `NOT_STARTED` ⬜\n  - Deps: — ·", "· `DONE_ISH` ⬜\n  - Deps: — ·")
    assert "bad status DONE_ISH" in _bad(ws)


def test_forged_completed_task_is_detected(ws: Workspace) -> None:
    ws.edit("TASK_CHECKLIST.md", "- [ ] **P00-T01** · First task · `NOT_STARTED` ⬜", "- [x] **P00-T01** · First task · `COMPLETED` ✅")
    out = _bad(ws)
    assert "COMPLETED without ISO8601+tz Completed timestamp" in out
    assert "COMPLETED without evidence" in out
    assert "COMPLETED with unticked subtasks" in out


def test_completed_task_with_unfinished_prerequisite(ws: Workspace) -> None:
    ws.finish("P00-T01")
    block = ws.task_block("P00-T01")
    ws.edit("TASK_CHECKLIST.md", block, block.replace("`COMPLETED` ✅", "`IN_PROGRESS` 🔄").replace("- [x] **", "- [ ] **", 1))
    ws.edit("TASK_CHECKLIST.md", "- [ ] **P00-T02** · Second task needing approval · `NOT_STARTED` ⬜", "- [x] **P00-T02** · Second task needing approval · `COMPLETED` ✅")
    assert "prerequisite P00-T01 is IN_PROGRESS" in _bad(ws)  # fmt: skip


def test_in_progress_without_a_start_timestamp(ws: Workspace) -> None:
    ws.edit("TASK_CHECKLIST.md", "- [ ] **P00-T01** · First task · `NOT_STARTED` ⬜", "- [ ] **P00-T01** · First task · `IN_PROGRESS` 🔄")
    assert "IN_PROGRESS without a recorded Started timestamp" in _bad(ws)


def test_not_started_task_must_not_carry_timestamps(ws: Workspace) -> None:
    ws.edit("TASK_CHECKLIST.md", "  - Started: — · Completed: — · Duration: — · Blocker: —\n  - Evidence: —\n  - [ ] P00-T01.1", "  - Started: 2026-01-01T00:00:00+00:00 · Completed: — · Duration: — · Blocker: —\n  - Evidence: —\n  - [ ] P00-T01.1")  # fmt: skip
    assert "NOT_STARTED but has timestamps" in _bad(ws)


# ----------------------------------------------------------------------------- quality-gate bindings
def test_unknown_gate_token(ws: Workspace) -> None:
    ws.edit("TASK_CHECKLIST.md", "Gates-start: QG-01.1", "Gates-start: QG-99.9")
    assert "unknown gate/criterion QG-99.9" in _bad(ws)


def test_malformed_gate_token(ws: Workspace) -> None:
    ws.edit("TASK_CHECKLIST.md", "Gates-start: QG-01.1", "Gates-start: whatever")
    assert "bad gate token whatever" in _bad(ws)


def test_criterion_not_bound_to_any_task_is_rejected(ws: Workspace) -> None:
    ws.edit("TASK_CHECKLIST.md", ", QG-12.1", "")
    assert "criteria not bound to any task gate: QG-12.1" in _bad(ws)


def test_evidence_task_must_exist(ws: Workspace) -> None:
    ws.edit("QUALITY_GATES.md", "· By: P00-T01\n\nStatus: NOT_STARTED  \nOwner: Unassigned  \nStart Timestamp: —  \nEnd Timestamp: —  \nVerification Timestamp: —  \nEvidence: —  \nBlocking Issues: —  \nBlocks: —  \nApproved By: —\n\n### QG-02", "· By: P99-T99\n\nStatus: NOT_STARTED  \nOwner: Unassigned  \nStart Timestamp: —  \nEnd Timestamp: —  \nVerification Timestamp: —  \nEvidence: —  \nBlocking Issues: —  \nBlocks: —  \nApproved By: —\n\n### QG-02")  # fmt: skip
    assert "evidence task P99-T99 does not exist" in _bad(ws)


# ----------------------------------------------------------------------------- register integrity
def _set_status(ws: Workspace, gate: str, status: str) -> None:
    text = ws.read("QUALITY_GATES.md")
    start = text.index(f"### {gate}:")
    pos = text.index("Status: NOT_STARTED", start)
    ws.write("QUALITY_GATES.md", text[:pos] + f"Status: {status}" + text[pos + len("Status: NOT_STARTED") :])


def test_forged_passed_gate_is_detected(ws: Workspace) -> None:
    _set_status(ws, "QG-01", "PASSED")
    out = _bad(ws)
    assert "QG-01 is PASSED but QG-01.1 is not satisfied" in out
    assert "PASSED without ISO8601+tz End Timestamp" in out
    assert "PASSED without evidence" in out


def test_unknown_gate_status(ws: Workspace) -> None:
    _set_status(ws, "QG-03", "GREAT")
    assert "QG-03: bad status GREAT" in _bad(ws)


def test_failed_gate_needs_blocking_issue(ws: Workspace) -> None:
    _set_status(ws, "QG-03", "FAILED")
    assert "FAILED without Blocking Issues" in _bad(ws)


def test_missing_gate_is_detected(ws: Workspace) -> None:
    text = ws.read("QUALITY_GATES.md")
    start = text.index("### QG-12:")
    end = text.index("## Waiver register")
    ws.write("QUALITY_GATES.md", text[:start] + text[end:])
    assert "expected 12 gates, found 11" in _bad(ws)


def test_verified_criterion_needs_evidence_and_timestamp(ws: Workspace) -> None:
    ws.edit("QUALITY_GATES.md", "- [ ] QG-01.1 Criterion 1", "- [x] QG-01.1 Criterion 1")
    assert "verified without Evidence and ISO8601+tz Verified timestamp" in _bad(ws)


def test_expired_waiver_fails_validation(ws: Workspace) -> None:
    ws.ok("qg", "waive", "QG-01.1", "--justification", "j", "--approved-by", "a", "--risk-owner", "r", "--expires", (date.today() + timedelta(days=30)).isoformat())  # fmt: skip
    assert "OK" in ws.ok("validate")
    ws.edit("QUALITY_GATES.md", (date.today() + timedelta(days=30)).isoformat(), "2020-01-01")
    assert "waiver for QG-01.1 expired 2020-01-01" in _bad(ws)


def test_waiver_on_a_critical_criterion_is_invalid(ws: Workspace) -> None:
    row = "| W-001 | QG-02.1 | because | a | r | 2026-01-01T00:00:00+00:00 | 2099-01-01 | ACTIVE |"
    ws.edit("QUALITY_GATES.md", "<!-- WAIVERS:BEGIN -->", f"<!-- WAIVERS:BEGIN -->\n{row}")
    assert "waiver on CRITICAL criterion QG-02.1 is not allowed" in _bad(ws)


def test_regression_after_completion_is_a_warning_not_a_failure(ws: Workspace) -> None:
    ws.finish("P00-T01")
    ws.finish("P00-T02", approval=True)
    for n in range(1, 7):
        ws.ok("qg", "check", f"QG-{n:02d}.1", "--evidence", "e")
    ws.finish("P00-GATE", approval=True)
    ws.ok("qg", "uncheck", "QG-03.1", "--reason", "scope changed")
    result = ws.run("validate")
    assert result.returncode == 0
    assert "WARNING: P00-GATE is COMPLETED but gate criteria are no longer satisfied: QG-03.1" in result.stdout


@pytest.mark.parametrize("name", ["TASK_CHECKLIST.md", "QUALITY_GATES.md"])
def test_validate_is_read_only(ws: Workspace, name: str) -> None:
    before = ws.read(name)
    ws.ok("validate")
    assert ws.read(name) == before


# ----------------------------------------------------------------------------- scale: more waves and gates
def test_waves_compare_numerically_not_as_text(ws: Workspace) -> None:
    ws.edit("TASK_CHECKLIST.md", "Deps: P00-T01 · Wave: W2", "Deps: P00-T01 · Wave: W10")
    ws.edit("TASK_CHECKLIST.md", "Deps: — · Wave: W1 · Track: DOC", "Deps: — · Wave: W9 · Track: DOC")
    ws.edit("TASK_CHECKLIST.md", "Deps: P00-T01, P00-T02 · Wave: W3", "Deps: P00-T01, P00-T02 · Wave: W11")
    assert "OK" in ws.ok("validate"), "W9 must come before W10"


def _with_extra_gate(ws: Workspace, number: int) -> None:
    text = ws.read("QUALITY_GATES.md")
    start = text.index("### QG-12:")
    end = text.index("## Waiver register")
    section = text[start:end].replace("QG-12", f"QG-{number:02d}")
    ws.write("QUALITY_GATES.md", text[:end] + section + text[end:])


def test_additional_contiguous_gates_are_allowed(ws: Workspace) -> None:
    _with_extra_gate(ws, 13)
    ws.edit("TASK_CHECKLIST.md", "QG-11.1, QG-12.1", "QG-11.1, QG-12.1, QG-13.1")
    assert "13 quality gates" in ws.ok("validate")


def test_gate_numbering_gap_is_detected(ws: Workspace) -> None:
    _with_extra_gate(ws, 14)
    assert "contiguous" in _bad(ws)
