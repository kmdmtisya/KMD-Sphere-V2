"""Fixtures for the execution-tracker tests.

Every test works on a miniature roadmap written to a temporary directory and drives the real CLI
(`python scripts/track.py --root <dir> ...`). The real tracking files are never touched.

Mini roadmap
  P00 (approved)  P00-T01 -> P00-T02 (needs user approval) -> P00-GATE (approval, requires QG-01.1..QG-06.1)
  P01 (pending)   P01-T01 (start gate QG-01.1) -> P01-T02 -> P01-GATE (requires QG-07.1..QG-12.1)
Quality gates: QG-01..QG-12 with one criterion each (QG-01..06 due in P00, QG-07..12 due in P01);
QG-02.1 is CRITICAL.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO = Path(__file__).resolve().parents[2]
TRACK = REPO / "scripts" / "track.py"
ISO_TZ = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")

GATE_TITLES = {
    1: "Architecture and Design", 2: "Code Quality", 3: "Automated Testing", 4: "Android Platform",
    5: "iOS Platform", 6: "Financial Accuracy", 7: "AI Reliability", 8: "Security and Privacy",
    9: "Performance", 10: "CI/CD", 11: "End-to-End Integration", 12: "Release Readiness",
}  # fmt: skip


def _task(tid: str, title: str, deps: str, wave: int, approval: bool, subs: int, extra: str = "") -> str:
    lines = [
        f"- [ ] **{tid}** · {title} · `NOT_STARTED` ⬜",
        f"  - Deps: {deps} · Wave: W{wave} · Track: DOC · Size: S · Approval: {'yes' if approval else 'no'}{extra}",
        "  - Started: — · Completed: — · Duration: — · Blocker: —",
        "  - Evidence: —",
    ]
    lines += [f"  - [ ] {tid}.{i} subtask {i}" for i in range(1, subs + 1)]
    return "\n".join(lines)


def build_checklist() -> str:
    p00_done = ", ".join(f"QG-{n:02d}.1" for n in range(1, 7))
    p01_done = ", ".join(f"QG-{n:02d}.1" for n in range(7, 13))
    parts = [
        "# Task Checklist\n",
        "## P00 — Bootstrap\n",
        "- Phase approval: `APPROVED (bootstrap)`\n",
        _task("P00-T01", "First task", "—", 1, False, 2),
        _task("P00-T02", "Second task needing approval", "P00-T01", 2, True, 1),
        _task("P00-GATE", "Phase gate", "P00-T01, P00-T02", 3, True, 1, f" · Gates-done: {p00_done}"),
        "\n## P01 — Next phase\n",
        "- Phase approval: `PENDING`\n",
        _task("P01-T01", "Release-gated task", "P00-GATE", 1, False, 1, " · Gates-start: QG-01.1"),
        _task("P01-T02", "Follow-up task", "P01-T01", 2, False, 2),
        _task("P01-GATE", "Phase gate", "P01-T01, P01-T02", 3, True, 1, f" · Gates-done: {p01_done}"),
    ]
    return "\n".join(parts) + "\n"


def build_register() -> str:
    out = ["# Quality Gates Register", "", "## Summary", "", "<!-- QG-AUTO:BEGIN -->", "(placeholder)", "<!-- QG-AUTO:END -->", ""]
    for n in range(1, 13):
        phase = "P00" if n <= 6 else "P01"
        crit = " · CRITICAL" if n == 2 else ""
        out += [
            f"### QG-{n:02d}: {GATE_TITLES[n]}",
            "",
            f"- [ ] QG-{n:02d}.1 Criterion {n} · Required: {phase} · By: P00-T01{crit}",
            "",
            "Status: NOT_STARTED  ",
            "Owner: Unassigned  ",
            "Start Timestamp: —  ",
            "End Timestamp: —  ",
            "Verification Timestamp: —  ",
            "Evidence: —  ",
            "Blocking Issues: —  ",
            "Blocks: —  ",
            "Approved By: —",
            "",
        ]
    out += [
        "## Waiver register", "",
        "| Waiver | Criterion | Justification | Approved by | Risk owner | Granted | Expires | Status |",
        "|---|---|---|---|---|---|---|---|",
        "<!-- WAIVERS:BEGIN -->", "<!-- WAIVERS:END -->", "",
    ]  # fmt: skip
    return "\n".join(out)


DASHBOARD = "# Dashboard\n\nhand-written intro\n\n<!-- AUTO:BEGIN -->\n(none)\n<!-- AUTO:END -->\n\nhand-written outro\n"
LOG = "# Execution Log\n\nIntro text.\n"


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root

    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            [sys.executable, str(TRACK), "--root", str(self.root), *args],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )  # fmt: skip

    def ok(self, *args: str) -> str:
        result = self.run(*args)
        assert result.returncode == 0, f"{args} failed: {result.stdout}{result.stderr}"
        return result.stdout

    def fail(self, *args: str) -> str:
        result = self.run(*args)
        assert result.returncode != 0, f"{args} unexpectedly succeeded: {result.stdout}"
        return result.stdout + result.stderr

    def read(self, name: str) -> str:
        return (self.root / name).read_text(encoding="utf-8")

    def write(self, name: str, text: str) -> None:
        (self.root / name).write_text(text, encoding="utf-8", newline="\n")

    def edit(self, name: str, old: str, new: str) -> None:
        text = self.read(name)
        assert old in text, f"{old!r} not found in {name}"
        self.write(name, text.replace(old, new, 1))

    def task_block(self, tid: str) -> str:
        text = self.read("TASK_CHECKLIST.md")
        start = text.index(f"**{tid}**")
        nxt = text.find("\n- [", start + 1)
        return text[start - 6 : nxt if nxt != -1 else len(text)]

    # helpers for the common flow ---------------------------------------------------------
    def finish(self, tid: str, approval: bool = False) -> None:
        """start -> tick every subtask -> (verify) -> complete, via the CLI."""
        self.ok("start", tid)
        subs = re.findall(rf"\[[ x]\] ({re.escape(tid)}\.\d+) ", self.read("TASK_CHECKLIST.md"))
        if subs:
            self.ok("check", *subs)
        if approval:
            self.ok("verify", tid, "--evidence", "verified in test")
            self.ok("complete", tid, "--evidence", "approved in test", "--approved-by", "tester")
        else:
            self.ok("complete", tid, "--evidence", "done in test")


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    w = Workspace(tmp_path)
    w.write("TASK_CHECKLIST.md", build_checklist())
    w.write("QUALITY_GATES.md", build_register())
    w.write("PROGRESS_DASHBOARD.md", DASHBOARD)
    w.write("EXECUTION_LOG.md", LOG)
    assert "OK" in w.ok("validate")
    return w


@pytest.fixture
def track() -> ModuleType:
    spec = importlib.util.spec_from_file_location("track_under_test", TRACK)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
