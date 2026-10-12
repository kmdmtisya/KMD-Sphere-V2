"""FX refresh soak on the local stack (P11-T11, approved option A: no real vendor).

Days of operation are simulated against a freshly migrated database with a simulated clock. The
two sources mirror the default provider order (`fx_provider_order`): a daily ECB-like source that
publishes at 15:00 UTC on weekdays and lacks AED and KES, then an hourly commercial source with
a monthly quota. Both are wrapped in the production `ResilientProvider` (retry and circuit
breaker on the simulated clock), so the request counts are what a deployment would send. Every
30 simulated seconds users press refresh (worst case: someone always does), and the hourly job
runs at :05, all through `refresh_once_per_window`. Outages and a "quota reached" spell are
scripted. Every simulated minute the rate board is read and checked.

Checks:
- **Quota:** in a window where a source answers, it is asked at most once; the whole run stays
  within the monthly budget prorated to the run; normal operation extrapolated to a 31-day month
  stays within the budget; the simulated quota is never hit unscripted.
- **Honest status:** no rate older than its source's current window is labelled current, and
  every rate shown is one a source actually published (no invented or carried-forward values).
- **Recovery:** after each outage the rates are current again within one refresh window, with
  no manual action.

Long run with a report (needs the compose database):

    cd backend
    uv run python -m tests.fx.soak --hours 96 --out ../reports/fx-soak/fx-soak-96h.json

A shorter run is part of the test suite (tests/fx/test_soak.py)."""

import argparse
import asyncio
import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.modules.fx.board import RateBoard
from app.modules.fx.refresh import refresh_once_per_window, window_key
from app.modules.fx.status import RateStatus, StatusPolicy
from app.modules.market_data.providers.errors import (
    ProviderUnavailable,
    RateLimited,
    UnsupportedKind,
)
from app.modules.market_data.providers.models import (
    AssetKind,
    FxBatch,
    FxQuote,
    PricePoint,
    PriceQuote,
    Provenance,
)
from app.modules.market_data.providers.resilience import CircuitBreaker, ResilientProvider

TICK = timedelta(seconds=30)
BOARD_EVERY = timedelta(minutes=1)
CALLERS_PER_TICK = 2  # two users pressing refresh at the same moment, every 30 seconds
JOB_MINUTE = 5  # the hourly worker job (app/worker/settings.py)
MONTH_HOURS = 31 * 24
PIVOT = "USD"
RATES = {
    "AED": Decimal("3.6725"),
    "AUD": Decimal("1.5112"),
    "CAD": Decimal("1.3705"),
    "CHF": Decimal("0.8634"),
    "EUR": Decimal("0.9216"),
    "GBP": Decimal("0.7712"),
    "JPY": Decimal("149.83"),
    "KES": Decimal("129.15"),
    "ZAR": Decimal("17.8421"),
}
ECB = "ecb"  # the name the status policy treats as a daily publisher
COMMERCIAL = "soak-commercial"
Mode = Literal["down", "quota"]


@dataclass
class Clock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


async def _no_sleep(_: float) -> None:
    """Retry back-off takes no simulated time (the conservative case: retries come faster)."""


@dataclass
class Outage:
    provider: str  # a source name, or "all"
    mode: Mode
    start_minute: int  # minutes from the start of the run
    end_minute: int


