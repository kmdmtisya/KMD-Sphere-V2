"""Renders docs/contracts/dto-mapping.md from docs/contracts/dto-mapping.json (P05-T10).

    python scripts/dto_mapping.py           # write the Markdown
    python scripts/dto_mapping.py --check   # fail if the committed Markdown is out of date

backend/tests/test_dto_mapping.py runs the check in CI and verifies the mapping against
backend/openapi.json and the Dart DTOs.
"""

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "contracts" / "dto-mapping.json"
TARGET = ROOT / "docs" / "contracts" / "dto-mapping.md"


def render(data: dict[str, Any]) -> str:
    lines = [
        "# Mobile DTOs and the API: field mapping",
        "",
        "Generated from `dto-mapping.json` by `scripts/dto_mapping.py`; edit the JSON, not this "
        "file. Decision on client generation: [ADR-0013](../adr/0013-api-client-dtos.md).",
        "",
        data["about"],
        "",
        "## Endpoints that exist",
        "",
    ]
    for entry in data["live"]:
        lines += [
            f"### {entry['dto']} - `{entry['api']}` ({entry['schema']})",
            "",
            f"Dart: `mobile/wealthsphere_app/{entry['dart']}`",
            "",
            "| DTO field | API field | Status | Resolution | Owner |",
            "|---|---|---|---|---|",
        ]
        for f in entry["fields"]:
            lines.append(
                f"| {_code(f['dto'])} | {_code(f['api'])} | {f['status']} | "
                f"{f.get('resolution', '')} | {f.get('owner', '')} |"
            )
        if entry.get("notes"):
            lines += ["", entry["notes"]]
        lines.append("")
    lines += [
        "## DTOs whose API is not built yet",
        "",
        "These DEMO DTOs are the proposed contract; the owning task adopts them or updates this "
        "mapping.",
        "",
        "| DTO | Dart | JSON keys | Owner | Resolution |",
        "|---|---|---|---|---|",
    ]
    for p in data["pending"]:
        keys = ", ".join(f"`{k}`" for k in p["keys"]) or "-"
        lines.append(
            f"| {p['dto']} | `{p['dart'].rsplit('/', 1)[-1]}` | {keys} | {p['owner']} | "
            f"{p['resolution']} |"
        )
    return "\n".join(lines) + "\n"


def _code(value: str | None) -> str:
    return f"`{value}`" if value else "-"


def main() -> int:
    text = render(json.loads(SOURCE.read_text(encoding="utf-8")))
    if "--check" in sys.argv:
        if TARGET.read_text(encoding="utf-8") != text:
            print("docs/contracts/dto-mapping.md is out of date: run scripts/dto_mapping.py")
            return 1
        print("OK: dto-mapping.md matches dto-mapping.json")
        return 0
    TARGET.write_bytes(text.encode())
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
