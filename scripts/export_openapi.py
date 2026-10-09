#!/usr/bin/env python3
"""Export (or verify) the committed OpenAPI contract.

  cd backend && uv run python ../scripts/export_openapi.py            # write backend/openapi.json
  cd backend && uv run python ../scripts/export_openapi.py --check    # exit 1 if it is out of date

The app is built with hermetic settings (no .env, no network), so the output is deterministic
and identical on every machine. `--check` is used by CI and by tests/test_openapi_contract.py.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
TARGET = BACKEND / "openapi.json"


def generate() -> str:
    sys.path.insert(0, str(BACKEND))
    from app.core.config import Settings  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415

    settings = Settings(_env_file=None, environment="test")  # type: ignore[call-arg]
    app = create_app(settings, readiness_checks={})
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="fail if the committed file differs")
    args = parser.parse_args()

    new = generate()
    if args.check:
        current = TARGET.read_text(encoding="utf-8").replace("\r\n", "\n") if TARGET.exists() else ""
        if current == new:
            print(f"OK: {TARGET.name} matches the application")
            return 0
        diff = difflib.unified_diff(
            current.splitlines(), new.splitlines(), "committed", "generated", lineterm="", n=2
        )
        print("\n".join(list(diff)[:60]))
        print(f"\nERROR: {TARGET} is out of date. Regenerate it: cd backend && uv run python ../scripts/export_openapi.py")
        return 1

    TARGET.write_text(new, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET} ({len(new)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
