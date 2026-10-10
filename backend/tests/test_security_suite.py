"""The security suite stays complete: every module that tests a security control carries the
`security` marker (so `pytest -m security` in CI runs all of them), and each control area named
in docs/threat-model.md has tests (P04-T09)."""

import importlib
import inspect

import pytest

pytestmark = pytest.mark.security

# Control area -> modules testing it. Keep in step with docs/threat-model.md.
SECURITY_MODULES: dict[str, tuple[str, ...]] = {
    "token validation (tamper, expiry, audience, issuer, algorithm)": ("tests.test_auth_tokens",),
    "every route authenticated unless public": ("tests.test_auth_coverage",),
    "authorization / IDOR": (
        "tests.test_authz_risk_profiles",
        "tests.test_authz_helpers",
        "tests.test_idor_coverage",
        "tests.test_assets_api",
        "tests.test_portfolios_api",
        "tests.test_transactions_api",
        "tests.test_holdings_api",
        "tests.test_valuations_api",
        "tests.test_summary_api",
        "tests.test_integrity_suite",
    ),
    "identity provisioning and preferences": ("tests.test_identity_api",),
    "rate limits, body limits, headers, CORS": ("tests.test_api_protection",),
    "audit trail (append-only, redacted)": ("tests.test_audit",),
    "log redaction": ("tests.test_redaction",),
    "identity provider configuration": ("tests.test_keycloak_realm",),
}


def _marks(module: object) -> set[str]:
    raw = getattr(module, "pytestmark", [])
    marks = raw if isinstance(raw, list) else [raw]
    return {m.name for m in marks}


@pytest.mark.parametrize(
    "name", sorted({m for modules in SECURITY_MODULES.values() for m in modules})
)
def test_module_is_in_the_security_suite(name: str) -> None:
    module = importlib.import_module(name)
    assert "security" in _marks(module), f"{name} must set pytestmark to include security"
    tests = [n for n, obj in inspect.getmembers(module) if n.startswith("test_") and callable(obj)]
    assert tests, f"{name} has no tests"
