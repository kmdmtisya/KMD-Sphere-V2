"""Renders docs/financial-test-matrix.md from docs/contracts/financial-test-matrix.json (QG-03.4).

    python scripts/test_matrix.py           # write the Markdown
    python scripts/test_matrix.py --check   # fail if the committed Markdown is out of date

backend/tests/test_financial_matrix.py runs the check in CI and verifies the matrix against the
tests, the financial modules and docs/financial-methods.md.
"""

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "contracts" / "financial-test-matrix.json"
TARGET = ROOT / "docs" / "financial-test-matrix.md"


def render(data: dict[str, Any]) -> str:
    rows = data["requirements"]
    tests = {t for r in rows for t in r["tests"]}
    covered = {c for r in rows for c in r["covers"]}
    lines = [
        "# Financial test matrix",
        "",
        "Generated from `contracts/financial-test-matrix.json` by `scripts/test_matrix.py`; edit "
        "the JSON, not this file. Quality gate QG-03.4.",
        "",
        data["about"],
        "",
        f"**{len(rows)} requirements, {len(tests)} distinct tests, {len(covered)} public "
        "functions of the financial modules covered.** Tests are under `backend/`.",
        "",
        "| Id | Method section | Requirement or edge case | Functions | Tests |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        functions = "<br>".join(f"`{c}`" for c in r["covers"]) or "-"
        names = "<br>".join(f"`{t}`" for t in r["tests"])
        lines.append(f"| {r['id']} | {r['section']} | {r['text']} | {functions} | {names} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    text = render(json.loads(SOURCE.read_text(encoding="utf-8")))
    if "--check" in sys.argv:
        if TARGET.read_text(encoding="utf-8") != text:
            print("docs/financial-test-matrix.md is out of date: run scripts/test_matrix.py")
            return 1
        print("OK: financial-test-matrix.md matches financial-test-matrix.json")
        return 0
    TARGET.write_bytes(text.encode())
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
