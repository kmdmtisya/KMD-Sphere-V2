"""End to end with the real Keycloak from the compose stack: a token from the PKCE login is
verified against the realm's live JWKS and provisions the user.

Skipped unless Keycloak is reachable and the dev realm users are seeded
(`python scripts/keycloak_dev.py seed-users`). CI does not run Keycloak, so this is a local check.
"""

import importlib.util
import urllib.request
from collections.abc import AsyncIterator
from pathlib import Path
from types import ModuleType

import httpx
import pytest

from app.core.config import Settings
from app.main import create_app
from tests.db_fixtures import migrated_settings  # noqa: F401 (fixture)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="module")]
ROOT = Path(__file__).resolve().parents[2]


def _keycloak_dev() -> ModuleType:
    if not (ROOT / ".env").exists():
        pytest.skip("no .env (local stack not configured)")
    spec = importlib.util.spec_from_file_location("keycloak_dev", ROOT / "scripts/keycloak_dev.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        urllib.request.urlopen(f"{module.BASE}/realms/{module.REALM}", timeout=2)  # noqa: S310
    except OSError:
        pytest.skip("Keycloak is not reachable")
    if module.E.get("KEYCLOAK_TEST_USER_PASSWORD", "") in ("", "CHANGE_ME"):
        pytest.skip("KEYCLOAK_TEST_USER_PASSWORD not set")
    return module


@pytest.fixture(scope="module")
async def live(
    migrated_settings: Settings,  # noqa: F811
) -> AsyncIterator[tuple[httpx.AsyncClient, ModuleType]]:
    kc = _keycloak_dev()
    settings = migrated_settings.model_copy(update={"oidc_issuer": f"{kc.BASE}/realms/{kc.REALM}"})
    app = create_app(settings, readiness_checks={})  # real JwksKeySource from settings
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, kc
    await app.state.db.dispose()


async def _access_token(kc: ModuleType, username: str) -> str:
    code, verifier = kc.login(username, kc.require("KEYCLOAK_TEST_USER_PASSWORD"))
    status, tokens = kc.exchange(code, verifier)
    assert status == 200
    return str(tokens["access_token"])


async def test_a_real_keycloak_token_signs_in_and_provisions(
    live: tuple[httpx.AsyncClient, ModuleType],
) -> None:
    client, kc = live
    tok = await _access_token(kc, "alice@example.test")
    r = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "alice@example.test"
    assert r.json()["email_verified"] is True


async def test_two_real_users_are_different_accounts(
    live: tuple[httpx.AsyncClient, ModuleType],
) -> None:
    client, kc = live
    a = await client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {await _access_token(kc, 'alice@example.test')}"},
    )
    b = await client.get(
        "/api/v1/me",
        headers={"Authorization": f"Bearer {await _access_token(kc, 'bob@example.test')}"},
    )
    assert a.json()["id"] != b.json()["id"]


async def test_a_tampered_real_token_is_rejected(
    live: tuple[httpx.AsyncClient, ModuleType],
) -> None:
    client, kc = live
    tok = await _access_token(kc, "alice@example.test")
    header, payload, sig = tok.split(".")
    tampered = f"{header}.{payload}.{sig[:-4]}AAAA"
    r = await client.get("/api/v1/me", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401
