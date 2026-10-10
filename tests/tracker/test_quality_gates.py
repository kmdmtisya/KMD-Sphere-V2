"""Quality-gate register: criteria, gate lifecycle, waivers, failures and enforcement on tasks."""

import re
from datetime import date, timedelta

from conftest import ISO_TZ, Workspace


def _future(days: int = 30) -> str:
    return (date.today() + timedelta(days=days)).isoformat()


def _gate(ws: Workspace, gate: str) -> str:
    text = ws.read("QUALITY_GATES.md")
    start = text.index(f"### {gate}:")
    end = text.find("\n### ", start + 1)
    nxt_section = text.find("\n## ", start + 1)
    ends = [e for e in (end, nxt_section) if e != -1]
    return text[start : min(ends) if ends else len(text)]


def _field(gate_text: str, name: str) -> str:
    m = re.search(rf"^{re.escape(name)}: ?(.*?)\s*$", gate_text, re.M)
    assert m, name
    return m.group(1)


def _waive(ws: Workspace, cid: str, days: int = 30) -> str:
    return ws.ok("qg", "waive", cid, "--justification", "deferred", "--approved-by", "Ada", "--risk-owner", "Bo", "--expires", _future(days))  # fmt: skip


# ------------------------------------------------------------------------------ check / uncheck
def test_check_records_evidence_timestamp_and_starts_the_gate(ws: Workspace) -> None:
    ws.ok("qg", "check", "QG-01.1", "--evidence", "ran the thing; it passed")
    g = _gate(ws, "QG-01")
    assert "- [x] QG-01.1" in g
    assert "Evidence: ran the thing; it passed" in g
    assert re.search(r"Verified: \d{4}-\d\d-\d\dT[\d:]+[+-]\d\d:\d\d", g)
    assert _field(g, "Status") == "IN_PROGRESS"
    assert ISO_TZ.match(_field(g, "Start Timestamp"))
    assert ISO_TZ.match(_field(g, "Verification Timestamp"))
    assert _field(g, "Evidence").startswith("1/1 criteria verified")


def test_check_requires_evidence_and_a_known_criterion(ws: Workspace) -> None:
    assert "--evidence required" in ws.fail("qg", "check", "QG-01.1", "--evidence", "   ")
    assert "unknown criterion" in ws.fail("qg", "check", "QG-01.9", "--evidence", "x")
    assert "- [ ] QG-01.1" in _gate(ws, "QG-01")


def test_evidence_separator_is_neutralised(ws: Workspace) -> None:
    ws.ok("qg", "check", "QG-01.1", "--evidence", "part one · part two | with a pipe")
    assert "OK" in ws.ok("validate")  # no field corruption
    assert " · part two" not in _gate(ws, "QG-01")


def test_uncheck_reopens_a_passed_gate(ws: Workspace) -> None:
    ws.ok("qg", "check", "QG-01.1", "--evidence", "e")
    ws.ok("qg", "pass", "QG-01", "--evidence", "all good")
    assert _field(_gate(ws, "QG-01"), "Status") == "PASSED"
    ws.ok("qg", "uncheck", "QG-01.1", "--reason", "regression found")
    g = _gate(ws, "QG-01")
    assert "- [ ] QG-01.1" in g
    assert _field(g, "Status") == "IN_PROGRESS"
    assert _field(g, "End Timestamp") == "—"


# ------------------------------------------------------------------------------ pass / reverify
def test_pass_requires_every_criterion(ws: Workspace) -> None:
    assert "criteria not satisfied: QG-01.1" in ws.fail("qg", "pass", "QG-01", "--evidence", "x")


def test_pass_sets_timestamps_and_status(ws: Workspace) -> None:
    ws.ok("qg", "check", "QG-01.1", "--evidence", "e")
    ws.ok("qg", "pass", "QG-01", "--evidence", "gate evidence")
    g = _gate(ws, "QG-01")
    assert _field(g, "Status") == "PASSED"
    assert ISO_TZ.match(_field(g, "End Timestamp"))
    assert _field(g, "Evidence") == "gate evidence"
    assert "OK" in ws.ok("validate")


