#!/usr/bin/env python3
"""Fails when the mobile app and the web portal disagree about the mobile destinations (P14-T18,
QG-28.1, QG-33.10).

The mobile app declares every destination once, in `AppRoutes` (mobile/wealthsphere_app/lib/app/
app_routes.dart; widgets never build path strings). The web declares the same list as
`MOBILE_ROUTES` in web/src/lib/nav/nav.ts and maps each entry to a web page or to a recorded
exception with a reason (checked by web/src/lib/nav/nav.test.ts). This script compares the two
lists, so a mobile screen added without a web mapping, or a stale web entry, fails CI.

  python scripts/check_route_parity.py            # exit 1 on a difference
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOBILE = ROOT / "mobile/wealthsphere_app/lib/app/app_routes.dart"
WEB = ROOT / "web/src/lib/nav/nav.ts"


def mobile_routes(text: str) -> set[str]:
    """Every static destination in AppRoutes (a path with a parameter is reached from its parent)."""
    paths = re.findall(r"static const String \w+ = '(/[^']*)';", text)
    return {p for p in paths if ":" not in p}


def web_routes(text: str) -> set[str]:
    block = re.search(r"export const MOBILE_ROUTES = \[(.*?)\];", text, re.S)
    if block is None:
        sys.exit("MOBILE_ROUTES not found in web/src/lib/nav/nav.ts")
    return set(re.findall(r'"(/[^"]*)"', block.group(1)))


def compare(mobile: set[str], web: set[str]) -> list[str]:
    problems = [f"mobile route {p} has no entry in MOBILE_ROUTES (map it to a web page or record an exception)" for p in sorted(mobile - web)]
    problems += [f"MOBILE_ROUTES lists {p}, which the mobile app no longer declares" for p in sorted(web - mobile)]
    return problems


def main() -> int:
    mobile = mobile_routes(MOBILE.read_text(encoding="utf-8"))
    web = web_routes(WEB.read_text(encoding="utf-8"))
    if not mobile:
        print("no mobile routes found: has app_routes.dart changed shape?", file=sys.stderr)
        return 1
    problems = compare(mobile, web)
    for line in problems:
        print(line, file=sys.stderr)
    print(f"{len(mobile)} mobile destinations, {len(web)} in the web list: {'OK' if not problems else 'MISMATCH'}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
