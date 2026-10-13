"""Builds the forex provider and policies from settings. DEC-19: the simulated provider is the
only one that can be built; a vendor adapter exists (`oanda.py`) but is not wired here until a
vendor and its licence are approved."""

from datetime import timedelta

from app.core.config import Settings
from app.modules.forex.instruments.registry import load_registry
from app.modules.forex.marketdata.fake import FakeForexProvider
from app.modules.forex.marketdata.monitor import Clock, HeartbeatPolicy, utc_now
from app.modules.forex.marketdata.provider import ResilientForexProvider
from app.modules.forex.marketdata.quality import QualityPolicy


def heartbeat_policy(settings: Settings) -> HeartbeatPolicy:
    return HeartbeatPolicy(
        timedelta(seconds=settings.forex_heartbeat_degraded_seconds),
        timedelta(seconds=settings.forex_heartbeat_disconnected_seconds),
    )


def quality_policy(settings: Settings) -> QualityPolicy:
    return QualityPolicy(stale_after=timedelta(seconds=settings.forex_quote_stale_seconds))


def build_provider(settings: Settings, clock: Clock = utc_now) -> ResilientForexProvider:
    if settings.forex_provider != "fake":  # pragma: no cover - the setting allows nothing else
        raise ValueError("only the simulated forex provider exists (DEC-19)")
    return ResilientForexProvider(FakeForexProvider(load_registry(), clock=clock))