def test_release_readiness_gate_needs_a_named_approver(ws: Workspace) -> None:
    for n in range(1, 12):  # every gate except the release-readiness gate itself
        ws.ok("qg", "check", f"QG-{n:02d}.1", "--evidence", "e")
    ws.ok("qg", "require", "QG-all@P15")
    ws.ok("qg", "check", "QG-12.1", "--evidence", "all gates verified")
    assert "requires --approved-by" in ws.fail("qg", "pass", "QG-12", "--evidence", "x")
    ws.ok("qg", "pass", "QG-12", "--evidence", "release approved", "--approved-by", "Ada")
    assert _field(_gate(ws, "QG-12"), "Approved By") == "Ada"


def test_reverify_only_after_a_pass_and_refreshes_the_verification_time(ws: Workspace) -> None:
    ws.ok("qg", "check", "QG-01.1", "--evidence", "e")
    assert "use `qg pass`" in ws.fail("qg", "reverify", "QG-01", "--evidence", "x")
    ws.ok("qg", "pass", "QG-01", "--evidence", "first")
    end_before = _field(_gate(ws, "QG-01"), "End Timestamp")
    ws.ok("qg", "reverify", "QG-01", "--evidence", "second look")
    g = _gate(ws, "QG-01")
    assert _field(g, "End Timestamp") == end_before
    assert _field(g, "Evidence") == "second look"


def test_check_of_the_final_criterion_requires_all_earlier_gates(ws: Workspace) -> None:
    out = ws.fail("qg", "check", "QG-12.1", "--evidence", "x")
    assert "requires every core criterion" in out
    assert "QG-01.1" in out


# ------------------------------------------------------------------------------ failure handling
def test_fail_blocks_only_the_listed_tasks(ws: Workspace) -> None:
    ws.ok("qg", "fail", "QG-04.1", "--issue", "build is broken", "--blocks", "P00-T01")
    g = _gate(ws, "QG-04")
    assert _field(g, "Status") == "FAILED"
    assert "QG-04.1: build is broken" in _field(g, "Blocking Issues")
    assert _field(g, "Blocks") == "P00-T01"
    assert ISO_TZ.match(_field(g, "Start Timestamp"))  # a failed gate was necessarily started
    assert "blocked by failed/blocked quality gate(s) QG-04" in ws.fail("start", "P00-T01")
    assert "OK" in ws.ok("validate")


def test_failed_gate_cannot_be_rechecked_until_resolved(ws: Workspace) -> None:
    ws.ok("qg", "fail", "QG-04.1", "--issue", "broken")
    assert "run `qg resolve QG-04`" in ws.fail("qg", "check", "QG-04.1", "--evidence", "fixed?")
    ws.ok("qg", "resolve", "QG-04", "--note", "fixed the build")
    g = _gate(ws, "QG-04")
    assert _field(g, "Status") == "IN_PROGRESS"
    assert _field(g, "Blocking Issues") == "—"
    assert _field(g, "Blocks") == "—"
    ws.ok("qg", "check", "QG-04.1", "--evidence", "fresh evidence")
    ws.ok("start", "P00-T01")  # the task is unblocked again


def test_block_and_resolve_a_gate(ws: Workspace) -> None:
    ws.ok("qg", "block", "QG-04", "--reason", "waiting for a device", "--blocks", "P00-T01")
    assert _field(_gate(ws, "QG-04"), "Status") == "BLOCKED"
    assert "is NOT_STARTED, not FAILED/BLOCKED" in ws.fail("qg", "resolve", "QG-01", "--note", "n")
    ws.ok("qg", "resolve", "QG-04", "--note", "device arrived")
    assert _field(_gate(ws, "QG-04"), "Status") == "IN_PROGRESS"


# ------------------------------------------------------------------------------ waivers
def test_critical_criteria_can_never_be_waived(ws: Workspace) -> None:
    out = ws.fail("qg", "waive", "QG-02.1", "--justification", "j", "--approved-by", "a", "--risk-owner", "r", "--expires", _future())  # fmt: skip
    assert "CRITICAL" in out
    assert "WAIVED" not in _gate(ws, "QG-02")


