"""Task lifecycle: start / check / verify / complete / block / approve-phase / next / dashboard."""

import re

from conftest import ISO_TZ, Workspace


def _field(block: str, name: str) -> str:
    m = re.search(rf"{name}: ([^·\n]+)", block)
    assert m, f"{name} not found in {block!r}"
    return m.group(1).strip()


# --------------------------------------------------------------------------- start
def test_start_refused_when_phase_not_approved(ws: Workspace) -> None:
    out = ws.fail("start", "P01-T01")
    assert "phase P01 is not approved" in out


def test_start_refused_when_prerequisites_incomplete(ws: Workspace) -> None:
    out = ws.fail("start", "P00-T02")
    assert "prerequisites not COMPLETED: P00-T01" in out
    assert "`NOT_STARTED`" in ws.task_block("P00-T02")


def test_start_unknown_task(ws: Workspace) -> None:
    assert "unknown task id" in ws.fail("start", "P00-T99")


def test_start_records_status_and_a_real_timestamp(ws: Workspace) -> None:
    ws.ok("start", "P00-T01")
    block = ws.task_block("P00-T01")
    assert "`IN_PROGRESS` 🔄" in block
    assert ISO_TZ.match(_field(block, "Started"))
    assert _field(block, "Completed") == "—"


def test_start_twice_is_refused(ws: Workspace) -> None:
    ws.ok("start", "P00-T01")
    assert "expected NOT_STARTED" in ws.fail("start", "P00-T01")


def test_multi_start_is_all_or_nothing(ws: Workspace) -> None:
    ws.fail("start", "P00-T01", "P00-T02")  # T02 is not eligible
    assert "`NOT_STARTED`" in ws.task_block("P00-T01")


def test_timestamps_cannot_be_supplied_by_hand(ws: Workspace) -> None:
    out = ws.fail("start", "P00-T01", "--started", "2020-01-01T00:00:00+00:00")
    assert "unrecognized arguments" in out
    assert "`NOT_STARTED`" in ws.task_block("P00-T01")


# --------------------------------------------------------------------------- check
def test_check_requires_task_in_progress(ws: Workspace) -> None:
    assert "only be ticked while it is in progress" in ws.fail("check", "P00-T01.1")


def test_check_ticks_subtasks_and_rejects_unknown(ws: Workspace) -> None:
    ws.ok("start", "P00-T01")
    ws.ok("check", "P00-T01.1")
    block = ws.task_block("P00-T01")
    assert "- [x] P00-T01.1" in block
    assert "- [ ] P00-T01.2" in block
    assert "unknown subtask" in ws.fail("check", "P00-T01.9")


# --------------------------------------------------------------------------- complete
def test_complete_refused_with_unticked_subtasks(ws: Workspace) -> None:
    ws.ok("start", "P00-T01")
    out = ws.fail("complete", "P00-T01", "--evidence", "x")
    assert "unticked subtasks: P00-T01.1, P00-T01.2" in out


def test_complete_requires_real_evidence(ws: Workspace) -> None:
    ws.ok("start", "P00-T01")
    ws.ok("check", "P00-T01.1", "P00-T01.2")
    for bad in ("", "   ", "—", "-"):
        assert "evidence is required" in ws.fail("complete", "P00-T01", "--evidence", bad)
    assert "`IN_PROGRESS`" in ws.task_block("P00-T01")


def test_complete_records_checkbox_timestamps_duration_and_evidence(ws: Workspace) -> None:
    ws.finish("P00-T01")
    block = ws.task_block("P00-T01")
    assert block.startswith("- [x] **P00-T01**")
    assert "`COMPLETED` ✅" in block
    assert ISO_TZ.match(_field(block, "Started"))
    assert ISO_TZ.match(_field(block, "Completed"))
    assert re.fullmatch(r"(\d+h )?\d+m \d\ds", _field(block, "Duration"))
    assert "Evidence: done in test" in block


def test_complete_from_not_started_is_refused(ws: Workspace) -> None:
    assert "cannot complete" in ws.fail("complete", "P00-T01", "--evidence", "x")


def test_approval_task_needs_verify_then_named_approver(ws: Workspace) -> None:
    ws.finish("P00-T01")
    ws.ok("start", "P00-T02")
    ws.ok("check", "P00-T02.1")
    assert "run verify first" in ws.fail("complete", "P00-T02", "--evidence", "x", "--approved-by", "me")
    ws.ok("verify", "P00-T02", "--evidence", "ready for review")
    assert "`AWAITING_VERIFICATION` 🔎" in ws.task_block("P00-T02")
    assert "requires --approved-by" in ws.fail("complete", "P00-T02", "--evidence", "approved")
    ws.ok("complete", "P00-T02", "--evidence", "approved", "--approved-by", "Ada")
    assert "Approved by: Ada" in ws.task_block("P00-T02")


def test_verify_requires_in_progress_and_ticked_subtasks(ws: Workspace) -> None:
    assert "expected IN_PROGRESS" in ws.fail("verify", "P00-T01", "--evidence", "x")
    ws.ok("start", "P00-T01")
    assert "unticked subtasks" in ws.fail("verify", "P00-T01", "--evidence", "x")


# --------------------------------------------------------------------------- block / unblock
def test_block_records_reason_and_prevents_completion(ws: Workspace) -> None:
    ws.ok("start", "P00-T01")
    ws.ok("check", "P00-T01.1", "P00-T01.2")
    ws.ok("block", "P00-T01", "--reason", "waiting for access")
    block = ws.task_block("P00-T01")
    assert "`BLOCKED` ⛔" in block
    assert "Blocker: waiting for access" in block
    assert "cannot complete" in ws.fail("complete", "P00-T01", "--evidence", "x")
    status = ws.ok("status")
    assert "`P00-T01` First task — **waiting for access**" in status


