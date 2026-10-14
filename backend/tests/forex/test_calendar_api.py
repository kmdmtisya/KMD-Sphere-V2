# ruff: noqa: F811 (imported pytest fixtures are used by name as test parameters)
"""The economic calendar on the real database (P13-T04): idempotent ingestion where a release
gains its actual value and never loses it, the calendar API with confirmed, expected and
commentary content apart, release times in UTC and in the user's time zone, event-risk windows,
policy-rate differentials, validation and the feature flag."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.modules.forex.calendar.ingest import ingest
from app.modules.forex.calendar.sources import DemoCalendarSource
from tests import auth_helpers as ah
from tests.authz_harness import TestUser, make_user
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.forex.test_forex_api import app, http, sessions, user  # noqa: F401

pytestmark = [pytest.mark.integration, pytest.mark.security]
PATH = "/api/v1/forex"
BEFORE = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)  # US CPI is released at 12:30 UTC
AFTER = datetime(2026, 10, 12, 13, 0, tzinfo=UTC)


async def load(sessions: async_sessionmaker[AsyncSession], now: datetime) -> Any:
    async with sessions() as s:
        return await ingest(s, DemoCalendarSource(), date(2026, 10, 1), date(2026, 10, 31), now)


def window(**extra: Any) -> dict[str, Any]:
    return {
        "start": "2026-10-12T00:00:00+00:00",
        "end": "2026-10-13T00:00:00+00:00",
        **extra,
    }


# ------------------------------------------------------------------------------- ingestion
async def test_ingestion_is_idempotent_and_a_release_gains_its_actual_once(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    first = await load(sessions, BEFORE)
    # October in UTC: 14 DEMO events (the 1 October Tokyo release is on 30 September in UTC);
    # by 12:00 on the 12th, six have been released. Ten policy rates are in effect.
    assert (first.added, first.released, first.rates) == (14, 6, 10)
    again = await load(sessions, BEFORE)
    assert (again.added, again.updated, again.released, again.rates) == (0, 0, 0, 0)
    after = await load(sessions, AFTER)
    assert after.added == 0 and after.released == 1  # the 12:30 US CPI release
    async with sessions() as s:
        row = (
            await s.execute(
                text(
                    "SELECT actual, actual_seen_at, forecast, previous FROM forex_economic_events "
                    "WHERE source_event_id = 'us_cpi:2026-10-12'"
                )
            )
        ).one()
    assert row.actual is not None and row.actual_seen_at == AFTER
    # A later run that sees no actual (an earlier clock) never clears the published value.
    await load(sessions, BEFORE)
    async with sessions() as s:
        kept = await s.scalar(
            text(
                "SELECT actual FROM forex_economic_events "
                "WHERE source_event_id = 'us_cpi:2026-10-12'"
            )
        )
    assert kept == row.actual


# ------------------------------------------------------------------------------- calendar
async def test_the_calendar_keeps_confirmed_expected_and_commentary_apart(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await load(sessions, AFTER)
    r = await http.get(f"{PATH}/calendar", params=window(), headers=user.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["timezone"] == "UTC" and "not data" in body["notice"]
    cpi = next(i for i in body["items"] if i["name"] == "DEMO United States consumer prices (m/m)")
    assert cpi["scheduled_at"] == "2026-10-12T12:30:00Z"
    assert cpi["confirmed"]["released"] is True and cpi["confirmed"]["actual"] is not None
    assert cpi["confirmed"]["unit"] == "%" and cpi["confirmed"]["previous"] is not None
    assert set(cpi["expectation"]) == {"forecast"} and cpi["commentary"] is None
    assert (cpi["is_demo"], cpi["licence_status"], cpi["source"]) == (True, "demo", "demo")
    assert cpi["risk_window"] == {
        "name": cpi["name"],
        "currencies": ["USD"],
        "importance": "high",
        "scheduled_at": "2026-10-12T12:30:00Z",
        "starts": "2026-10-12T12:00:00Z",
        "ends": "2026-10-12T13:30:00Z",
    }
    r = await http.get(
        f"{PATH}/calendar",
        params={"start": "2026-10-07T00:00:00+00:00", "end": "2026-10-08T00:00:00+00:00"},
        headers=user.headers,
    )
    fed = next(i for i in r.json()["items"] if i["kind"] == "central_bank_decision")
    assert fed["commentary"]["label"] == "Commentary from the source: not confirmed data"
    assert "not confirmed data" in fed["commentary"]["text"]
    assert fed["confirmed"]["actual"] == "4.5"


async def test_release_times_are_shown_in_the_users_time_zone(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await load(sessions, AFTER)
    r = await http.patch(
        "/api/v1/me/preferences", json={"timezone": "Africa/Nairobi"}, headers=user.headers
    )
    assert r.status_code == 200, r.text
    body = (
        await http.get(f"{PATH}/calendar", params=window(currency="USD"), headers=user.headers)
    ).json()
    assert body["timezone"] == "Africa/Nairobi"
    cpi = next(i for i in body["items"] if "consumer prices" in i["name"])
    assert cpi["scheduled_at"] == "2026-10-12T12:30:00Z"
    assert cpi["scheduled_local"] == "2026-10-12T15:30:00+03:00"
    tokyo = (
        await http.get(f"{PATH}/calendar", params=window(tz="Asia/Tokyo"), headers=user.headers)
    ).json()
    assert tokyo["timezone"] == "Asia/Tokyo"
    assert (
        next(i for i in tokyo["items"] if "consumer prices" in i["name"])["scheduled_local"]
        == "2026-10-12T21:30:00+09:00"
    )
    assert (
        await http.get(f"{PATH}/calendar", params=window(tz="Mars/Olympus"), headers=user.headers)
    ).status_code == 422


async def test_filters_by_currency_and_importance(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await load(sessions, AFTER)
    month = {"start": "2026-10-01T00:00:00+00:00", "end": "2026-11-01T00:00:00+00:00"}
    everything = (await http.get(f"{PATH}/calendar", params=month, headers=user.headers)).json()[
        "items"
    ]
    kes = (
        await http.get(
            f"{PATH}/calendar", params={**month, "currency": "KES"}, headers=user.headers
        )
    ).json()["items"]
    assert kes and all("KES" in i["currencies"] for i in kes)
    high = (
        await http.get(
            f"{PATH}/calendar", params={**month, "min_importance": "high"}, headers=user.headers
        )
    ).json()["items"]
    assert high and all(i["importance"] == "high" for i in high)
    assert len(high) < len(everything)
    times = [i["scheduled_at"] for i in everything]
    assert times == sorted(times)


@pytest.mark.parametrize(
    "bad",
    [
        {"start": "2026-10-12T00:00:00", "end": "2026-10-13T00:00:00+00:00"},
        {"start": "2026-10-13T00:00:00+00:00", "end": "2026-10-12T00:00:00+00:00"},
        {"start": "2026-01-01T00:00:00+00:00", "end": "2026-12-31T00:00:00+00:00"},
        {**window(), "currency": "usd"},
        {**window(), "min_importance": "urgent"},
    ],
)
async def test_bad_calendar_requests_are_refused(
    http: httpx.AsyncClient, user: TestUser, bad: dict[str, Any]
) -> None:
    assert (await http.get(f"{PATH}/calendar", params=bad, headers=user.headers)).status_code == 422


# ------------------------------------------------------------------------- risk windows
async def test_risk_windows_for_a_pair_at_a_time(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await load(sessions, AFTER)
    at = {"at": "2026-10-12T12:10:00+00:00"}
    eur_usd = (
        await http.get(
            f"{PATH}/calendar/risk", params={"instrument": "EUR_USD", **at}, headers=user.headers
        )
    ).json()
    assert eur_usd["in_window"] is True
    assert [w["name"] for w in eur_usd["windows"]] == ["DEMO United States consumer prices (m/m)"]
    gbp_jpy = (
        await http.get(
            f"{PATH}/calendar/risk", params={"instrument": "GBP_JPY", **at}, headers=user.headers
        )
    ).json()
    assert gbp_jpy == {**gbp_jpy, "in_window": False, "windows": []}
    after_close = {"instrument": "EUR_USD", "at": "2026-10-12T13:30:00+00:00"}
    assert (
        await http.get(f"{PATH}/calendar/risk", params=after_close, headers=user.headers)
    ).json()["in_window"] is False
    r = await http.get(
        f"{PATH}/calendar/risk", params={"instrument": "EUR_SEK"}, headers=user.headers
    )
    assert r.status_code == 404
    now = await http.get(
        f"{PATH}/calendar/risk", params={"instrument": "EUR_USD"}, headers=user.headers
    )
    assert now.status_code == 200 and now.json()["at"]


# ---------------------------------------------------------------------- policy rates
async def test_the_rate_differential_is_base_minus_quote_with_sources(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await load(sessions, AFTER)
    body = (
        await http.get(
            f"{PATH}/policy-rates/differential",
            params={"instrument": "EUR_USD"},
            headers=user.headers,
        )
    ).json()
    assert body["base"]["currency"] == "EUR" and body["base"]["rate"] == "2.25"
    assert body["quote"]["currency"] == "USD" and body["quote"]["rate"] == "4.5"
    assert body["differential"] == "-2.25"
    assert body["base"]["is_demo"] is True and body["base"]["effective_date"] == "2026-09-17"
    kes = (
        await http.get(
            f"{PATH}/policy-rates/differential",
            params={"instrument": "USD_KES"},
            headers=user.headers,
        )
    ).json()
    assert kes["differential"] == "-5"  # 4.50 - 9.50


async def test_a_missing_rate_gives_no_differential_rather_than_a_guess(
    http: httpx.AsyncClient, user: TestUser, sessions: async_sessionmaker[AsyncSession]
) -> None:
    await load(sessions, AFTER)
    async with sessions() as s:
        await s.execute(text("DELETE FROM forex_policy_rates WHERE currency = 'ZAR'"))
        await s.commit()
    body = (
        await http.get(
            f"{PATH}/policy-rates/differential",
            params={"instrument": "USD_ZAR"},
            headers=user.headers,
        )
    ).json()
    assert (
        body["quote"] is None and body["differential"] is None and body["base"]["currency"] == "USD"
    )


# ------------------------------------------------------------------- sign-in and flag
async def test_the_calendar_needs_sign_in_and_the_flag(
    http: httpx.AsyncClient, migrated_settings: Settings
) -> None:
    routes = [
        ("calendar", window()),
        ("calendar/risk", {"instrument": "EUR_USD"}),
        ("policy-rates/differential", {"instrument": "EUR_USD"}),
    ]
    for path, params in routes:
        assert (await http.get(f"{PATH}/{path}", params=params)).status_code == 401, path
    off = create_app(
        migrated_settings.model_copy(update={"forex_enabled": False}),
        readiness_checks={},
        token_verifier=ah.verifier(),
    )
    transport = httpx.ASGITransport(app=off, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            someone = await make_user(client, "calendar-off")
            for path, params in routes:
                r = await client.get(f"{PATH}/{path}", params=params, headers=someone.headers)
                assert r.status_code == 404, path
    finally:
        await off.state.db.dispose()


def test_the_ingest_window_is_a_week_back_and_thirty_days_ahead() -> None:
    import inspect

    import app.worker.tasks as tasks

    source = inspect.getsource(tasks.forex_calendar_ingest_job)
    assert "timedelta(days=7)" in source and "timedelta(days=30)" in source
    assert timedelta(days=30) > timedelta(days=7)
