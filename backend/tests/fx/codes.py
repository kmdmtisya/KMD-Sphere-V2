"""Test-only currency codes for the FX tests.

The rate table is shared by the whole test session, so every test that stores rates uses its own
codes. Codes start with "Y" (no real currency but YER does) and are never handed out twice in a
session, so two tests can never read each other's rates."""

import secrets
import string

_ISSUED: set[str] = {"YER"}


def unique_code() -> str:
    while True:
        candidate = "Y" + "".join(secrets.choice(string.ascii_uppercase) for _ in range(2))
        if candidate not in _ISSUED:
            _ISSUED.add(candidate)
            return candidate
