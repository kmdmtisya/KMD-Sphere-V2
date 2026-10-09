#!/usr/bin/env python3
"""Per-module coverage report and policy check (QG-03.5).

  cd backend && uv run pytest --cov --cov-report=xml
  uv run python ../scripts/coverage_by_module.py coverage.xml --policy coverage-policy.toml \
      [--summary "$GITHUB_STEP_SUMMARY"]

Groups line coverage by module (`core`, `api`, `db`, `modules/<name>`, ...), prints a table, and
fails (exit 1) when a *business-critical* module listed in the policy exists and is below the
threshold. Critical modules that do not exist yet are reported as "not yet present". Coverage is
a floor, never a substitute for meaningful tests (docs/quality-targets.md section 6).
"""

from __future__ import annotations

import argparse
import sys
import tomllib
import xml.etree.ElementTree as ET  # noqa: S405 (coverage.xml is produced by our own CI step)
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Module:
    name: str
    lines: int = 0
    covered: int = 0

    @property
    def percent(self) -> float:
        return 100.0 * self.covered / self.lines if self.lines else 100.0


def module_of(filename: str) -> str:
    parts = Path(filename.replace("\\", "/")).parts
    if parts and parts[0] == "app":
        parts = parts[1:]
    if not parts:
        return "(root)"
    if parts[0] == "modules" and len(parts) > 2:
        return f"modules/{parts[1]}"
    if len(parts) == 1:
        return "(app root)"
    return parts[0]


def collect(xml_path: Path) -> dict[str, Module]:
    root = ET.parse(xml_path).getroot()  # noqa: S314
    modules: dict[str, Module] = {}
    for cls in root.iter("class"):
        name = module_of(cls.get("filename", ""))
        module = modules.setdefault(name, Module(name))
        seen: dict[int, bool] = {}
        for line in cls.iter("line"):
            number = int(line.get("number", "0"))
            seen[number] = seen.get(number, False) or int(line.get("hits", "0")) > 0
        module.lines += len(seen)
        module.covered += sum(seen.values())
    return modules


def evaluate(
    modules: dict[str, Module], critical: list[str], threshold: float
) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    absent: list[str] = []
    for name in critical:
        module = modules.get(name)
        if module is None:
            absent.append(name)
        elif module.percent < threshold:
            failures.append(f"{name}: {module.percent:.1f}% < {threshold:.0f}%")
    return failures, absent


def render(modules: dict[str, Module], critical: list[str], threshold: float) -> str:
    rows = ["| Module | Lines | Covered | Line coverage | Business-critical |", "|---|---|---|---|---|"]
    for name in sorted(modules):
        m = modules[name]
        flag = f"yes (>= {threshold:.0f}%)" if name in critical else ""
        rows.append(f"| `{name}` | {m.lines} | {m.covered} | {m.percent:.1f}% | {flag} |")
    total = sum(m.lines for m in modules.values())
    covered = sum(m.covered for m in modules.values())
    pct = 100.0 * covered / total if total else 100.0
    rows.append(f"| **total** | {total} | {covered} | **{pct:.1f}%** | |")
    return "\n".join(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("coverage_xml", type=Path)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--summary", type=Path, help="append the markdown table to this file")
    args = parser.parse_args()

    policy = tomllib.loads(args.policy.read_text(encoding="utf-8"))
    threshold = float(policy.get("threshold", 85))
    critical = [str(m) for m in policy.get("critical", [])]

    modules = collect(args.coverage_xml)
    failures, absent = evaluate(modules, critical, threshold)

    table = render(modules, critical, threshold)
    notes = []
    if absent:
        notes.append("Business-critical modules not yet present (checked once they exist): " + ", ".join(absent))
    notes.append("Policy: " + (("FAILED - " + "; ".join(failures)) if failures else "OK"))
    report = "### Backend coverage by module\n\n" + table + "\n\n" + "\n".join(f"- {n}" for n in notes) + "\n"

    print(report)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as fh:
            fh.write(report)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
