"""Static checks on the committed Keycloak development realm (infra/keycloak/realm-export.json).

The realm is imported by `docker compose up`; these tests keep its security settings from drifting
and make sure no credential is ever committed with it. Runtime behaviour (PKCE, rejected grants,
TOTP enrolment) is checked against a running Keycloak by `scripts/keycloak_dev.py smoke`.
"""

import json
from pathlib import Path
from typing import Any

import pytest

REALM_FILE = Path(__file__).resolve().parents[2] / "infra" / "keycloak" / "realm-export.json"


@pytest.fixture(scope="module")
def realm() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(REALM_FILE.read_text(encoding="utf-8"))
    return data


def client(realm: dict[str, Any], client_id: str) -> dict[str, Any]:
    matches: list[dict[str, Any]] = [c for c in realm["clients"] if c["clientId"] == client_id]
    assert len(matches) == 1, client_id
    return matches[0]


def test_mobile_client_is_public_pkce_only(realm: dict[str, Any]) -> None:
    mobile = client(realm, "wealthsphere-mobile")
    assert mobile["publicClient"] is True
    assert mobile["standardFlowEnabled"] is True
    assert mobile["implicitFlowEnabled"] is False
    assert mobile["directAccessGrantsEnabled"] is False
    assert mobile["serviceAccountsEnabled"] is False
    assert mobile["attributes"]["pkce.code.challenge.method"] == "S256"


def test_redirects_are_exact_app_scheme_uris(realm: dict[str, Any]) -> None:
    mobile = client(realm, "wealthsphere-mobile")
    assert mobile["redirectUris"] == ["com.kmdmtisya.wealthsphere:/oauth2redirect"]
    assert all("*" not in uri for uri in mobile["redirectUris"])
    assert mobile["webOrigins"] == []


def test_access_tokens_target_the_api(realm: dict[str, Any]) -> None:
    mappers = client(realm, "wealthsphere-mobile")["protocolMappers"]
    audience = [m for m in mappers if m["protocolMapper"] == "oidc-audience-mapper"]
    assert audience and audience[0]["config"]["included.client.audience"] == "wealthsphere-api"
    api = client(realm, "wealthsphere-api")
    assert not api["standardFlowEnabled"] and not api["directAccessGrantsEnabled"]
    assert not api["implicitFlowEnabled"] and not api["serviceAccountsEnabled"]


def test_password_mfa_and_session_policy(realm: dict[str, Any]) -> None:
    policy = realm["passwordPolicy"]
    for rule in (
        "length(12)",
        "upperCase(1)",
        "lowerCase(1)",
        "digits(1)",
        "specialChars(1)",
        "notUsername",
        "passwordHistory(5)",
    ):
        assert rule in policy, rule
    assert realm["verifyEmail"] is True
    assert realm["otpPolicyType"] == "totp" and realm["otpPolicyDigits"] == 6
    actions = {a["alias"]: a for a in realm["requiredActions"]}
    assert actions["CONFIGURE_TOTP"]["enabled"] is True
    assert realm["accessTokenLifespan"] <= 300
    assert realm["revokeRefreshToken"] is True and realm["refreshTokenMaxReuse"] == 0


def test_brute_force_detection_locks_accounts_temporarily(realm: dict[str, Any]) -> None:
    assert realm["bruteForceProtected"] is True
    assert realm["failureFactor"] <= 5
    assert realm["waitIncrementSeconds"] >= 60
    assert realm["maxFailureWaitSeconds"] >= 900
    assert realm["minimumQuickLoginWaitSeconds"] >= 60
    # Temporary, not permanent: a permanent lockout lets anyone disable any account by guessing.
    assert realm["permanentLockout"] is False


def test_no_credentials_or_secrets_are_committed(realm: dict[str, Any]) -> None:
    text = REALM_FILE.read_text(encoding="utf-8").lower()
    for user in realm.get("users", []):
        assert "credentials" not in user, user["username"]
    for c in realm["clients"]:
        assert "secret" not in c, c["clientId"]
    assert '"secret"' not in text and '"value"' not in text
    assert all(u["email"].endswith("@example.test") for u in realm["users"])
