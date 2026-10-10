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
    ("GET", "/api/v1/portfolios/{portfolio_id}"): (
        "tests.test_portfolios_api::test_bob_cannot_read_alices_portfolio"
    ),
    ("PATCH", "/api/v1/portfolios/{portfolio_id}"): (
        "tests.test_portfolios_api::test_bob_cannot_change_alices_portfolio"
    ),
    ("POST", "/api/v1/portfolios/{portfolio_id}/archive"): (
        "tests.test_portfolios_api::test_bob_cannot_archive_alices_portfolio"
    ),
    ("GET", "/api/v1/portfolios/{portfolio_id}/transactions"): (
        "tests.test_transactions_api::test_bob_cannot_list_alices_ledger"
    ),
    ("POST", "/api/v1/portfolios/{portfolio_id}/transactions"): (
        "tests.test_transactions_api::test_bob_cannot_post_to_alices_portfolio"
    ),
    ("GET", "/api/v1/portfolios/{portfolio_id}/transactions/{transaction_id}"): (
        "tests.test_transactions_api::test_bob_cannot_read_alices_transaction"
    ),
    ("POST", "/api/v1/portfolios/{portfolio_id}/transactions/{transaction_id}/reversal"): (
        "tests.test_transactions_api::test_bob_cannot_reverse_alices_transaction"
    ),
}
