"""Every route that takes a resource id in its path, and the test proving another user cannot
read or change it (ADR-0011). tests/test_idor_coverage.py fails when a route is missing here or a
named test does not exist.

Format: (METHOD, path template) -> "tests.module::test_function".
"""

IDOR_TESTS: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/risk-profiles/{risk_profile_id}"): (
        "tests.test_authz_risk_profiles::test_bob_cannot_read_alices_risk_profile"
    ),
    ("PATCH", "/api/v1/risk-profiles/{risk_profile_id}"): (
        "tests.test_authz_risk_profiles::test_bob_cannot_change_alices_risk_profile"
    ),
    ("GET", "/api/v1/assets/{asset_id}"): (
        "tests.test_assets_api::test_bob_cannot_read_alices_asset"
    ),
}
