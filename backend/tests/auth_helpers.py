"""Test signing keys and tokens. A fresh RSA key is generated per test session; nothing secret
is committed. Tokens look like Keycloak's (issuer, audience, azp, realm roles)."""

import json
import time
import uuid
from functools import lru_cache
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWK
from jwt.algorithms import RSAAlgorithm

from app.core.auth import StaticKeySource, TokenVerifier

ISSUER = "http://keycloak.test/realms/wealthsphere"
AUDIENCE = "wealthsphere-api"
CLIENT = "wealthsphere-mobile"
KID = "test-key-1"


@lru_cache
def private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@lru_cache
def other_private_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def public_jwk(key: rsa.RSAPrivateKey | None = None, kid: str = KID) -> dict[str, Any]:
    jwk: dict[str, Any] = json.loads(RSAAlgorithm.to_jwk((key or private_key()).public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return jwk


def verifier(leeway: int = 30) -> TokenVerifier:
    keys = StaticKeySource({KID: PyJWK(public_jwk())})
    return TokenVerifier(keys, ISSUER, AUDIENCE, frozenset({CLIENT}), leeway_seconds=leeway)


def claims(subject: str | None = None, **overrides: Any) -> dict[str, Any]:
    now = int(time.time())
    base: dict[str, Any] = {
        "iss": ISSUER,
        "sub": subject or str(uuid.uuid4()),
        "aud": [AUDIENCE, "account"],
        "azp": CLIENT,
        "iat": now,
        "nbf": now,
        "exp": now + 300,
        "email": "user@example.test",
        "email_verified": True,
        "realm_access": {"roles": ["user", "offline_access"]},
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def token(
    subject: str | None = None,
    *,
    key: rsa.RSAPrivateKey | None = None,
    kid: str | None = KID,
    algorithm: str = "RS256",
    **overrides: Any,
) -> str:
    headers = {"kid": kid} if kid is not None else {}
    return jwt.encode(
        claims(subject, **overrides),
        key or private_key(),
        algorithm=algorithm,
        headers=headers,
    )


def bearer(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}