@dataclass
class SoakSource:
    """A scripted FX source on the simulated clock; counts every request that reaches it."""

    name: str
    clock: Clock
    daily: bool
    lacks: frozenset[str] = frozenset()
    monthly_quota: int | None = None
    mode: Mode | None = None
    requests: int = 0
    failed: int = 0
    unscripted_quota_refusals: int = 0
    per_window: Counter[str] = field(default_factory=Counter)
    per_hour: Counter[int] = field(default_factory=Counter)
    start: datetime | None = None
    window_minutes: int = 15
    supported_kinds: frozenset[AssetKind] = frozenset()

    def published(self) -> datetime:
        now = self.clock.now
        if not self.daily:
            return now.replace(minute=0, second=0, microsecond=0)
        day = now.replace(hour=15, minute=0, second=0, microsecond=0)
        if now < day:
            day -= timedelta(days=1)
        while day.weekday() >= 5:  # no publication on Saturday or Sunday
            day -= timedelta(days=1)
        return day

    async def get_fx_rates(self, base: str, quotes: list[str]) -> FxBatch:
        self.requests += 1
        self.per_window[window_key(self.clock.now, self.window_minutes)] += 1
        if self.start is not None:
            self.per_hour[int((self.clock.now - self.start) / timedelta(hours=1))] += 1
        if self.mode == "down":
            self.failed += 1
            raise ProviderUnavailable(f"{self.name} down (soak)")
        if self.mode == "quota":
            self.failed += 1
            raise RateLimited(f"{self.name} monthly quota reached (soak)", None)
        if self.monthly_quota is not None and self.requests > self.monthly_quota:
            self.failed += 1
            self.unscripted_quota_refusals += 1
            raise RateLimited(f"{self.name} monthly quota reached", None)
        published = self.published()
        rates = [
            FxQuote(base, q, RATES[q], Provenance(self.name, published, self.clock.now))
            for q in quotes
            if q in RATES and q not in self.lacks
        ]
        return FxBatch(rates, [q for q in quotes if q not in RATES or q in self.lacks])

    async def get_fx_rate(self, base: str, quote: str) -> FxQuote:  # pragma: no cover
        raise UnsupportedKind("batch only")

    async def get_fx_history(  # pragma: no cover
        self, base: str, quote: str, start: date, end: date
    ) -> list[FxQuote]:
        raise UnsupportedKind("no history in the soak")

    async def get_quote(self, symbol: str, kind: AssetKind) -> PriceQuote:  # pragma: no cover
        raise UnsupportedKind("FX only")

    async def get_history(  # pragma: no cover
        self, symbol: str, kind: AssetKind, start: date, end: date
    ) -> list[PricePoint]:
        raise UnsupportedKind("FX only")


@dataclass
class OutageResult:
    provider: str
    mode: str
    start_minute: int
    end_minute: int
    degraded_during: bool  # some rate stopped being current, so the outage was felt
    requests_during: dict[str, int]
    recovered_after_minutes: int | None  # None: not current again by the end of the run


@dataclass
class SoakReport:
    hours: int
    started_at: str
    ticks: int
    board_reads: int
    refreshes_run: int
    requests: dict[str, int]
    failed_requests: dict[str, int]
    max_requests_in_a_healthy_window: dict[str, int]
    max_requests_in_an_hour: dict[str, int]
    budget_per_month: int
    budget_prorated_to_run: int
    normal_month_extrapolated: dict[str, int]
    unscripted_quota_refusals: int
    current_but_too_old: int
    invented_values: int
    status_counts: dict[str, int]
    weekend_status_counts: dict[str, int]
    outages: list[OutageResult]

    def failures(self, window_minutes: int) -> list[str]:
        """The acceptance checks that did not hold; empty when the soak passed."""
        out: list[str] = []
        for name, n in self.max_requests_in_a_healthy_window.items():
            if n > 1:
                out.append(f"{name}: {n} requests in one healthy window")
        for name, n in self.requests.items():
            if n > self.budget_prorated_to_run:
                out.append(f"{name}: {n} requests > prorated budget {self.budget_prorated_to_run}")
        for name, n in self.normal_month_extrapolated.items():
            if n > self.budget_per_month:
                out.append(f"{name}: normal month {n} > budget {self.budget_per_month}")
        if self.unscripted_quota_refusals:
            out.append(f"quota hit unscripted {self.unscripted_quota_refusals} times")
        if self.current_but_too_old:
            out.append(f"{self.current_but_too_old} rates labelled current but too old")
        if self.invented_values:
            out.append(f"{self.invented_values} rates shown that no source published")
        for o in self.outages:
            if not o.degraded_during:
                out.append(f"outage {o.provider}/{o.mode} at {o.start_minute} min was never felt")
            if o.recovered_after_minutes is None or o.recovered_after_minutes > window_minutes:
                out.append(
                    f"outage {o.provider}/{o.mode} at {o.start_minute} min: recovered after "
                    f"{o.recovered_after_minutes} minutes"
                )
        return out


