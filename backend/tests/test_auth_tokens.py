"""Access-token verification: every way a token can be wrong is rejected with the same 401, and no
database is touched before the token is proven valid."""

import base64
import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator, Callable

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from fastapi import FastAPI
from jwt import PyJWK

from app.core.auth import AuthenticationError, StaticKeySource, TokenVerifier
from app.main import create_app
from tests import auth_helpers as ah
from tests.conftest import make_settings

# ------------------------------------------------------------------------- unit: verifier


def test_a_valid_token_yields_its_claims() -> None:
    c = ah.verifier().verify(ah.token("user-1", email="a@example.test"))
    assert c.subject == "user-1"
    assert c.issuer == ah.ISSUER
    assert c.email == "a@example.test"
    assert c.authorized_party == ah.CLIENT
    assert "user" in c.roles


@pytest.mark.parametrize(
    ("label", "make"),
    [
        ("expired", lambda: ah.token(exp=int(time.time()) - 120, iat=int(time.time()) - 600)),
        ("not yet valid", lambda: ah.token(nbf=int(time.time()) + 600)),
        ("issued in the future", lambda: ah.token(iat=int(time.time()) + 600)),
        ("wrong audience", lambda: ah.token(aud="some-other-api")),
        ("no audience", lambda: ah.token(aud=None)),
        ("wrong issuer", lambda: ah.token(iss="http://evil.test/realms/wealthsphere")),
        ("no subject", lambda: ah.token(sub=None)),
        ("no expiry", lambda: ah.token(exp=None)),
        ("unknown client (azp)", lambda: ah.token(azp="some-other-client")),
        ("signed with another key", lambda: ah.token(key=ah.other_private_key())),
        ("unknown key id", lambda: ah.token(kid="rotated-away")),
        ("no key id", lambda: ah.token(kid=None)),
        ("garbage", lambda: "not-a-jwt"),
        ("empty", lambda: ""),
    ],
)
def test_bad_tokens_are_rejected(label: str, make: Callable[[], str]) -> None:
    with pytest.raises(AuthenticationError):
        ah.verifier().verify(make())


def _b64(data: dict[str, object]) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def test_tampered_payload_is_rejected() -> None:
    header, _payload, signature = ah.token("victim").split(".")
    forged = _b64(ah.claims("attacker"))
    with pytest.raises(AuthenticationError):
        ah.verifier().verify(f"{header}.{forged}.{signature}")


def test_alg_none_is_rejected() -> None:
    unsigned = f"{_b64({'alg': 'none', 'kid': ah.KID})}.{_b64(ah.claims())}."
    with pytest.raises(AuthenticationError):
        ah.verifier().verify(unsigned)


def test_hmac_with_the_public_key_is_rejected() -> None:
    # Key-confusion attack: an HS256 signature made with the RSA public key as the secret.
    public_pem = (
        ah.private_key()
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    header = _b64({"alg": "HS256", "kid": ah.KID, "typ": "JWT"})
    payload = _b64(ah.claims())
    sig = hmac.new(public_pem, f"{header}.{payload}".encode(), hashlib.sha256).digest()
    forged = f"{header}.{payload}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"
    with pytest.raises(AuthenticationError):
        ah.verifier().verify(forged)


def test_clock_skew_within_leeway_is_tolerated() -> None:
    now = int(time.time())
    ah.verifier(leeway=30).verify(ah.token(exp=now - 10, iat=now - 310, nbf=now - 310))
    with pytest.raises(AuthenticationError):
        ah.verifier(leeway=0).verify(ah.token(exp=now - 10, iat=now - 310, nbf=now - 310))


class _RotatingKeys(StaticKeySource):
    """Starts without the key; a refresh 'fetches' it, like a JWKS after key rotation."""

    def __init__(self) -> None:
        super().__init__({})
        self.refreshes = 0

    def refresh(self) -> None:
        self.refreshes += 1
        self._keys = {ah.KID: PyJWK(ah.public_jwk())}


def test_an_unknown_key_id_triggers_one_refetch() -> None:
    keys = _RotatingKeys()
    v = TokenVerifier(keys, ah.ISSUER, ah.AUDIENCE, frozenset({ah.CLIENT}))
    assert v.verify(ah.token("u")).subject == "u"
    assert keys.refreshes == 1


def test_verifier_needs_issuer_and_audience() -> None:
    with pytest.raises(ValueError):
        TokenVerifier(StaticKeySource({}), "", ah.AUDIENCE, frozenset())
    with pytest.raises(ValueError):
        TokenVerifier(StaticKeySource({}), ah.ISSUER, "", frozenset())


# ------------------------------------------------------------------- HTTP: no DB involved


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(make_settings(), readiness_checks={}, token_verifier=ah.verifier())
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": ""},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer not-a-jwt"},
    ],
)
async def test_missing_or_malformed_credentials_get_401(
    http: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    r = await http.get("/api/v1/me", headers=headers)
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.headers["www-authenticate"].startswith("Bearer")
    assert r.json()["type"].endswith("/unauthenticated")


async def test_every_rejection_looks_the_same(http: httpx.AsyncClient) -> None:
    bodies = []
    for bad in (
        ah.token(exp=int(time.time()) - 600, iat=int(time.time()) - 900),
        ah.token(aud="other"),
        ah.token(key=ah.other_private_key()),
    ):
        r = await http.get("/api/v1/me", headers=ah.bearer(bad))
        assert r.status_code == 401
        body = r.json()
        body.pop("correlation_id")
        bodies.append(body)
    assert bodies[0] == bodies[1] == bodies[2], "callers must not learn why a token failed"


async def test_protected_routes_fail_closed_without_oidc_configuration(
    client_for: Callable[[FastAPI], httpx.AsyncClient],
) -> None:
    app = create_app(make_settings(), readiness_checks={})  # no issuer -> no verifier
    assert app.state.token_verifier is None
    async with client_for(app) as c:
        r = await c.get("/api/v1/me", headers=ah.bearer(ah.token()))
    assert r.status_code == 401


async def test_preferences_endpoint_is_protected_too(http: httpx.AsyncClient) -> None:
    r = await http.patch("/api/v1/me/preferences", json={"theme_mode": "dark"})
    assert r.status_code == 401


async def test_health_stays_public(http: httpx.AsyncClient) -> None:
    assert (await http.get("/health/live")).status_code == 200


def test_settings_derive_the_jwks_url_and_parties() -> None:
    s = make_settings(
        oidc_issuer="http://kc.test/realms/wealthsphere/", oidc_authorized_parties="a, b,"
    )
    assert s.jwks_url == "http://kc.test/realms/wealthsphere/protocol/openid-connect/certs"
    assert s.authorized_parties == frozenset({"a", "b"})
    assert make_settings().jwks_url == ""
