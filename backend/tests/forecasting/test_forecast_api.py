"""/api/v1/forecasts (P06-T02): shapes, limits, assumption echo and authentication."""

import json
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from app.modules.forecasting.limits import NOTICE
from tests import auth_helpers as ah
from tests.authz_harness import TwoUsers, two_users  # noqa: F401
from tests.db_fixtures import migrated_settings  # noqa: F401

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
async def app(migrated_settings: Settings) -> AsyncIterator[FastAPI]:  # noqa: F811
    application = create_app(migrated_settings, readiness_checks={}, token_verifier=ah.verifier())
    yield application
    await application.state.db.dispose()


@pytest.fixture
async def http(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


# The mobile calculator's opening inputs (ForecastInputLimits.defaults).
COMPOUND: dict[str, Any] = {
    "initial_investment": usd("10000.00"),
    "contribution": usd("500.00"),
    "annual_return_percent": "8.00",
    "years": 20,
    "contribution_growth_percent": "0.00",
    "inflation_percent": "2.50",
    "annual_fee_percent": "0.50",
    "compounding_frequency": "monthly",
    "contribution_frequency": "monthly",
}
SCENARIOS = COMPOUND | {"conservative_return_percent": "5.00", "growth_return_percent": "12.00"}
GOAL = {k: v for k, v in COMPOUND.items() if k != "contribution"} | {"target": usd("1000000.00")}
PATHS = {
    "/api/v1/forecasts/compound": COMPOUND,
    "/api/v1/forecasts/scenarios": SCENARIOS,
    "/api/v1/forecasts/goal": GOAL,
}


async def post(
    http: httpx.AsyncClient, users: TwoUsers, path: str, body: dict[str, Any]
) -> httpx.Response:
    return await http.post(path, headers=users.alice.headers, json=body)


def _no_json_numbers(value: Any, path: str = "$") -> None:
    """Amounts, rates and percentages are strings; only years are numbers."""
    if isinstance(value, dict):
        for k, v in value.items():
            _no_json_numbers(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _no_json_numbers(v, f"{path}[{i}]")
    elif isinstance(value, int | float) and not isinstance(value, bool):
        assert path.endswith((".year", ".years")), path
        assert isinstance(value, int), path


# ------------------------------------------------------------------------------------- results


async def test_scenarios_match_the_mobile_contract(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    r = await post(http, two_users, "/api/v1/forecasts/scenarios", SCENARIOS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"currency", "scenarios", "assumptions", "as_of", "notice"}
    assert body["currency"] == "USD" and body["notice"] == NOTICE
    assert set(body["scenarios"]) == {"conservative", "base", "growth"}
    base = body["scenarios"]["base"]
    # Golden vector "calculator defaults" (tests/golden/forecast_vectors.json).
    assert base["final_nominal"] == usd("321473.53")
    assert base["final_real"] == usd("196185.96")
    assert base["total_contributions"] == usd("130000.00")
    assert base["total_growth"] == usd("191473.53")
    assert base["annual_return_percent"] == "8"
    for kind, rate in (("conservative", "5"), ("base", "8"), ("growth", "12")):
        s = body["scenarios"][kind]
        assert s["annual_return_percent"] == rate
        for series in ("nominal", "real", "contributions"):
            assert [p["year"] for p in s[series]] == list(range(21))
        assert s["nominal"][-1]["value"] == s["final_nominal"]["amount"]
        assert s["real"][-1]["value"] == s["final_real"]["amount"]
        assert s["contributions"][0]["value"] == "10000.00"
    finals = [Decimal(body["scenarios"][k]["final_nominal"]["amount"]) for k in SCENARIOS_ORDER]
    assert finals == sorted(finals)
    _no_json_numbers(body)


SCENARIOS_ORDER = ("conservative", "base", "growth")


async def test_the_assumptions_are_echoed(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    for path, request in PATHS.items():
        body = (await post(http, two_users, path, request)).json()
        echoed = body["assumptions"]
        assert set(echoed) >= set(request), path
        for key, sent in request.items():
            got = echoed[key]
            if isinstance(sent, dict):
                assert got == sent, (path, key)
            elif isinstance(sent, str) and key.endswith("_percent"):
                assert Decimal(got) == Decimal(sent), (path, key)
            else:
                assert got == sent, (path, key)


async def test_defaults_are_applied_and_echoed(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    minimal = {
        "initial_investment": usd("1000.00"),
        "contribution": usd("0.00"),
        "annual_return_percent": "5",
        "years": 10,
    }
    body = (await post(http, two_users, "/api/v1/forecasts/compound", minimal)).json()
    assert body["assumptions"] | {} == minimal | {
        "contribution_growth_percent": "0",
        "inflation_percent": "0",
        "annual_fee_percent": "0",
        "compounding_frequency": "monthly",
        "contribution_frequency": "monthly",
    }
    # 1000 at 5% compounded monthly for 10 years.
    assert body["projection"]["final_nominal"] == usd("1647.01")


async def test_compound_is_the_base_scenario(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    compound = (await post(http, two_users, "/api/v1/forecasts/compound", COMPOUND)).json()
    scenarios = (await post(http, two_users, "/api/v1/forecasts/scenarios", SCENARIOS)).json()
    assert set(compound) == {"currency", "projection", "assumptions", "as_of", "notice"}
    assert compound["projection"] == scenarios["scenarios"]["base"]
    _no_json_numbers(compound)


async def test_goal_returns_the_required_contribution(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    r = await post(http, two_users, "/api/v1/forecasts/goal", GOAL)
    assert r.status_code == 200, r.text
    body = r.json()
    # Closed form: (T - PV (1+i)^N) / (((1+i)^N - 1) / i), i = 7.5%/12, N = 240.
    assert body["required_contribution"] == usd("1725.37")
    assert body["reached_without_contributions"] is False
    assert body["projection"]["final_nominal"] == usd("999998.55")  # within rounding
    assert body["notice"] == NOTICE and body["assumptions"]["target_in_todays_money"] is False
    _no_json_numbers(body)

    real = (
        await post(
            http, two_users, "/api/v1/forecasts/goal", GOAL | {"target_in_todays_money": True}
        )
    ).json()
    assert Decimal(real["required_contribution"]["amount"]) > Decimal("1725.37")
    assert abs(Decimal(real["projection"]["final_real"]["amount"]) - 1000000) <= 2

    reached = (
        await post(http, two_users, "/api/v1/forecasts/goal", GOAL | {"target": usd("40000.00")})
    ).json()
    assert reached["reached_without_contributions"] is True
    assert reached["required_contribution"] == usd("0.00")


async def test_other_currencies_use_their_minor_units(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    jpy = {
        "initial_investment": {"amount": "1000000", "currency": "JPY"},
        "contribution": {"amount": "30000", "currency": "JPY"},
        "annual_return_percent": "3",
        "years": 25,
        "inflation_percent": "1",
    }
    body = (await post(http, two_users, "/api/v1/forecasts/compound", jpy)).json()
    assert body["currency"] == "JPY"
    assert body["projection"]["final_nominal"] == {"amount": "15495254", "currency": "JPY"}
    assert body["projection"]["nominal"][1]["value"].isdigit()


# ------------------------------------------------------------------------------------- limits


def _with(base: dict[str, Any], **changes: Any) -> dict[str, Any]:
    out = dict(base)
    for key, value in changes.items():
        if value is ...:
            out.pop(key)
        else:
            out[key] = value
    return out


INVALID = [
    ("initial too high", _with(SCENARIOS, initial_investment=usd("1000000000.01"))),
    ("initial negative", _with(SCENARIOS, initial_investment=usd("-0.01"))),
    ("initial too many decimals", _with(SCENARIOS, initial_investment=usd("1.001"))),
    ("initial a JSON number",
     _with(SCENARIOS, initial_investment={"amount": 1, "currency": "USD"})),
    ("contribution too high", _with(SCENARIOS, contribution=usd("10000000.01"))),
    ("contribution negative", _with(SCENARIOS, contribution=usd("-1.00"))),
    ("mixed currencies", _with(SCENARIOS, contribution={"amount": "1", "currency": "EUR"})),
    ("JPY with decimals", _with(SCENARIOS, initial_investment={"amount": "1.5", "currency": "JPY"},
                                contribution={"amount": "1", "currency": "JPY"})),
    ("return too low",
     _with(SCENARIOS, annual_return_percent="-20.01", conservative_return_percent="-21")),
    ("return too high",
     _with(SCENARIOS, annual_return_percent="50.01", growth_return_percent="51")),
    ("return 3 decimals", _with(SCENARIOS, annual_return_percent="8.001")),
    ("return a JSON number", _with(SCENARIOS, annual_return_percent=8)),
    ("return with exponent", _with(SCENARIOS, annual_return_percent="8E0")),
    ("years zero", _with(SCENARIOS, years=0)),
    ("years too many", _with(SCENARIOS, years=61)),
    ("years fractional", _with(SCENARIOS, years=20.5)),
    ("years as text", _with(SCENARIOS, years="20")),
    ("years boolean", _with(SCENARIOS, years=True)),
    ("growth negative", _with(SCENARIOS, contribution_growth_percent="-0.01")),
    ("growth too high", _with(SCENARIOS, contribution_growth_percent="20.01")),
    ("inflation too high", _with(SCENARIOS, inflation_percent="30.01")),
    ("inflation negative", _with(SCENARIOS, inflation_percent="-1")),
    ("fee too high", _with(SCENARIOS, annual_fee_percent="5.01")),
    ("fee negative", _with(SCENARIOS, annual_fee_percent="-0.01")),
    ("unknown frequency", _with(SCENARIOS, compounding_frequency="daily")),
    ("unknown contribution frequency", _with(SCENARIOS, contribution_frequency="weekly")),
    ("conservative above base", _with(SCENARIOS, conservative_return_percent="8.01")),
    ("growth below base", _with(SCENARIOS, growth_return_percent="7.99")),
    ("unknown field", _with(SCENARIOS, expected_return="9")),
    ("missing years", _with(SCENARIOS, years=...)),
    ("missing scenario rate", _with(SCENARIOS, growth_return_percent=...)),
    ("the mobile name", _with(SCENARIOS, contribution=..., monthly_contribution=usd("500.00"))),
]  # fmt: skip


@pytest.mark.parametrize(("name", "body"), INVALID, ids=[n for n, _ in INVALID])
async def test_inputs_outside_the_limits_are_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    name: str,
    body: dict[str, Any],
) -> None:
    r = await post(http, two_users, "/api/v1/forecasts/scenarios", body)
    assert r.status_code == 422, (name, r.text)
    problem = r.json()
    assert problem["type"].endswith("/validation")
    assert "1000000000.01" not in r.text and "50.01" not in r.text  # values are not echoed


GOAL_INVALID = [
    ("target zero", _with(GOAL, target=usd("0.00"))),
    ("target too high", _with(GOAL, target=usd("10000000000.01"))),
    ("target other currency", _with(GOAL, target={"amount": "1000", "currency": "EUR"})),
    ("target too many decimals", _with(GOAL, target=usd("1.001"))),
    ("contribution not accepted", _with(GOAL, contribution=usd("1.00"))),
    ("missing target", _with(GOAL, target=...)),
    ("today's money not boolean", _with(GOAL, target_in_todays_money="yes")),
]


@pytest.mark.parametrize(("name", "body"), GOAL_INVALID, ids=[n for n, _ in GOAL_INVALID])
async def test_goal_inputs_outside_the_limits_are_refused(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    name: str,
    body: dict[str, Any],
) -> None:
    r = await post(http, two_users, "/api/v1/forecasts/goal", body)
    assert r.status_code == 422, (name, r.text)


EDGES = [
    _with(SCENARIOS, initial_investment=usd("0"), contribution=usd("0")),
    _with(SCENARIOS, initial_investment=usd("1000000000.00"), contribution=usd("10000000.00"),
          years=60, annual_return_percent="50", growth_return_percent="50",
          conservative_return_percent="50", contribution_growth_percent="20",
          inflation_percent="30", annual_fee_percent="5"),
    _with(SCENARIOS, annual_return_percent="-20", conservative_return_percent="-20",
          growth_return_percent="-20", years=1, compounding_frequency="yearly",
          contribution_frequency="quarterly"),
    _with(SCENARIOS, conservative_return_percent="8.00", growth_return_percent="8"),
]  # fmt: skip


@pytest.mark.parametrize("body", EDGES)
async def test_the_edges_of_the_limits_are_accepted(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    body: dict[str, Any],
) -> None:
    r = await post(http, two_users, "/api/v1/forecasts/scenarios", body)
    assert r.status_code == 200, r.text
    _no_json_numbers(r.json())


async def test_goal_edges_are_accepted(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    for target in ("0.01", "10000000000.00"):
        r = await post(http, two_users, "/api/v1/forecasts/goal", _with(GOAL, target=usd(target)))
        assert r.status_code == 200, r.text


# ------------------------------------------------------------------------------ authentication


@pytest.mark.security
@pytest.mark.parametrize("path", list(PATHS))
async def test_a_signed_in_user_is_required(http: httpx.AsyncClient, path: str) -> None:
    assert (await http.post(path, json=PATHS[path])).status_code == 401
    bad = {"Authorization": "Bearer not-a-token"}
    assert (await http.post(path, json=PATHS[path], headers=bad)).status_code == 401


VECTORS = json.loads(
    (Path(__file__).parents[1] / "golden" / "forecast_vectors.json").read_text("utf-8")
)


@pytest.mark.parametrize("case", VECTORS["cases"], ids=lambda c: c["name"])
async def test_every_golden_vector_through_the_api(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
    case: dict[str, Any],
) -> None:
    spec = case["input"]
    currency = spec["currency"]
    body = {
        "initial_investment": {"amount": spec["initial"], "currency": currency},
        "contribution": {"amount": spec["contribution"], "currency": currency},
        "annual_return_percent": spec["annual_return_percent"],
        "years": spec["years"],
        "compounding_frequency": spec["compounding"],
        "contribution_frequency": spec["contribution_frequency"],
    } | {
        k: spec[k]
        for k in ("contribution_growth_percent", "inflation_percent", "annual_fee_percent")
        if k in spec
    }
    r = await post(http, two_users, "/api/v1/forecasts/compound", body)
    assert r.status_code == 200, r.text
    p = r.json()["projection"]
    got = {k: p[k]["amount"] for k in case["expected"]}
    assert got == case["expected"]


async def test_the_notice_says_projections_are_not_guaranteed(
    http: httpx.AsyncClient,
    two_users: TwoUsers,  # noqa: F811
) -> None:
    for path, request in PATHS.items():
        notice = (await post(http, two_users, path, request)).json()["notice"]
        assert "not guaranteed" in notice and "illustrative" in notice, path