def test_waiver_needs_a_future_valid_date(ws: Workspace) -> None:
    base = ("qg", "waive", "QG-01.1", "--justification", "j", "--approved-by", "a", "--risk-owner", "r")
    assert "future date" in ws.fail(*base, "--expires", date.today().isoformat())
    assert "future date" in ws.fail(*base, "--expires", "2020-01-01")
    assert "YYYY-MM-DD" in ws.fail(*base, "--expires", "next week")


def test_waiver_is_registered_and_counts_as_satisfied(ws: Workspace) -> None:
    _waive(ws, "QG-01.1")
    text = ws.read("QUALITY_GATES.md")
    assert re.search(r"\| W-001 \| QG-01\.1 \| deferred \| Ada \| Bo \| [^|]+ \| \d{4}-\d\d-\d\d \| ACTIVE \|", text)
    assert "· WAIVED: W-001" in _gate(ws, "QG-01")
    assert "satisfied" in ws.ok("qg", "require", "QG-01.1")
    assert "OK" in ws.ok("validate")


def test_gate_with_a_waiver_ends_as_waived_and_needs_an_approver(ws: Workspace) -> None:
    _waive(ws, "QG-01.1")
    assert "requires --approved-by (waived criteria present)" in ws.fail("qg", "pass", "QG-01", "--evidence", "x")
    ws.ok("qg", "pass", "QG-01", "--evidence", "x", "--approved-by", "Ada")
    assert _field(_gate(ws, "QG-01"), "Status") == "WAIVED"


def test_real_evidence_supersedes_a_waiver(ws: Workspace) -> None:
    _waive(ws, "QG-01.1")
    ws.ok("qg", "check", "QG-01.1", "--evidence", "now properly verified")
    text = ws.read("QUALITY_GATES.md")
    assert "SUPERSEDED" in text
    assert "WAIVED" not in _gate(ws, "QG-01")


def test_revoking_a_waiver_makes_the_criterion_unsatisfied_again(ws: Workspace) -> None:
    _waive(ws, "QG-01.1")
    ws.ok("qg", "revoke-waiver", "W-001")
    assert "REVOKED" in ws.read("QUALITY_GATES.md")
    assert "NOT SATISFIED" in ws.fail("qg", "require", "QG-01.1")
    assert "unknown waiver" in ws.fail("qg", "revoke-waiver", "W-099")


def test_an_expired_waiver_no_longer_satisfies_the_criterion(ws: Workspace) -> None:
    _waive(ws, "QG-01.1", days=5)
    ws.edit("QUALITY_GATES.md", _future(5), "2020-01-01")
    assert "NOT SATISFIED" in ws.fail("qg", "require", "QG-01.1")


# ------------------------------------------------------------------------------ require (CI)
def test_require_tokens_and_exit_codes(ws: Workspace) -> None:
    assert "NOT SATISFIED: QG-01.1" in ws.fail("qg", "require", "QG-01.1")
    ws.ok("qg", "check", "QG-01.1", "--evidence", "e")
    ws.ok("qg", "require", "QG-01.1")
    ws.ok("qg", "require", "QG-01")  # whole gate
    out = ws.fail("qg", "require", "QG-01", "QG-02")
    assert "QG-02.1" in out
    assert "unknown" in ws.fail("qg", "require", "QG-77.7")


def test_require_all_at_phase_covers_only_criteria_due_by_then(ws: Workspace) -> None:
    for n in range(1, 7):
        ws.ok("qg", "check", f"QG-{n:02d}.1", "--evidence", "e")
    ws.ok("qg", "require", "QG-all@P00")  # everything due at P00 is verified
    assert "QG-07.1" in ws.fail("qg", "require", "QG-all@P01")  # P01 criteria are not


