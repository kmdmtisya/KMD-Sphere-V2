"""Guards the IDOR registry: every route with an id in its path must name a cross-user test, and
that test must exist. This keeps ownership tests from being forgotten as modules are added."""

import importlib

import pytest

from app.main import create_app
from tests.conftest import make_settings
from tests.idor_registry import IDOR_TESTS, NOT_USER_RESOURCES

pytestmark = pytest.mark.security


def _id_routes() -> set[tuple[str, str]]:
    """Every (METHOD, path) with a path parameter, from the OpenAPI document (FastAPI mounts
    included routers lazily, so the OpenAPI paths are the reliable list of public operations)."""
    spec = create_app(make_settings(), readiness_checks={}).openapi()
    return {
        (method.upper(), path)
        for path, operations in spec["paths"].items()
        if "{" in path
        for method in operations
        if method in ("get", "post", "put", "patch", "delete")
    }


def test_every_id_route_has_a_cross_user_test() -> None:
    missing = sorted(_id_routes() - IDOR_TESTS.keys() - NOT_USER_RESOURCES.keys())
    assert not missing, f"add an IDOR test and register it in tests/idor_registry.py: {missing}"


def test_registry_has_no_stale_routes() -> None:
    stale = sorted(IDOR_TESTS.keys() - _id_routes())
    assert not stale, f"routes no longer exist: {stale}"


def test_every_named_test_exists() -> None:
    for route, target in IDOR_TESTS.items():
        module_name, _, function = target.partition("::")
        module = importlib.import_module(module_name)
        assert callable(getattr(module, function, None)), f"{route}: {target} not found"


def test_exemptions_are_real_and_take_no_resource_id() -> None:
    routes = _id_routes()
    for route, reason in NOT_USER_RESOURCES.items():
        assert route in routes, f"stale exemption: {route}"
        assert "_id}" not in route[1], f"{route} takes a resource id: it needs an IDOR test"
        assert reason.strip(), f"{route}: give a reason"
        assert route not in IDOR_TESTS, f"{route} is both exempt and registered"
