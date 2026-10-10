"""Bearer-token authentication: OIDC access tokens issued by Keycloak, verified with its JWKS.

Rules (docs/security.md, CLAUDE.md):
- Only RS256 is accepted; `none` and HMAC algorithms are rejected, so a public key can never be
  used as an HMAC secret.
- Signature, issuer, audience, expiry, not-before and issued-at are all checked, with a small
  clock-skew allowance. The authorised party must be one of the known clients.
- Keys come from the issuer's JWKS, cached; an unknown key id triggers one refetch (key rotation).
- Tokens are never logged. Every failure is the same 401 for the caller; the reason is logged
  without the token.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Protocol

import jwt
from jwt import PyJWK

logger = logging.getLogger(__name__)

ALLOWED_ALGORITHMS = ("RS256",)


class AuthenticationError(Exception):
    """The request does not carry a valid access token. Always surfaces as HTTP 401."""


@dataclass(frozen=True)
class TokenClaims:
    issuer: str
    subject: str
    email: str | None
    email_verified: bool
    authorized_party: str | None
    roles: frozenset[str]
    expires_at: int


class KeySource(Protocol):
    """Where verification keys come from (the issuer's JWKS in production, fixed keys in tests)."""

    def key_for(self, kid: str) -> PyJWK | None: ...

    def refresh(self) -> None: ...


class JwksKeySource:
    """Fetches the issuer's JWKS over HTTP and caches it for `cache_seconds`."""

    def __init__(
        self, jwks_url: str, cache_seconds: int = 300, timeout_seconds: float = 3.0
    ) -> None:
        self._client = jwt.PyJWKClient(
            jwks_url,
            cache_keys=False,
            cache_jwk_set=True,
            lifespan=cache_seconds,
            timeout=timeout_seconds,
        )

    def key_for(self, kid: str) -> PyJWK | None:
        for key in self._client.get_signing_keys():
            if key.key_id == kid:
                return key
        return None

    def refresh(self) -> None:
        self._client.get_jwk_set(refresh=True)


class StaticKeySource:
    """Keys fixed at construction (tests and offline tooling)."""

    def __init__(self, keys: dict[str, PyJWK]) -> None:
        self._keys = keys

    def key_for(self, kid: str) -> PyJWK | None:
        return self._keys.get(kid)

    def refresh(self) -> None:
        return None


class TokenVerifier:
    def __init__(
        self,
        keys: KeySource,
        issuer: str,
        audience: str,
        authorized_parties: frozenset[str],
        leeway_seconds: int = 30,
    ) -> None:
        if not issuer or not audience:
            raise ValueError("issuer and audience are required")
        self._keys = keys
        self._issuer = issuer
        self._audience = audience
        self._parties = authorized_parties
        self._leeway = leeway_seconds

    def verify(self, token: str) -> TokenClaims:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as e:
            raise AuthenticationError("malformed token") from e
        alg = header.get("alg")
        kid = header.get("kid")
        if alg not in ALLOWED_ALGORITHMS:
            raise AuthenticationError(f"algorithm {alg!r} is not accepted")
        if not isinstance(kid, str) or not kid:
            raise AuthenticationError("token has no key id")

        key = self._key(kid)
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key=key.key,
                algorithms=list(ALLOWED_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                leeway=self._leeway,
                options={"require": ["exp", "iat", "iss", "sub", "aud"]},
            )
        except jwt.ExpiredSignatureError as e:
            raise AuthenticationError("token expired") from e
        except jwt.PyJWTError as e:
            raise AuthenticationError(f"token rejected: {type(e).__name__}") from e

        if claims.get("iat", 0) > time.time() + self._leeway:
            raise AuthenticationError("token issued in the future")
        azp = claims.get("azp")
        if self._parties and azp not in self._parties:
            raise AuthenticationError("token was issued to an unknown client")
        roles = claims.get("realm_access", {}).get("roles", [])
        return TokenClaims(
            issuer=claims["iss"],
            subject=str(claims["sub"]),
            email=claims.get("email"),
            email_verified=bool(claims.get("email_verified", False)),
            authorized_party=azp,
            roles=frozenset(r for r in roles if isinstance(r, str)),
            expires_at=int(claims["exp"]),
        )

    def _key(self, kid: str) -> PyJWK:
        try:
            key = self._keys.key_for(kid)
            if key is None:  # possibly a rotated key: refetch once
                self._keys.refresh()
                key = self._keys.key_for(kid)
        except jwt.PyJWKClientError as e:
            logger.warning("jwks unavailable", extra={"error": type(e).__name__})
            raise AuthenticationError("signing keys unavailable") from e
        if key is None:
            raise AuthenticationError("unknown signing key")
        return key
