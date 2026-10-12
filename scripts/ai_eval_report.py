"""Turns backend/ai_eval_results.json (written by `pytest tests/ai_eval`) into a Markdown table.

    cd backend && uv run pytest tests/ai_eval -q && cd .. && python scripts/ai_eval_report.py
"""

import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "backend" / "ai_eval_results.json"
NOTES = {
    "routing": "stand-in model; the real-model rate is measured before release",
    "numeric": "answers checked against tool results",
    "injection": "scripted compromised model; user-text payloads also run with refusal rules off",
    "cross_user": "tool, scope, conversation and identity vectors",
    "guarantee": "reject wording, keep denials",
    "invented": "invented prices, FX and returns rejected; supported ones kept",
    "stale": "server-added qualifications",
    "refusal": "unsafe declined, legitimate answered",
}


def main() -> int:
    if not RESULTS.exists():
        print("No results: run `uv run pytest tests/ai_eval` in backend/ first.")
        return 1
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    print("| Dataset | Cases | Passed | Rate | Threshold | Gate | Mode | Note |")
    print("|---|---|---|---|---|---|---|---|")
    for name, r in data.items():
        rule = "100% (zero tolerance)" if r["zero_tolerance"] else f">= {r['minimum_rate']:.0%}"
        mode = "run in CI" if r["mode"] == "ci" else "runner only (needs a real model)"
        print(
            f"| {name} | {r['total']} | {r['passed']} | {r['rate']:.0%} | {rule} | {r['gate']} "
            f"| {mode} | {NOTES.get(name, '')} |"
        )
    failed = {n: r["failures"] for n, r in data.items() if r["failures"]}
    if failed:
        print("\nFailing cases:", json.dumps(failed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