def test_unblock_returns_to_in_progress_only_if_it_had_started(ws: Workspace) -> None:
    ws.ok("start", "P00-T01")
    ws.ok("block", "P00-T01", "--reason", "r")
    ws.ok("unblock", "P00-T01")
    assert "`IN_PROGRESS`" in ws.task_block("P00-T01")
    assert "Blocker: —" in ws.task_block("P00-T01")

    ws.ok("block", "P00-T02", "--reason", "never started")
    ws.ok("unblock", "P00-T02")
    assert "`NOT_STARTED`" in ws.task_block("P00-T02")
    assert "is NOT_STARTED, not BLOCKED" in ws.fail("unblock", "P00-T02")


# --------------------------------------------------------------------------- approve-phase / next
def test_approve_phase_records_approver_and_time_and_unlocks_start(ws: Workspace) -> None:
    ws.finish("P00-T01")
    ws.finish("P00-T02", approval=True)
    for q in range(1, 7):
        ws.ok("qg", "check", f"QG-{q:02d}.1", "--evidence", "e")
    ws.finish("P00-GATE", approval=True)
    ws.ok("qg", "check", "QG-01.1", "--evidence", "e")  # already satisfied; idempotent re-check
    ws.ok("approve-phase", "P01", "--by", "Ada")
    line = next(ln for ln in ws.read("TASK_CHECKLIST.md").splitlines() if "Phase approval" in ln and "Ada" in ln)
    assert re.search(r"APPROVED by Ada at \d{4}-\d\d-\d\dT", line)
    ws.ok("start", "P01-T01")
    assert "`IN_PROGRESS`" in ws.task_block("P01-T01")


def test_approve_unknown_phase(ws: Workspace) -> None:
    assert "unknown phase" in ws.fail("approve-phase", "P99", "--by", "x")


def test_next_lists_only_eligible_tasks(ws: Workspace) -> None:
    assert ws.ok("next").split() == ["P00-T01", "W1", "First", "task"]
    ws.finish("P00-T01")
    assert ws.ok("next").startswith("P00-T02")
    assert "P01" not in ws.ok("next")  # phase not approved
    assert "P00-T01" not in ws.ok("next")  # already completed


# --------------------------------------------------------------------------- dashboard / log / files
def test_dashboard_reflects_state_and_preserves_hand_written_text(ws: Workspace) -> None:
    ws.finish("P00-T01")
    ws.ok("start", "P00-T02")
    text = ws.read("PROGRESS_DASHBOARD.md")
    assert "hand-written intro" in text
    assert "hand-written outro" in text
    assert "| ✅ Completed | 1 |" in text
    assert "| 🔄 In progress | 1 |" in text
    assert "`P00-T02`" in text
    assert "### Quality gates" in text


def test_dashboard_is_idempotent_apart_from_its_timestamp(ws: Workspace) -> None:
    ws.ok("dashboard")
    first = re.sub(r"at \*\*[^*]+\*\*", "", ws.read("PROGRESS_DASHBOARD.md"))
    ws.ok("dashboard")
    second = re.sub(r"at \*\*[^*]+\*\*", "", ws.read("PROGRESS_DASHBOARD.md"))
    assert first == second


def test_dashboard_without_markers_fails_clearly(ws: Workspace) -> None:
    ws.write("PROGRESS_DASHBOARD.md", "# no markers\n")
    assert "AUTO markers" in ws.fail("dashboard")


def test_log_is_append_only_and_records_each_action(ws: Workspace) -> None:
    before = ws.read("EXECUTION_LOG.md")
    ws.ok("start", "P00-T01")
    ws.ok("check", "P00-T01.1", "P00-T01.2")
    ws.ok("complete", "P00-T01", "--evidence", "all good")
    after = ws.read("EXECUTION_LOG.md")
    assert after.startswith(before.rstrip("\n"))
    assert "START P00-T01" in after
    assert "COMPLETE P00-T01" in after
    assert "evidence: all good" in after
    assert re.search(r"### \d{4}-\d\d-\d\dT[\d:]+[+-]\d\d:\d\d — START", after)


def test_an_action_changes_only_the_lines_of_its_task(ws: Workspace) -> None:
    before = ws.read("TASK_CHECKLIST.md").splitlines()
    ws.ok("start", "P00-T01")
    after = ws.read("TASK_CHECKLIST.md").splitlines()
    assert len(before) == len(after)
    changed = [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b]
    assert len(changed) == 2  # the task line and its timing line
    assert all("P00-T01" in before[i] or "Started" in before[i] for i in changed)


def test_files_stay_lf_with_trailing_newline(ws: Workspace) -> None:
    ws.finish("P00-T01")
    for name in ("TASK_CHECKLIST.md", "EXECUTION_LOG.md", "PROGRESS_DASHBOARD.md", "QUALITY_GATES.md"):
        raw = (ws.root / name).read_bytes()
        assert b"\r\n" not in raw, name
        assert raw.endswith(b"\n"), name


def test_validate_stays_clean_after_every_step_of_a_full_flow(ws: Workspace) -> None:
    steps = [
        ("start", "P00-T01"), ("check", "P00-T01.1", "P00-T01.2"),
        ("complete", "P00-T01", "--evidence", "e"), ("start", "P00-T02"), ("check", "P00-T02.1"),
        ("verify", "P00-T02", "--evidence", "v"),
        ("complete", "P00-T02", "--evidence", "c", "--approved-by", "t"),
    ]  # fmt: skip
    for step in steps:
        ws.ok(*step)
        assert "OK" in ws.ok("validate"), step
