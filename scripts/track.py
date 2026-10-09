#!/usr/bin/env python3
"""WealthSphere execution tracker.

Single writer for TASK_CHECKLIST.md, EXECUTION_LOG.md and the auto-generated block of
PROGRESS_DASHBOARD.md. Timestamps always come from the system clock (ISO 8601 with
timezone); they can never be passed in by hand. Standard library only.

Usage (run from the repository root):
  python scripts/track.py status
  python scripts/track.py next [--phase P05]
  python scripts/track.py start P01-T01 [P01-T02 ...]
  python scripts/track.py check P01-T01.1 [P01-T01.2 ...]
  python scripts/track.py verify P01-T01 --evidence "..."
  python scripts/track.py complete P01-T01 --evidence "..." [--approved-by "name"]
  python scripts/track.py block P01-T01 --reason "..."
  python scripts/track.py unblock P01-T01
  python scripts/track.py approve-phase P01 --by "name"
  python scripts/track.py dashboard
  python scripts/track.py validate
  python scripts/track.py qg status
  python scripts/track.py qg owner QG-06 --name "<name>"
  python scripts/track.py qg start QG-06
  python scripts/track.py qg check QG-06.2 [QG-06.3 ...] --evidence "..."
  python scripts/track.py qg uncheck QG-06.2 --reason "..."
  python scripts/track.py qg fail QG-06.2 --issue "..." [--blocks P06-T09,P06-GATE]
  python scripts/track.py qg block QG-04 --reason "..." [--blocks ...]
  python scripts/track.py qg resolve QG-06 --note "..."
  python scripts/track.py qg pass QG-06 --evidence "..." [--approved-by "name"]
  python scripts/track.py qg reverify QG-06 --evidence "..." [--approved-by "name"]
  python scripts/track.py qg waive QG-02.6 --justification "..." --approved-by "name" --risk-owner "name" --expires YYYY-MM-DD
  python scripts/track.py qg revoke-waiver W-001
  python scripts/track.py qg require QG-02.1 QG-03 QG-all@P13   # exit 1 if not satisfied (for CI)
Add --root <dir> to operate on a copy of the tracking files.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

STATUSES = {
    "NOT_STARTED": "⬜",
    "IN_PROGRESS": "🔄",
    "BLOCKED": "⛔",
    "AWAITING_VERIFICATION": "🔎",
    "COMPLETED": "✅",
}
TASK_ID = r"P\d\d-(?:T\d\d|GATE)"
TASK_RE = re.compile(rf"^- \[([ x])\] \*\*({TASK_ID})\*\* · (.*?) · `([A-Z_]+)`.*$")
SUB_RE = re.compile(rf"^  - \[([ x])\] ({TASK_ID}\.\d+) (.*)$")
PHASE_RE = re.compile(r"^## (P\d\d) — (.*)$")
APPROVAL_RE = re.compile(r"^- Phase approval: `(.*)`\s*$")
ISO_TZ_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")
CRLF, LF = chr(13) + chr(10), chr(10)
AUTO_BEGIN, AUTO_END = "<!-- AUTO:BEGIN -->", "<!-- AUTO:END -->"


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def fmt_duration(start: str, end: str) -> str:
    secs = int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())
    if secs < 0:
        return "n/a"
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m:02d}m {s:02d}s" if h else f"{m}m {s:02d}s"


class Task:
    def __init__(self, tid: str, phase: str, line_no: int):
        self.id, self.phase, self.line_no = tid, phase, line_no
        self.title = ""
        self.status = "NOT_STARTED"
        self.deps: list[str] = []
        self.wave = ""
        self.approval = False
        self.started = self.completed = self.duration = "—"
        self.evidence = "—"
        self.blocker = ""
        self.subs: list[tuple[int, bool, str, str]] = []  # (line_no, done, id, text)
        self.meta_line = self.timing_line = self.evidence_line = -1
        self.gs: list[str] = []   # quality-gate tokens required before the task may START
        self.gd: list[str] = []   # quality-gate tokens required before the task may be COMPLETED


class Checklist:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "TASK_CHECKLIST.md"
        self.lines = self.path.read_text(encoding="utf-8").replace(CRLF, LF).split("\n")
        self.tasks: dict[str, Task] = {}
        self.phases: dict[str, dict] = {}
        self._parse()

    def _parse(self) -> None:
        phase, cur = None, None
        for i, line in enumerate(self.lines):
            if m := PHASE_RE.match(line):
                phase, cur = m.group(1), None
                self.phases[phase] = {"title": m.group(2), "approval_line": -1, "approval": "PENDING"}
                continue
            if phase and (m := APPROVAL_RE.match(line)):
                self.phases[phase]["approval_line"] = i
                self.phases[phase]["approval"] = m.group(1)
                continue
            if m := TASK_RE.match(line):
                cur = Task(m.group(2), phase or "", i)
                cur.title, cur.status = m.group(3), m.group(4)
                self.tasks[cur.id] = cur
                continue
            if cur is None:
                continue
            if m := SUB_RE.match(line):
                cur.subs.append((i, m.group(1) == "x", m.group(2), m.group(3)))
            elif line.startswith("  - Deps:"):
                cur.meta_line = i
                parts = [p.strip() for p in line[len("  - "):].split(" · ")]
                kv = dict(p.split(": ", 1) for p in parts if ": " in p)
                deps = kv.get("Deps", "—")
                cur.deps = [] if deps in ("—", "") else [d.strip() for d in deps.split(",")]
                cur.wave = kv.get("Wave", "")
                cur.approval = kv.get("Approval", "no").lower().startswith("yes")
                _tok = lambda v: [] if v in ("—", "") else [x.strip() for x in v.split(",")]  # noqa: E731
                cur.gs = _tok(kv.get("Gates-start", "—"))
                cur.gd = _tok(kv.get("Gates-done", "—"))
            elif line.startswith("  - Started:"):
                cur.timing_line = i
                parts = [p.strip() for p in line[len("  - "):].split(" · ")]
                kv = dict(p.split(": ", 1) for p in parts if ": " in p)
                cur.started = kv.get("Started", "—")
                cur.completed = kv.get("Completed", "—")
                cur.duration = kv.get("Duration", "—")
                cur.blocker = "" if kv.get("Blocker", "—") == "—" else kv["Blocker"]
            elif line.startswith("  - Evidence:"):
                cur.evidence_line = i
                cur.evidence = line[len("  - Evidence: "):]

    # ----- writers (line-preserving) -----
    def _task_line(self, t: Task) -> str:
        box = "x" if t.status == "COMPLETED" else " "
        return f"- [{box}] **{t.id}** · {t.title} · `{t.status}` {STATUSES[t.status]}"

    def _timing(self, t: Task) -> str:
        return (f"  - Started: {t.started} · Completed: {t.completed} · Duration: {t.duration}"
                f" · Blocker: {t.blocker or '—'}")

    def flush(self, t: Task) -> None:
        self.lines[t.line_no] = self._task_line(t)
        self.lines[t.timing_line] = self._timing(t)
        self.lines[t.evidence_line] = f"  - Evidence: {t.evidence}"
        for ln, done, sid, text in t.subs:
            self.lines[ln] = f"  - [{'x' if done else ' '}] {sid} {text}"

    def save(self) -> None:
        self.path.write_text("\n".join(self.lines), encoding="utf-8", newline="\n")

    # ----- queries -----
    def phase_approved(self, phase: str) -> bool:
        return self.phases[phase]["approval"].startswith("APPROVED")

    def unmet_deps(self, t: Task) -> list[str]:
        return [d for d in t.deps if d not in self.tasks or self.tasks[d].status != "COMPLETED"]

    def eligible(self, t: Task) -> bool:
        return t.status == "NOT_STARTED" and self.phase_approved(t.phase) and not self.unmet_deps(t)


def log_append(root: Path, title: str, bullets: list[str]) -> None:
    path = root / "EXECUTION_LOG.md"
    text = path.read_text(encoding="utf-8").replace(CRLF, LF).rstrip("\n")
    entry = f"\n\n### {now()} — {title}\n" + "\n".join(f"- {b}" for b in bullets)
    path.write_text(text + entry + "\n", encoding="utf-8", newline="\n")


# ------------------------------------------------------------------ commands
def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def get(cl: Checklist, tid: str) -> Task:
    if tid not in cl.tasks:
        die(f"unknown task id {tid}")
    return cl.tasks[tid]


def cmd_start(cl: Checklist, args) -> None:
    ts = now()
    for tid in args.ids:
        t = get(cl, tid)
        if t.status != "NOT_STARTED":
            die(f"{tid} is {t.status}, expected NOT_STARTED (use unblock for BLOCKED tasks)")
        if not cl.phase_approved(t.phase):
            die(f"{tid}: phase {t.phase} is not approved ({cl.phases[t.phase]['approval']}). "
                f"Run: approve-phase {t.phase} --by <name> after the user approves it")
        unmet = cl.unmet_deps(t)
        if unmet:
            die(f"{tid}: prerequisites not COMPLETED: {', '.join(unmet)}")
        reg = Register.load(cl.root)
        if reg is None and (t.gs or t.gd):
            die(f"{tid}: QUALITY_GATES.md is missing, so its quality gates cannot be verified")
        if reg:
            if (g := reg.blocking(tid)):
                die(f"{tid}: blocked by failed/blocked quality gate(s) {', '.join(g)}; resolve and re-verify first")
            if (un := reg.unsatisfied(t.gs)):
                die(f"{tid}: start gates not satisfied: {short(un)}")
    for tid in args.ids:
        t = cl.tasks[tid]
        t.status, t.started = "IN_PROGRESS", ts
        t.completed = t.duration = "—"
        cl.flush(t)
        print(f"{tid} started {ts}")
    cl.save()
    for tid in args.ids:
        log_append(cl.root, f"START {tid}", [f"{cl.tasks[tid].title}", "prerequisites verified COMPLETED"])


def cmd_check(cl: Checklist, args) -> None:
    for sid in args.ids:
        tid = sid.rsplit(".", 1)[0]
        t = get(cl, tid)
        if t.status not in ("IN_PROGRESS", "AWAITING_VERIFICATION"):
            die(f"{sid}: task {tid} is {t.status}; subtasks can only be ticked while it is in progress")
        for k, (ln, done, s, text) in enumerate(t.subs):
            if s == sid:
                t.subs[k] = (ln, True, s, text)
                break
        else:
            die(f"unknown subtask {sid}")
        cl.flush(t)
    cl.save()
    print("ticked:", ", ".join(args.ids))


def _require_subs(t: Task) -> None:
    open_subs = [s for _, d, s, _ in t.subs if not d]
    if open_subs:
        die(f"{t.id}: unticked subtasks: {', '.join(open_subs)}")


def _require_evidence(evidence: str) -> None:
    if not evidence.strip() or evidence.strip() in ("—", "-"):
        die("--evidence is required (commands run, results, commit/PR reference)")


def cmd_verify(cl: Checklist, args) -> None:
    t = get(cl, args.id)
    if t.status != "IN_PROGRESS":
        die(f"{t.id} is {t.status}, expected IN_PROGRESS")
    _require_subs(t)
    _require_evidence(args.evidence)
    t.status, t.evidence = "AWAITING_VERIFICATION", args.evidence
    cl.flush(t)
    cl.save()
    log_append(cl.root, f"AWAITING_VERIFICATION {t.id}", [f"evidence: {args.evidence}"])
    print(f"{t.id} awaiting verification")


def cmd_complete(cl: Checklist, args) -> None:
    t = get(cl, args.id)
    if t.approval:
        if t.status != "AWAITING_VERIFICATION":
            die(f"{t.id} requires user approval: run verify first, then complete --approved-by <name>")
        if not args.approved_by:
            die(f"{t.id} requires --approved-by <name> (user approval)")
    elif t.status not in ("IN_PROGRESS", "AWAITING_VERIFICATION"):
        die(f"{t.id} is {t.status}; cannot complete")
    _require_evidence(args.evidence)
    _require_subs(t)
    reg = Register.load(cl.root)
    if reg is None and (t.gs or t.gd):
        die(f"{t.id}: QUALITY_GATES.md is missing, so its quality gates cannot be verified")
    if reg:
        if (g := reg.blocking(t.id)):
            die(f"{t.id}: blocked by failed/blocked quality gate(s) {', '.join(g)}")
        if (un := reg.unsatisfied(t.gd)):
            die(f"{t.id}: quality-gate criteria not satisfied: {short(un)}. "
                "Verify them with `qg check` (evidence required) or an approved waiver first")
    ts = now()
    t.status, t.completed = "COMPLETED", ts
    t.duration = fmt_duration(t.started, ts) if ISO_TZ_RE.match(t.started) else "n/a (start not recorded)"
    ev = args.evidence + (f" · Approved by: {args.approved_by}" if args.approved_by else "")
    t.evidence = ev
    cl.flush(t)
    cl.save()
    log_append(cl.root, f"COMPLETE {t.id}", [f"duration: {t.duration}", f"evidence: {ev}"])
    print(f"{t.id} completed {ts} ({t.duration})")


def cmd_block(cl: Checklist, args) -> None:
    t = get(cl, args.id)
    if t.status not in ("IN_PROGRESS", "AWAITING_VERIFICATION", "NOT_STARTED"):
        die(f"{t.id} is {t.status}; cannot block")
    t.status, t.blocker = "BLOCKED", args.reason
    cl.flush(t)
    cl.save()
    log_append(cl.root, f"BLOCKED {t.id}", [f"reason: {args.reason}"])
    print(f"{t.id} blocked")


def cmd_unblock(cl: Checklist, args) -> None:
    t = get(cl, args.id)
    if t.status != "BLOCKED":
        die(f"{t.id} is {t.status}, not BLOCKED")
    t.status = "IN_PROGRESS" if ISO_TZ_RE.match(t.started) else "NOT_STARTED"
    old, t.blocker = t.blocker, ""
    cl.flush(t)
    cl.save()
    log_append(cl.root, f"UNBLOCKED {t.id}", [f"resolved: {old}", f"status now {t.status}"])
    print(f"{t.id} -> {t.status}")


def cmd_approve_phase(cl: Checklist, args) -> None:
    p = args.phase
    if p not in cl.phases:
        die(f"unknown phase {p}")
    ts = now()
    cl.lines[cl.phases[p]["approval_line"]] = f"- Phase approval: `APPROVED by {args.by} at {ts}`"
    cl.save()
    log_append(cl.root, f"PHASE APPROVED {p}", [f"approved by {args.by}", cl.phases[p]["title"]])
    print(f"{p} approved")


def cmd_next(cl: Checklist, args) -> None:
    rows = [t for t in cl.tasks.values() if cl.eligible(t) and (not args.phase or t.phase == args.phase)]
    if not rows:
        print("No eligible tasks. Check: phase approvals, unmet prerequisites, tasks awaiting verification.")
    for t in rows:
        print(f"{t.id}  {t.wave}  {t.title}")


def cmd_status(cl: Checklist, args) -> None:
    block = render_dashboard(cl)
    print(block)


# --------------------------------------------------------------- dashboard
def render_dashboard(cl: Checklist) -> str:
    tasks = list(cl.tasks.values())
    total = len(tasks)
    by = {s: [t for t in tasks if t.status == s] for s in STATUSES}
    subs_total = sum(len(t.subs) for t in tasks)
    subs_done = sum(1 for t in tasks for s in t.subs if s[1])
    pct = lambda a, b: f"{(100 * a / b):.1f}%" if b else "n/a"  # noqa: E731
    order = list(cl.phases)
    current = next(
        (p for p in order if cl.phase_approved(p) and any(t.status != "COMPLETED" for t in tasks if t.phase == p)),
        None,
    )
    out = [f"_Generated by `scripts/track.py dashboard` at **{now()}**. Do not edit between the AUTO markers._", ""]
    out += ["### Overall", "", "| Metric | Value |", "|---|---|"]
    out += [
        f"| Phases | {len(order)} ({sum(1 for p in order if all(t.status == 'COMPLETED' for t in tasks if t.phase == p))} complete) |",
        f"| Tasks (incl. phase gates) | {total} |",
        f"| ✅ Completed | {len(by['COMPLETED'])} |",
        f"| 🔄 In progress | {len(by['IN_PROGRESS'])} |",
        f"| 🔎 Awaiting verification | {len(by['AWAITING_VERIFICATION'])} |",
        f"| ⛔ Blocked | {len(by['BLOCKED'])} |",
        f"| ⬜ Not started | {len(by['NOT_STARTED'])} |",
        f"| **Overall completion (tasks)** | **{pct(len(by['COMPLETED']), total)}** |",
        f"| Subtasks ticked | {subs_done} / {subs_total} ({pct(subs_done, subs_total)}) |",
        f"| Current phase | {current + ' — ' + cl.phases[current]['title'] if current else 'none approved/active'} |",
        "",
    ]
    out += ["### Phases", "", "| Phase | Title | Approval | Done | In prog. | Awaiting | Blocked | Complete |", "|---|---|---|---|---|---|---|---|"]
    for p in order:
        pt = [t for t in tasks if t.phase == p]
        c = lambda s: sum(1 for t in pt if t.status == s)  # noqa: E731
        appr = cl.phases[p]["approval"].split(" at ")[0]
        out.append(f"| {p} | {cl.phases[p]['title']} | {appr} | {c('COMPLETED')}/{len(pt)} | {c('IN_PROGRESS')} | {c('AWAITING_VERIFICATION')} | {c('BLOCKED')} | {pct(c('COMPLETED'), len(pt))} |")
    out.append("")
    out += ["### Next executable tasks", ""]
    nxt = [t for t in tasks if cl.eligible(t)]
    if nxt:
        out += [f"- `{t.id}` ({t.wave}) {t.title}" for t in nxt[:20]]
        if len(nxt) > 20:
            out.append(f"- … and {len(nxt) - 20} more (`python scripts/track.py next`)")
    else:
        out.append("- None. Reasons: phases awaiting approval, prerequisites incomplete, or tasks awaiting verification.")
    ready_unapproved = sorted({t.phase for t in tasks if t.status == "NOT_STARTED" and not cl.phase_approved(t.phase) and not cl.unmet_deps(t)})
    if ready_unapproved:
        out += ["", f"Prerequisites satisfied but **phase approval pending**: {', '.join(ready_unapproved)}"]
    out.append("")
    for title, key in (("In progress", "IN_PROGRESS"), ("Awaiting verification / user approval", "AWAITING_VERIFICATION"), ("Blocked", "BLOCKED")):
        out += [f"### {title}", ""]
        items = by[key]
        out += [f"- `{t.id}` {t.title}" + (f" — **{t.blocker}**" if key == "BLOCKED" and t.blocker else "") for t in items] or ["- None"]
        out.append("")
    reg = Register.load(cl.root)
    if reg:
        out += ["### Quality gates (see QUALITY_GATES.md)", "", render_qg_summary(reg, cl), ""]
    return "\n".join(out)


def cmd_dashboard(cl: Checklist, args) -> None:
    path = cl.root / "PROGRESS_DASHBOARD.md"
    text = path.read_text(encoding="utf-8").replace(CRLF, LF)
    if AUTO_BEGIN not in text or AUTO_END not in text:
        die("PROGRESS_DASHBOARD.md is missing AUTO markers")
    head, rest = text.split(AUTO_BEGIN, 1)
    _, tail = rest.split(AUTO_END, 1)
    path.write_text(head + AUTO_BEGIN + "\n" + render_dashboard(cl) + "\n" + AUTO_END + tail, encoding="utf-8", newline="\n")
    print("dashboard updated")


# ---------------------------------------------------------------- validate
def cmd_validate(cl: Checklist, args) -> None:
    errs: list[str] = []
    seen_lines = [l for l in cl.lines if TASK_RE.match(l)]
    if len(seen_lines) != len(cl.tasks):
        errs.append("duplicate task ids")
    for t in cl.tasks.values():
        if t.status not in STATUSES:
            errs.append(f"{t.id}: bad status {t.status}")
        box = cl.lines[t.line_no][3]
        if (box == "x") != (t.status == "COMPLETED"):
            errs.append(f"{t.id}: checkbox/status mismatch")
        if min(t.meta_line, t.timing_line, t.evidence_line) < 0:
            errs.append(f"{t.id}: missing Deps/Started/Evidence line")
        for d in t.deps:
            if d not in cl.tasks:
                errs.append(f"{t.id}: unknown dependency {d}")
            elif cl.tasks[d].phase == t.phase and cl.tasks[d].wave >= t.wave and d != t.id and t.wave != "GATE":
                errs.append(f"{t.id}: dependency {d} not in an earlier wave")
        if t.status == "COMPLETED":
            if not ISO_TZ_RE.match(t.completed):
                errs.append(f"{t.id}: COMPLETED without ISO8601+tz Completed timestamp")
            if t.evidence in ("—", ""):
                errs.append(f"{t.id}: COMPLETED without evidence")
            if any(not d for _, d, _, _ in t.subs):
                errs.append(f"{t.id}: COMPLETED with unticked subtasks")
            for d in t.deps:
                if d in cl.tasks and cl.tasks[d].status != "COMPLETED":
                    errs.append(f"{t.id}: COMPLETED but prerequisite {d} is {cl.tasks[d].status}")
        if (t.status in ("IN_PROGRESS", "AWAITING_VERIFICATION") and not ISO_TZ_RE.match(t.started)
                and not t.started.startswith("not recorded")):
            errs.append(f"{t.id}: {t.status} without a recorded Started timestamp")
        if t.status == "NOT_STARTED" and (t.started != "—" or t.completed != "—"):
            errs.append(f"{t.id}: NOT_STARTED but has timestamps")
    warns: list[str] = []
    validate_qg(cl, errs, warns)
    # cycle check
    state: dict[str, int] = {}

    def visit(n: str, path: list[str]) -> None:
        if state.get(n) == 2:
            return
        if state.get(n) == 1:
            errs.append("dependency cycle: " + " -> ".join(path + [n]))
            return
        state[n] = 1
        for d in cl.tasks[n].deps:
            if d in cl.tasks:
                visit(d, path + [n])
        state[n] = 2

    for n in cl.tasks:
        visit(n, [])
    if errs:
        for w in warns:
            print("WARNING:", w)
        print("VALIDATION FAILED")
        for e in errs:
            print(" -", e)
        raise SystemExit(1)
    for w in warns:
        print("WARNING:", w)
    reg = Register.load(cl.root)
    extra = f", {len(reg.titles)} quality gates / {len(reg.crits)} criteria" if reg else ""
    print(f"OK: {len(cl.tasks)} tasks, {len(cl.phases)} phases{extra}, no cycles, status/checkbox/timestamp/gate rules satisfied")



# ===================================================================== quality gates
GATE_HEAD_RE = re.compile(r"^### (QG-\d\d): (.*)$")
CRIT_RE = re.compile(r"^- \[([ x])\] (QG-\d\d\.\d+) (.*)$")
FIELD_KEYS = ["Status", "Owner", "Start Timestamp", "End Timestamp", "Verification Timestamp",
              "Evidence", "Blocking Issues", "Blocks", "Approved By"]
FIELD_RE = re.compile(r"^(" + "|".join(re.escape(k) for k in FIELD_KEYS) + r"): ?(.*?)\s*$")
GATE_STATUSES = ["NOT_STARTED", "IN_PROGRESS", "BLOCKED", "FAILED", "PASSED", "WAIVED"]
GATE_ICON = {"NOT_STARTED": "⬜", "IN_PROGRESS": "🔄", "BLOCKED": "⛔", "FAILED": "❌", "PASSED": "✅", "WAIVED": "⚠️"}
META_ORDER = ["Required", "By", "Evidence", "Verified", "WAIVED"]
QG_BEGIN, QG_END = "<!-- QG-AUTO:BEGIN -->", "<!-- QG-AUTO:END -->"
WAIVER_BEGIN, WAIVER_END = "<!-- WAIVERS:BEGIN -->", "<!-- WAIVERS:END -->"
TOKEN_RE = re.compile(r"^(QG-\d\d(?:\.\d+)?|QG-all@P\d\d)$")


def short(items: list[str], n: int = 12) -> str:
    return ", ".join(items[:n]) + (f" (+{len(items) - n} more; run `qg status`)" if len(items) > n else "")


def clean(text: str) -> str:
    return " ".join(text.replace(" · ", "; ").replace("|", "/").split())


class Criterion:
    def __init__(self, cid, gate, line, done, text, meta, flags):
        self.id, self.gate, self.line, self.done = cid, gate, line, done
        self.text, self.meta, self.flags = text, meta, flags

    @property
    def critical(self) -> bool:
        return "CRITICAL" in self.flags

    @property
    def required_phase(self) -> int:
        return int(self.meta.get("Required", "P99")[1:])

    def render(self) -> str:
        parts = f"- [{'x' if self.done else ' '}] {self.id} {self.text}"
        for k in META_ORDER:
            if k in self.meta:
                parts += f" · {k}: {self.meta[k]}"
        if self.critical:
            parts += " · CRITICAL"
        return parts


class Register:
    def __init__(self, root: Path):
        self.root = root
        self.path = root / "QUALITY_GATES.md"
        self.lines = self.path.read_text(encoding="utf-8").replace(CRLF, LF).split("\n")
        self.titles: dict[str, str] = {}
        self.crits: dict[str, Criterion] = {}
        self.fields: dict[str, dict[str, int]] = {}
        self.waivers: dict[str, dict] = {}
        self.waiver_lines: dict[str, int] = {}
        gate = None
        in_waivers = False
        for i, line in enumerate(self.lines):
            if WAIVER_BEGIN in line:
                in_waivers = True
            elif WAIVER_END in line:
                in_waivers = False
            if in_waivers and line.startswith("| W-"):
                c = [x.strip() for x in line.strip().strip("|").split("|")]
                self.waivers[c[0]] = dict(criterion=c[1], justification=c[2], approved_by=c[3], risk_owner=c[4],
                                          granted=c[5], expires=c[6], status=c[7])
                self.waiver_lines[c[0]] = i
                continue
            if m := GATE_HEAD_RE.match(line):
                gate = m.group(1)
                self.titles[gate] = m.group(2)
                self.fields[gate] = {}
                continue
            if gate is None:
                continue
            if m := CRIT_RE.match(line):
                parts = m.group(3).split(" · ")
                meta, flags = {}, set()
                for p in parts[1:]:
                    if ": " in p:
                        k, v = p.split(": ", 1)
                        meta[k] = v
                    else:
                        flags.add(p)
                self.crits[m.group(2)] = Criterion(m.group(2), gate, i, m.group(1) == "x", parts[0], meta, flags)
            elif m := FIELD_RE.match(line):
                self.fields[gate][m.group(1)] = i

    @staticmethod
    def load(root: Path):
        return Register(root) if (root / "QUALITY_GATES.md").exists() else None

    # --- field access
    def get(self, gate: str, key: str) -> str:
        return FIELD_RE.match(self.lines[self.fields[gate][key]]).group(2)

    def set(self, gate: str, key: str, value: str) -> None:
        ln = self.fields[gate][key]
        suffix = "" if key == "Approved By" else "  "
        self.lines[ln] = f"{key}: {value}{suffix}"

    def flush(self, c: Criterion) -> None:
        self.lines[c.line] = c.render()

    def save(self) -> None:
        self.path.write_text("\n".join(self.lines), encoding="utf-8", newline="\n")

    # --- queries
    def gate_crits(self, gate: str) -> list[Criterion]:
        return [c for c in self.crits.values() if c.gate == gate]

    def active_waiver(self, cid: str):
        today = datetime.now().astimezone().date()
        for wid, w in self.waivers.items():
            if w["criterion"] == cid and w["status"] == "ACTIVE":
                try:
                    if datetime.fromisoformat(w["expires"]).date() >= today:
                        return wid
                except ValueError:
                    pass
        return None

    def satisfied(self, c: Criterion) -> bool:
        return c.done or self.active_waiver(c.id) is not None

    def expand(self, token: str) -> list[Criterion]:
        if token in self.crits:
            return [self.crits[token]]
        if re.fullmatch(r"QG-\d\d", token) and token in self.titles:
            return self.gate_crits(token)
        if m := re.fullmatch(r"QG-all@P(\d\d)", token):
            lim = int(m.group(1))
            return [c for c in self.crits.values() if c.gate != "QG-12" and c.required_phase <= lim]
        raise KeyError(token)

    def unsatisfied(self, tokens: list[str]) -> list[str]:
        out: list[str] = []
        for t in tokens:
            try:
                out += [c.id for c in self.expand(t) if not self.satisfied(c)]
            except KeyError:
                out.append(f"{t} (unknown)")
        return sorted(set(out))

    def blocking(self, task_id: str) -> list[str]:
        res = []
        for g in self.titles:
            if self.get(g, "Status") in ("FAILED", "BLOCKED") and task_id in [x.strip() for x in self.get(g, "Blocks").split(",")]:
                res.append(g)
        return res

    def summary_counts(self, gate: str) -> tuple[int, int]:
        cs = self.gate_crits(gate)
        return sum(1 for c in cs if self.satisfied(c)), len(cs)


def render_qg_summary(reg: Register, cl: Checklist | None = None) -> str:
    out = ["| Gate | Name | Status | Criteria satisfied | Owner | Blocking issues |", "|---|---|---|---|---|---|"]
    for g, title in reg.titles.items():
        st = reg.get(g, "Status")
        a, b = reg.summary_counts(g)
        out.append(f"| {g} | {title} | {GATE_ICON.get(st, '')} {st} | {a}/{b} | {reg.get(g, 'Owner')} | {reg.get(g, 'Blocking Issues')} |")
    today = datetime.now().astimezone().date()
    active = [w for w, d in reg.waivers.items() if d["status"] == "ACTIVE"]
    expired = [w for w in active if datetime.fromisoformat(reg.waivers[w]["expires"]).date() < today]
    out += ["", f"Waivers: {len(active)} active ({len(expired)} expired — must be resolved), {len(reg.waivers) - len(active)} closed.",
            f"Criteria satisfied overall: {sum(1 for c in reg.crits.values() if reg.satisfied(c))}/{len(reg.crits)}."]
    if cl:
        cur = next((p for p in cl.phases if cl.phase_approved(p) and any(t.status != 'COMPLETED' for t in cl.tasks.values() if t.phase == p)), None)
        if cur and f"{cur}-GATE" in cl.tasks:
            gt = cl.tasks[f"{cur}-GATE"]
            un = reg.unsatisfied(gt.gd)
            out += ["", f"Current phase **{cur}** exit-gate criteria outstanding: " + (", ".join(un) if un else "none") + "."]
    return "\n".join(out)


def refresh_qg(root: Path) -> None:
    reg = Register.load(root)
    if not reg:
        return
    cl = Checklist(root)
    text = "\n".join(reg.lines)
    if QG_BEGIN in text and QG_END in text:
        head, rest = text.split(QG_BEGIN, 1)
        _, tail = rest.split(QG_END, 1)
        text = head + QG_BEGIN + "\n" + f"_Generated at {now()} by `scripts/track.py`._\n\n" + render_qg_summary(reg, cl) + "\n" + QG_END + tail
        reg.path.write_text(text, encoding="utf-8", newline="\n")


def need_reg(cl: Checklist) -> Register:
    reg = Register.load(cl.root)
    if not reg:
        die("QUALITY_GATES.md not found")
    return reg


def qg_log(root: Path, title: str, bullets: list[str]) -> None:
    log_append(root, title, bullets)


def cmd_qg(cl: Checklist, args) -> None:
    reg = need_reg(cl)
    ts = now()
    a = args.qgcmd
    mutated = True
    if a == "status":
        mutated = False
        print(render_qg_summary(reg, cl))
    elif a == "require":
        mutated = False
        un = reg.unsatisfied(args.tokens)
        if un:
            print("NOT SATISFIED:", ", ".join(un))
            raise SystemExit(1)
        print("satisfied:", ", ".join(args.tokens))
    elif a == "owner":
        if args.gate not in reg.titles:
            die(f"unknown gate {args.gate}")
        reg.set(args.gate, "Owner", clean(args.name))
        reg.save()
        qg_log(cl.root, f"QG OWNER {args.gate}", [f"owner: {args.name}"])
    elif a == "start":
        g = args.gate
        if g not in reg.titles:
            die(f"unknown gate {g}")
        if reg.get(g, "Status") != "NOT_STARTED":
            die(f"{g} is {reg.get(g, 'Status')}")
        reg.set(g, "Status", "IN_PROGRESS")
        reg.set(g, "Start Timestamp", ts)
        reg.save()
        qg_log(cl.root, f"QG START {g}", [reg.titles[g]])
    elif a == "check":
        if not args.evidence.strip():
            die("--evidence required (commands run, results, report path)")
        for cid in args.ids:
            if cid not in reg.crits:
                die(f"unknown criterion {cid}")
            c = reg.crits[cid]
            g = c.gate
            st = reg.get(g, "Status")
            if st in ("FAILED", "BLOCKED"):
                die(f"{g} is {st}; run `qg resolve {g}` after remediation first")
            if cid == "QG-12.1":
                un = reg.unsatisfied(["QG-all@P13"])
                if un:
                    die("QG-12.1 requires every QG-01..QG-11 criterion due by P13; unsatisfied: " + short(un))
            c.done = True
            c.meta["Evidence"] = clean(args.evidence)
            c.meta["Verified"] = ts
            if "WAIVED" in c.meta:
                w = c.meta.pop("WAIVED")
                if w in reg.waivers:
                    reg.waivers[w]["status"] = "SUPERSEDED"
                    _rewrite_waiver(reg, w)
            reg.flush(c)
            if st == "NOT_STARTED":
                reg.set(g, "Status", "IN_PROGRESS")
                reg.set(g, "Start Timestamp", ts)
            x, y = reg.summary_counts(g)
            reg.set(g, "Verification Timestamp", ts)
            reg.set(g, "Evidence", f"{x}/{y} criteria verified; latest {cid} at {ts}")
        reg.save()
        qg_log(cl.root, "QG CHECK " + ", ".join(args.ids), [f"evidence: {clean(args.evidence)}"])
    elif a == "uncheck":
        c = reg.crits.get(args.id) or die(f"unknown criterion {args.id}")
        c.done = False
        c.meta.pop("Evidence", None)
        c.meta.pop("Verified", None)
        reg.flush(c)
        if reg.get(c.gate, "Status") in ("PASSED", "WAIVED"):
            reg.set(c.gate, "Status", "IN_PROGRESS")
            reg.set(c.gate, "End Timestamp", "—")
        reg.save()
        qg_log(cl.root, f"QG UNCHECK {args.id}", [f"reason: {clean(args.reason)}"])
    elif a == "fail":
        c = reg.crits.get(args.id) or die(f"unknown criterion {args.id}")
        g = c.gate
        c.done = False
        c.meta.pop("Evidence", None)
        c.meta.pop("Verified", None)
        reg.flush(c)
        old = reg.get(g, "Blocking Issues")
        issue = f"{c.id}: {clean(args.issue)}"
        reg.set(g, "Blocking Issues", issue if old in ("—", "") else f"{old}; {issue}")
        blocks = [x.strip() for x in reg.get(g, "Blocks").split(",") if x.strip() and x.strip() != "—"]
        for b in (args.blocks or "").split(","):
            if b.strip() and b.strip() not in blocks:
                blocks.append(b.strip())
        reg.set(g, "Blocks", ", ".join(blocks) or "—")
        if reg.get(g, "Start Timestamp") in ("—", ""):
            reg.set(g, "Start Timestamp", ts)
        reg.set(g, "Status", "FAILED")
        reg.set(g, "End Timestamp", "—")
        reg.set(g, "Verification Timestamp", ts)
        reg.save()
        qg_log(cl.root, f"QG FAILED {args.id}", [f"issue: {clean(args.issue)}", f"blocks: {args.blocks or '—'}"])
    elif a == "block":
        g = args.gate
        if g not in reg.titles:
            die(f"unknown gate {g}")
        if reg.get(g, "Start Timestamp") in ("—", ""):
            reg.set(g, "Start Timestamp", ts)
        reg.set(g, "Status", "BLOCKED")
        reg.set(g, "Blocking Issues", clean(args.reason))
        if args.blocks:
            reg.set(g, "Blocks", args.blocks)
        reg.save()
        qg_log(cl.root, f"QG BLOCKED {g}", [f"reason: {clean(args.reason)}"])
    elif a == "resolve":
        g = args.gate
        if reg.get(g, "Status") not in ("FAILED", "BLOCKED"):
            die(f"{g} is {reg.get(g, 'Status')}, not FAILED/BLOCKED")
        old = reg.get(g, "Blocking Issues")
        reg.set(g, "Status", "IN_PROGRESS")
        reg.set(g, "Blocking Issues", "—")
        reg.set(g, "Blocks", "—")
        reg.save()
        qg_log(cl.root, f"QG RESOLVED {g}", [f"was: {old}", f"note: {clean(args.note)}", "failed checks must be re-run: use `qg check` with fresh evidence"])
    elif a in ("pass", "reverify"):
        g = args.gate
        if g not in reg.titles:
            die(f"unknown gate {g}")
        un = [c.id for c in reg.gate_crits(g) if not reg.satisfied(c)]
        if un:
            die(f"{g}: criteria not satisfied: {', '.join(un)}")
        if reg.get(g, "Status") in ("FAILED", "BLOCKED"):
            die(f"{g} is {reg.get(g, 'Status')}; resolve first")
        waived = [c.id for c in reg.gate_crits(g) if not c.done]
        if (g == "QG-12" or waived) and not args.approved_by:
            die(f"{g} requires --approved-by" + (" (waived criteria present)" if waived else ""))
        if not args.evidence.strip():
            die("--evidence required")
        if a == "reverify" and reg.get(g, "Status") not in ("PASSED", "WAIVED"):
            die(f"{g} is not PASSED/WAIVED; use `qg pass`")
        reg.set(g, "Status", "WAIVED" if waived else "PASSED")
        if a == "pass" or reg.get(g, "End Timestamp") in ("—", ""):
            reg.set(g, "End Timestamp", ts)
        reg.set(g, "Verification Timestamp", ts)
        reg.set(g, "Evidence", clean(args.evidence))
        if args.approved_by:
            reg.set(g, "Approved By", clean(args.approved_by))
        if reg.get(g, "Start Timestamp") in ("—", ""):
            reg.set(g, "Start Timestamp", ts)
        reg.save()
        qg_log(cl.root, f"QG {'PASSED' if not waived else 'WAIVED'} {g}", [f"evidence: {clean(args.evidence)}"] + ([f"approved by {args.approved_by}"] if args.approved_by else []))
    elif a == "waive":
        c = reg.crits.get(args.id) or die(f"unknown criterion {args.id}")
        if c.critical:
            die(f"{c.id} is CRITICAL (security / financial-integrity / authorization). The tracker never waives these; "
                "record a user-approved plan change in EXECUTION_LOG.md instead.")
        try:
            exp = datetime.fromisoformat(args.expires).date()
        except ValueError:
            die("--expires must be YYYY-MM-DD")
        if exp <= datetime.now().astimezone().date():
            die("--expires must be a future date")
        n = len(reg.waivers) + 1
        wid = f"W-{n:03d}"
        row = f"| {wid} | {c.id} | {clean(args.justification)} | {clean(args.approved_by)} | {clean(args.risk_owner)} | {ts} | {exp.isoformat()} | ACTIVE |"
        end = next(i for i, l in enumerate(reg.lines) if WAIVER_END in l)
        reg.lines.insert(end, row)
        c.meta["WAIVED"] = wid
        c.done = False
        reg.flush(c)
        if reg.get(c.gate, "Status") == "NOT_STARTED":
            reg.set(c.gate, "Status", "IN_PROGRESS")
            reg.set(c.gate, "Start Timestamp", ts)
        reg.save()
        qg_log(cl.root, f"QG WAIVER {wid} for {c.id}", [f"justification: {clean(args.justification)}", f"approved by {args.approved_by}; risk owner {args.risk_owner}; expires {exp}"])
    elif a == "revoke-waiver":
        w = reg.waivers.get(args.id) or die(f"unknown waiver {args.id}")
        w["status"] = "REVOKED"
        _rewrite_waiver(reg, args.id)
        c = reg.crits[w["criterion"]]
        c.meta.pop("WAIVED", None)
        reg.flush(c)
        if reg.get(c.gate, "Status") in ("PASSED", "WAIVED"):
            reg.set(c.gate, "Status", "IN_PROGRESS")
            reg.set(c.gate, "End Timestamp", "—")
        reg.save()
        qg_log(cl.root, f"QG WAIVER REVOKED {args.id}", [f"criterion {c.id} is unsatisfied again"])
    if mutated:
        refresh_qg(cl.root)
        cmd_dashboard(Checklist(cl.root), args)


def _rewrite_waiver(reg: Register, wid: str) -> None:
    w = reg.waivers[wid]
    reg.lines[reg.waiver_lines[wid]] = (f"| {wid} | {w['criterion']} | {w['justification']} | {w['approved_by']} | "
                                        f"{w['risk_owner']} | {w['granted']} | {w['expires']} | {w['status']} |")


def validate_qg(cl: Checklist, errs: list[str], warns: list[str]) -> None:
    reg = Register.load(cl.root)
    if not reg:
        if any(t.gs or t.gd for t in cl.tasks.values()):
            errs.append("QUALITY_GATES.md is missing but tasks reference quality gates (enforcement would be off)")
        return
    if len(reg.titles) != 12:
        errs.append(f"QUALITY_GATES.md: expected 12 gates, found {len(reg.titles)}")
    for g in reg.titles:
        for k in FIELD_KEYS:
            if k not in reg.fields[g]:
                errs.append(f"{g}: missing field {k}")
        if any(k not in reg.fields[g] for k in FIELD_KEYS):
            continue
        st = reg.get(g, "Status")
        if st not in GATE_STATUSES:
            errs.append(f"{g}: bad status {st}")
        cs = reg.gate_crits(g)
        if not cs:
            errs.append(f"{g}: no criteria")
        if st in ("PASSED", "WAIVED"):
            for c in cs:
                if not reg.satisfied(c):
                    errs.append(f"{g} is {st} but {c.id} is not satisfied")
            for k in ("Start Timestamp", "End Timestamp", "Verification Timestamp"):
                if not ISO_TZ_RE.match(reg.get(g, k)):
                    errs.append(f"{g}: {st} without ISO8601+tz {k}")
            if reg.get(g, "Evidence") in ("—", ""):
                errs.append(f"{g}: {st} without evidence")
            if (g == "QG-12" or st == "WAIVED") and reg.get(g, "Approved By") in ("—", ""):
                errs.append(f"{g}: {st} without Approved By")
        if st == "IN_PROGRESS" and not ISO_TZ_RE.match(reg.get(g, "Start Timestamp")):
            errs.append(f"{g}: IN_PROGRESS without Start Timestamp")
        if st == "NOT_STARTED" and any(c.done for c in cs):
            errs.append(f"{g}: NOT_STARTED but has verified criteria")
        if st in ("FAILED", "BLOCKED") and reg.get(g, "Blocking Issues") in ("—", ""):
            errs.append(f"{g}: {st} without Blocking Issues")
        for b in [x.strip() for x in reg.get(g, "Blocks").split(",") if x.strip() and x.strip() != "—"]:
            if b not in cl.tasks:
                errs.append(f"{g}: Blocks unknown task {b}")
    for c in reg.crits.values():
        if c.done:
            if "Evidence" not in c.meta or not ISO_TZ_RE.match(c.meta.get("Verified", "")):
                errs.append(f"{c.id}: verified without Evidence and ISO8601+tz Verified timestamp")
        for by in c.meta.get("By", "").split(","):
            if by.strip() and by.strip() not in cl.tasks:
                errs.append(f"{c.id}: evidence task {by.strip()} does not exist")
    today = datetime.now().astimezone().date()
    for wid, w in reg.waivers.items():
        c = reg.crits.get(w["criterion"])
        if not c:
            errs.append(f"{wid}: unknown criterion {w['criterion']}")
            continue
        if c.critical:
            errs.append(f"{wid}: waiver on CRITICAL criterion {c.id} is not allowed")
        if w["status"] == "ACTIVE":
            try:
                if datetime.fromisoformat(w["expires"]).date() < today:
                    errs.append(f"{wid}: waiver for {c.id} expired {w['expires']}")
            except ValueError:
                errs.append(f"{wid}: bad expiry")
            if not (w["justification"] and w["approved_by"] and w["risk_owner"]):
                errs.append(f"{wid}: waiver needs justification, approver and risk owner")
    for t in cl.tasks.values():
        for tok in t.gs + t.gd:
            if not TOKEN_RE.match(tok):
                errs.append(f"{t.id}: bad gate token {tok}")
                continue
            try:
                reg.expand(tok)
            except KeyError:
                errs.append(f"{t.id}: unknown gate/criterion {tok}")
        if t.status == "COMPLETED":
            un = reg.unsatisfied(t.gd)
            if un:
                warns.append(f"{t.id} is COMPLETED but gate criteria are no longer satisfied: {', '.join(un)} (regression: re-verify before relying on this phase)")
    for p in cl.phases:
        g = cl.tasks.get(f"{p}-GATE")
        if g is None:
            errs.append(f"{p}: missing phase gate task")
    # every criterion is required by exactly one phase exit gate or release task
    bound = set()
    for t in cl.tasks.values():
        for tok in t.gd + t.gs:
            try:
                bound.update(c.id for c in reg.expand(tok))
            except KeyError:
                pass
    unbound = sorted(set(reg.crits) - bound)
    if unbound:
        errs.append("criteria not bound to any task gate: " + ", ".join(unbound))


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="directory holding the tracking files")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "check"):
        s = sub.add_parser(name)
        s.add_argument("ids", nargs="+")
    s = sub.add_parser("verify"); s.add_argument("id"); s.add_argument("--evidence", required=True)
    s = sub.add_parser("complete"); s.add_argument("id"); s.add_argument("--evidence", required=True); s.add_argument("--approved-by")
    s = sub.add_parser("block"); s.add_argument("id"); s.add_argument("--reason", required=True)
    s = sub.add_parser("unblock"); s.add_argument("id")
    s = sub.add_parser("approve-phase"); s.add_argument("phase"); s.add_argument("--by", required=True)
    s = sub.add_parser("next"); s.add_argument("--phase")
    for name in ("status", "dashboard", "validate"):
        sub.add_parser(name)
    q = sub.add_parser("qg"); qs = q.add_subparsers(dest="qgcmd", required=True)
    qs.add_parser("status")
    s = qs.add_parser("require"); s.add_argument("tokens", nargs="+")
    s = qs.add_parser("owner"); s.add_argument("gate"); s.add_argument("--name", required=True)
    s = qs.add_parser("start"); s.add_argument("gate")
    s = qs.add_parser("check"); s.add_argument("ids", nargs="+"); s.add_argument("--evidence", required=True)
    s = qs.add_parser("uncheck"); s.add_argument("id"); s.add_argument("--reason", required=True)
    s = qs.add_parser("fail"); s.add_argument("id"); s.add_argument("--issue", required=True); s.add_argument("--blocks")
    s = qs.add_parser("block"); s.add_argument("gate"); s.add_argument("--reason", required=True); s.add_argument("--blocks")
    s = qs.add_parser("resolve"); s.add_argument("gate"); s.add_argument("--note", required=True)
    for nm in ("pass", "reverify"):
        s = qs.add_parser(nm); s.add_argument("gate"); s.add_argument("--evidence", required=True); s.add_argument("--approved-by")
    s = qs.add_parser("waive"); s.add_argument("id"); s.add_argument("--justification", required=True)
    s.add_argument("--approved-by", required=True); s.add_argument("--risk-owner", required=True); s.add_argument("--expires", required=True)
    s = qs.add_parser("revoke-waiver"); s.add_argument("id")
    args = ap.parse_args()
    cl = Checklist(Path(args.root))
    {
        "start": cmd_start, "check": cmd_check, "verify": cmd_verify, "complete": cmd_complete,
        "block": cmd_block, "unblock": cmd_unblock, "approve-phase": cmd_approve_phase,
        "next": cmd_next, "status": cmd_status, "dashboard": cmd_dashboard, "validate": cmd_validate,
        "qg": cmd_qg,
    }[args.cmd](cl, args)
    if args.cmd in ("start", "verify", "complete", "block", "unblock", "approve-phase"):
        cmd_dashboard(Checklist(Path(args.root)), args)
        refresh_qg(Path(args.root))


if __name__ == "__main__":
    main()
