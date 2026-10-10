"""Every API route requires a valid access token unless it is explicitly public (P04-T09).

New endpoints are protected by default (they depend on `current_user`); this test fails the build
if one answers without authentication, so a forgotten dependency cannot ship. Public routes must
be listed in PUBLIC with a reason.
"""

import re
import time
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.main import create_app
from tests import auth_helpers as ah
from tests.conftest import make_settings

pytestmark = pytest.mark.security

# (METHOD, path) -> why it is reachable without a user token.
PUBLIC: dict[tuple[str, str], str] = {
    ("GET", "/health/live"): "liveness probe; no data",
    ("GET", "/health/ready"): "readiness probe; reports dependency status only",
}

_PARAM = re.compile(r"\{[^}]+\}")


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(make_settings(), readiness_checks={}, token_verifier=ah.verifier())
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _routes() -> list[tuple[str, str]]:
    app = create_app(make_settings(), readiness_checks={})
    return sorted(
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    )


def test_public_routes_still_exist() -> None:
    assert set(PUBLIC) <= set(_routes()), "remove stale entries from PUBLIC"


def test_there_are_protected_routes_to_check() -> None:
    assert len([r for r in _routes() if r not in PUBLIC]) >= 6


_EXPIRED = ah.token("someone", exp=int(time.time()) - 3600, iat=int(time.time()) - 3900)
_WRONG_KEY = ah.token("someone", key=ah.other_private_key())
_CASES = {
    "no token": {},
    "garbage": ah.bearer("not-a-jwt"),
    "expired": ah.bearer(_EXPIRED),
    "signed by another key": ah.bearer(_WRONG_KEY),
    "wrong scheme": {"Authorization": f"Basic {_EXPIRED}"},
}


@pytest.mark.parametrize(("method", "path"), [r for r in _routes() if r not in PUBLIC])
@pytest.mark.parametrize("case", list(_CASES))
async def test_every_protected_route_refuses_unauthenticated_callers(
    http: httpx.AsyncClient, method: str, path: str, case: str
) -> None:
    concrete = _PARAM.sub(str(uuid.uuid4()), path)
    response = await http.request(method, concrete, headers=_CASES[case], json={})
    assert response.status_code == 401, (method, path, case, response.text)
    assert response.headers["WWW-Authenticate"].startswith("Bearer")
    body = response.json()
    assert body["type"].endswith("/unauthenticated")
    # One uniform answer: nothing about why the token was refused.
    assert "expired" not in response.text.lower()
    assert "signature" not in response.text.lower()