def default_outages(hours: int) -> list[Outage]:
    """Scaled to the run: the commercial source down, then refusing with "quota reached", then
    every source down. Each lasts longer than the hourly current window (2 hours) so the board
    must show the rates ageing, and ends 7 minutes into a refresh window, so recovery has to
    wait for the next window."""
    h = 60
    if hours >= 48:
        return [
            Outage(COMMERCIAL, "down", 10 * h, 13 * h + 7),
            Outage(COMMERCIAL, "quota", 18 * h, 21 * h + 7),
            Outage("all", "down", 30 * h, 36 * h + 7),
        ]
    if hours < 12:
        raise ValueError("a soak needs at least 12 simulated hours")
    return [
        Outage(COMMERCIAL, "down", 1 * h, 4 * h + 7),
        Outage("all", "down", 6 * h, 9 * h + 7),
    ]


def _ecb_weekend(now: datetime) -> bool:
    """From Saturday until Monday's publication, when the daily source publishes nothing new."""
    return now.weekday() >= 5 or (now.weekday() == 0 and now.hour < 15)


async def soak(
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    hours: int,
    outages: list[Outage],
    start: datetime,
) -> SoakReport:
    clock = Clock(start)
    window = settings.fx_refresh_window_minutes
    ecb = SoakSource(ECB, clock, daily=True, lacks=frozenset({"AED", "KES"}))
    commercial = SoakSource(
        COMMERCIAL, clock, daily=False, monthly_quota=settings.fx_monthly_request_budget
    )
    raw = (ecb, commercial)
    for s in raw:
        s.start, s.window_minutes = start, window
    sources = tuple(
        ResilientProvider(s, breaker=CircuitBreaker(clock=clock), sleep=_no_sleep) for s in raw
    )
    policy = StatusPolicy.from_settings(settings)
    ticks = int(timedelta(hours=hours) / TICK)
    board_every = int(BOARD_EVERY / TICK)
    unhealthy_windows: dict[str, set[str]] = {s.name: set() for s in raw}
    refreshes_run = board_reads = too_old = invented = 0
    counts: Counter[str] = Counter()
    weekend: Counter[str] = Counter()
    timeline: list[tuple[datetime, bool]] = []  # (time, every rate current)
    at_start: dict[int, dict[str, int]] = {}  # requests so far when outage i began
    during: dict[int, dict[str, int]] = {}  # requests made while outage i lasted

    for tick in range(ticks):
        clock.now = start + tick * TICK
        elapsed = (clock.now - start) / timedelta(minutes=1)
        for s in raw:
            s.mode = next(
                (
                    o.mode
                    for o in outages
                    if o.provider in (s.name, "all") and o.start_minute <= elapsed < o.end_minute
                ),
                None,
            )
            if s.mode is not None:
                unhealthy_windows[s.name].add(window_key(clock.now, window))
        for i, o in enumerate(outages):
            if elapsed >= o.start_minute and i not in at_start:
                at_start[i] = {s.name: s.requests for s in raw}
            if elapsed >= o.end_minute and i in at_start and i not in during:
                during[i] = {s.name: s.requests - at_start[i][s.name] for s in raw}
        job = clock.now.minute == JOB_MINUTE and clock.now.second == 0
        callers = CALLERS_PER_TICK + (1 if job else 0)
        for _ in range(callers):
            try:
                run = await refresh_once_per_window(sessions, sources, PIVOT, clock.now, window)
            except ProviderUnavailable:
                continue  # every source failed: nothing stored, the window is released
            refreshes_run += run.ran
        if tick % board_every:
            continue
        async with sessions() as session:
            lines = [
                line
                for line in await RateBoard(session, policy).lines(PIVOT, clock.now)
                if line.currency in RATES
            ]
        board_reads += 1
        for line in lines:
            counts[line.status.value] += 1
            if _ecb_weekend(clock.now) and line.provider == ECB:
                weekend[line.status.value] += 1
            if line.status is RateStatus.UNAVAILABLE:
                continue
            assert line.rate_timestamp is not None and line.provider is not None
            if line.rate != RATES[line.currency] or line.rate_timestamp > clock.now:
                invented += 1
            if (
                line.status is RateStatus.CURRENT
                and clock.now - line.rate_timestamp > policy.windows(line.provider).current
            ):
                too_old += 1
        timeline.append((clock.now, all(line.status is RateStatus.CURRENT for line in lines)))

    results: list[OutageResult] = []
    for i, o in enumerate(outages):
        begin = start + timedelta(minutes=o.start_minute)
        end = start + timedelta(minutes=o.end_minute)
        seen = [ok for t, ok in timeline if begin <= t < end]
        back = next((t for t, ok in timeline if t >= end and ok), None)
        results.append(
            OutageResult(
                o.provider,
                o.mode,
                o.start_minute,
                o.end_minute,
                degraded_during=not all(seen),
                requests_during=during.get(i, {}),
                recovered_after_minutes=None
                if back is None
                else int((back - end) / timedelta(minutes=1)),
            )
        )

    normal_hours = [
        h
        for h in range(hours)
        if not any(o.start_minute < (h + 1) * 60 and h * 60 < o.end_minute for o in outages)
    ]
    budget = settings.fx_monthly_request_budget
    return SoakReport(
        hours=hours,
        started_at=start.isoformat(),
        ticks=ticks,
        board_reads=board_reads,
        refreshes_run=refreshes_run,
        requests={s.name: s.requests for s in raw},
        failed_requests={s.name: s.failed for s in raw},
        max_requests_in_a_healthy_window={
            s.name: max(
                (n for w, n in s.per_window.items() if w not in unhealthy_windows[s.name]),
                default=0,
            )
            for s in raw
        },
        max_requests_in_an_hour={s.name: max(s.per_hour.values(), default=0) for s in raw},
        budget_per_month=budget,
        budget_prorated_to_run=budget * hours // MONTH_HOURS,
        normal_month_extrapolated={
            s.name: sum(s.per_hour[h] for h in normal_hours)
            * MONTH_HOURS
            // max(len(normal_hours), 1)
            for s in raw
        },
        unscripted_quota_refusals=sum(s.unscripted_quota_refusals for s in raw),
        current_but_too_old=too_old,
        invented_values=invented,
        status_counts=dict(counts),
        weekend_status_counts=dict(weekend),
        outages=results,
    )


# A Thursday, so a 96-hour run covers two weekdays and a weekend (the daily source's rates
# age past 36 hours on Sunday at 03:00).
DEFAULT_START = datetime(2031, 6, 5, tzinfo=UTC)


async def _main(hours: int) -> dict[str, object]:
    from tests.db_fixtures import throwaway_database

    async with throwaway_database(Settings(environment="test")) as settings:
        engine = create_async_engine(settings.sqlalchemy_url)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            report = await soak(sessions, settings, hours, default_outages(hours), DEFAULT_START)
        finally:
            await engine.dispose()
    return asdict(report) | {"failures": report.failures(settings.fx_refresh_window_minutes)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--hours", type=int, default=96)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    text = json.dumps(asyncio.run(_main(args.hours)), indent=2) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text, end="")