# ------------------------------------------------------------------------------ enforcement on tasks
def _until_p01_is_startable(ws: Workspace) -> None:
    ws.finish("P00-T01")
    ws.finish("P00-T02", approval=True)
    for n in range(1, 7):
        ws.ok("qg", "check", f"QG-{n:02d}.1", "--evidence", "e")
    ws.finish("P00-GATE", approval=True)
    ws.ok("approve-phase", "P01", "--by", "Ada")


def test_phase_gate_cannot_complete_while_its_criteria_are_open(ws: Workspace) -> None:
    ws.finish("P00-T01")
    ws.finish("P00-T02", approval=True)
    ws.ok("start", "P00-GATE")
    ws.ok("check", "P00-GATE.1")
    ws.ok("verify", "P00-GATE", "--evidence", "ready")
    out = ws.fail("complete", "P00-GATE", "--evidence", "e", "--approved-by", "Ada")
    assert "quality-gate criteria not satisfied" in out
    assert "QG-01.1" in out


def test_task_cannot_start_until_its_start_gates_are_satisfied(ws: Workspace) -> None:
    _until_p01_is_startable(ws)
    ws.ok("qg", "uncheck", "QG-01.1", "--reason", "re-opened")
    assert "start gates not satisfied: QG-01.1" in ws.fail("start", "P01-T01")
    ws.ok("qg", "check", "QG-01.1", "--evidence", "re-verified")
    ws.ok("start", "P01-T01")


def test_phase_gate_completes_once_criteria_are_verified(ws: Workspace) -> None:
    _until_p01_is_startable(ws)
    assert "COMPLETED" in ws.task_block("P00-GATE")
    assert "Approved by: tester" in ws.task_block("P00-GATE")
    assert "QG-01" in ws.read("PROGRESS_DASHBOARD.md")


def test_summary_block_in_the_register_is_refreshed(ws: Workspace) -> None:
    ws.ok("qg", "check", "QG-01.1", "--evidence", "e")
    text = ws.read("QUALITY_GATES.md")
    assert "(placeholder)" not in text
    assert "| QG-01 | Architecture and Design | 🔄 IN_PROGRESS | 1/1 |" in text
    assert "Criteria satisfied overall: 1/12" in text


def test_qg_all_covers_only_the_core_gates(ws: Workspace) -> None:
    text = ws.read("QUALITY_GATES.md")
    end = text.index("## Waiver register")
    section = text[text.index("### QG-12:") : end].replace("QG-12", "QG-13").replace("Required: P", "Required: P")
    ws.write("QUALITY_GATES.md", text[:end] + section + text[end:])
    ws.edit("TASK_CHECKLIST.md", "QG-11.1, QG-12.1", "QG-11.1, QG-12.1, QG-13.1")
    for n in range(1, 12):
        ws.ok("qg", "check", f"QG-{n:02d}.1", "--evidence", "e")
    ws.ok("qg", "require", "QG-all@P15")  # QG-13.1 is unverified but is not a core gate


def test_qg_all_includes_core_workstream_gates_but_not_forex(ws: Workspace) -> None:
    """Gates QG-13..QG-20 (Forex) are optional; QG-21+ (multi-currency) are core."""
    text = ws.read("QUALITY_GATES.md")
    end = text.index("## Waiver register")
    base = text[text.index("### QG-12:") : end]
    extra = "".join(base.replace("QG-12", f"QG-{n}") for n in range(13, 22))
    ws.write("QUALITY_GATES.md", text[:end] + extra + text[end:])
    bound = ", ".join(f"QG-{n}.1" for n in range(13, 22))
    ws.edit("TASK_CHECKLIST.md", "QG-11.1, QG-12.1", f"QG-11.1, QG-12.1, {bound}")
    for n in range(1, 12):
        ws.ok("qg", "check", f"QG-{n:02d}.1", "--evidence", "e")
    out = ws.fail("qg", "require", "QG-all@P15")
    assert "QG-21.1" in out
    assert "QG-13.1" not in out
    ws.ok("qg", "check", "QG-21.1", "--evidence", "e")
    ws.ok("qg", "require", "QG-all@P15")
