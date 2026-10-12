"""The FX refresh soak (P11-T11), 12 simulated hours: quota, honest status and recovery under
user pressure, a commercial outage and a total outage. The 96-hour run is `tests/fx/soak.py`."""

from collections.abc import AsyncIterator
from math import ceil

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from tests.db_fixtures import migrated_settings  # noqa: F401
from tests.fx.soak import DEFAULT_START, RATES, SoakReport, default_outages, soak


@pytest.fixture(scope="module")
async def report(migrated_settings: Settings) -> AsyncIterator[SoakReport]:  # noqa: F811
    engine = create_async_engine(migrated_settings.sqlalchemy_url)
    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield await soak(sessions, migrated_settings, 12, default_outages(12), DEFAULT_START)
    finally:
        await engine.dispose()


async def test_the_soak_passes_every_check(
    report: SoakReport,
    migrated_settings: Settings,  # noqa: F811
) -> None:
    assert report.failures(migrated_settings.fx_refresh_window_minutes) == []


async def test_providers_are_asked_once_per_window_and_a_normal_month_fits_the_budget(
    report: SoakReport,
) -> None:
    assert report.max_requests_in_a_healthy_window == {"ecb": 1, "soak-commercial": 1}
    # The ECB never supplies AED and KES, so the commercial source is asked every window.
    assert report.normal_month_extrapolated == {"ecb": 2976, "soak-commercial": 2976}
    assert report.unscripted_quota_refusals == 0


async def test_an_outage_costs_at_most_one_attempt_per_window_whoever_presses_refresh(
    report: SoakReport,
    migrated_settings: Settings,  # noqa: F811
) -> None:
    window = migrated_settings.fx_refresh_window_minutes
    for outage in report.outages:
        windows = ceil((outage.end_minute - outage.start_minute) / window) + 1
        for requests in outage.requests_during.values():
            # One refresh per window; inside it the resilient wrapper tries 3 times.
            assert requests <= 3 * windows, outage
    assert max(report.max_requests_in_an_hour.values()) <= 3 * (60 // window)


async def test_rates_are_never_labelled_current_when_too_old_or_invented(
    report: SoakReport,
) -> None:
    assert report.board_reads == 12 * 60
    assert report.current_but_too_old == 0
    assert report.invented_values == 0
    assert report.status_counts.get("cached", 0) > 0, "the outages showed rates ageing"
    seen = sum(report.status_counts.values())
    assert seen == report.board_reads * len(RATES)


async def test_rates_are_current_again_within_one_window_of_every_outage(
    report: SoakReport,
    migrated_settings: Settings,  # noqa: F811
) -> None:
    for outage in report.outages:
        assert outage.degraded_during, outage
        assert outage.recovered_after_minutes is not None
        assert outage.recovered_after_minutes <= migrated_settings.fx_refresh_window_minutes
