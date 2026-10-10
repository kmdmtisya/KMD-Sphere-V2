"""Unit tests for app.core.authz (no database)."""

import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI

from app.core.authz import (
    PermissionDeniedError,
    ResourceNotFoundError,
    owned_by,
    require_found,
    require_role,
)
from app.main import create_app
from app.modules.identity.models import RiskProfile
from tests.conftest import make_settings


def test_owned_by_always_filters_on_the_owner() -> None:
    uid = uuid.uuid4()
    sql = str(owned_by(RiskProfile, uid).compile(compile_kwargs={"literal_binds": True}))
    assert "WHERE risk_profiles.user_id =" in sql
    assert str(uid).replace("-", "") in sql.replace("-", "")


def test_owned_by_keeps_the_owner_filter_when_more_conditions_are_added() -> None:
    uid, pid = uuid.uuid4(), uuid.uuid4()
    sql = str(owned_by(RiskProfile, uid).where(RiskProfile.id == pid).compile())
    assert "risk_profiles.user_id = " in sql
    assert "risk_profiles.id = " in sql
    assert " AND " in sql


def test_require_found() -> None:
    assert require_found("x", "thing") == "x"
    with pytest.raises(ResourceNotFoundError) as info:
        require_found(None, "thing")
    assert info.value.kind == "thing"


def test_require_role() -> None:
    require_role(frozenset({"user"}), "user")
    with pytest.raises(PermissionDeniedError):
        require_role(frozenset({"user"}), "support")


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    app: FastAPI = create_app(make_settings(), readiness_checks={})

    @app.get("/_test/missing")
    async def missing() -> None:
        raise ResourceNotFoundError("secret-kind")

    @app.get("/_test/forbidden")
    async def forbidden() -> None:
        raise PermissionDeniedError("admin")

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_not_found_is_a_plain_404_that_names_nothing(http: httpx.AsyncClient) -> None:
    r = await http.get("/_test/missing")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert "secret-kind" not in r.text
    assert r.json()["type"].endswith("/not-found")


async def test_permission_denied_is_403(http: httpx.AsyncClient) -> None:
    r = await http.get("/_test/forbidden")
    assert r.status_code == 403
    assert "admin" not in r.text
    assert r.json()["type"].endswith("/forbidden")
