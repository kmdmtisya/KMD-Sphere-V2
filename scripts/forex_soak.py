"""Forex streaming soak and outage drill on the local stack (P13-T13.1, T13.2, T13.3).

Runs the real feed (`run_feed`: stream client, monitor, storage, gap backfill, fan-out) against
the simulated provider and a fresh, migrated PostgreSQL database (dropped afterwards), with
subscribers on every pair, in three phases:

1. **Soak**: the feed runs; subscribers drain continuously.
2. **Outage**: the provider fails every call (as an outage would) for `--outage-seconds`.
3. **Recovery**: the provider comes back; the feed reconnects and backfills the gap.

It then checks, and writes `reports/quality/p13-t13-forex-soak.md` (and a JSON copy):
- **No invented prices:** every stored quote equals the simulated provider's own price at its
  second (the provider is deterministic), is labelled `simulated`, and none is dated inside the
  outage;
- **Status:** the feed reports disconnected during the outage, and connected after;
- **Stale data:** the quote board never shows a fresh price during the outage;
- **Subscribers:** no out-of-order or duplicate quote;
- **Memory:** Python heap growth over the soak (tracemalloc);
- **Metrics:** the forex metrics are exposed, and the status gauge read 2 during the outage.

    cd backend && uv run python ../scripts/forex_soak.py --soak-seconds 600
Needs the compose PostgreSQL (or the CI service). Simulated data only (DEC-19).
"""

import argparse
import asyncio
import json
import sys
import time
import tracemalloc
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from opentelemetry.exporter.prometheus import PrometheusMetricReader  # noqa: E402
from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from prometheus_client import CollectorRegistry, generate_latest  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.config import Settings  # noqa: E402
from app.db.session import Database  # noqa: E402
from app.modules.forex.instruments.registry import load_registry  # noqa: E402
from app.modules.forex.marketdata.factory import quality_policy  # noqa: E402
from app.modules.forex.marketdata.fake import FakeForexProvider  # noqa: E402
from app.modules.forex.marketdata.feed import run_feed  # noqa: E402
from app.modules.forex.marketdata.gateway import QuoteHub  # noqa: E402
from app.modules.forex.marketdata.metrics import ForexMetrics  # noqa: E402
from app.modules.forex.marketdata.models import ForexCandle, ForexQuote  # noqa: E402
from app.modules.forex.marketdata.service import quote_board  # noqa: E402
from tests.db_fixtures import throwaway_database  # noqa: E402

OUT = ROOT / "reports" / "quality" / "p13-t13-forex-soak.md"
SUBSCRIBERS = 5


async def consume(hub: QuoteHub, name: str, known: set[str], stop: asyncio.Event, stats: dict[str, Any]) -> None:
    sub = hub.open(name)
    hub.subscribe(sub, sorted(known), known)
    last: dict[str, datetime] = {}
    try:
        while not stop.is_set():
            quotes, _ = await sub.drain(0.5)
            for rq in quotes:
                q = rq.quote
                stats["received"] += 1
                prev = last.get(q.instrument)
                if prev is not None and q.ts_provider < prev:
                    stats["out_of_order"] += 1
                if prev is not None and q.ts_provider == prev:
                    stats["duplicates"] += 1
                last[q.instrument] = q.ts_provider
    finally:
        hub.close(sub)


def metric_value(text: str, name: str) -> list[float]:
    out = []
    for line in text.splitlines():
        if line.startswith(name) and not line.startswith("#"):
            head, _, value = line.rpartition(" ")
            if head.split("{")[0] == name:
                out.append(float(value))
    return out


async def run(args: argparse.Namespace) -> dict[str, Any]:
    base = Settings(environment="test", forex_enabled=True, forex_feed_enabled=False)
    async with throwaway_database(base) as settings:
        settings = settings.model_copy(update={"forex_enabled": True})
        db = Database(settings)
        sessions = db.session_factory
        registry = load_registry()
        instruments = {s.code for s in registry.active(settings.forex_universe)}
        provider = FakeForexProvider(registry)
        hub = QuoteHub(max_connections=SUBSCRIBERS + 1, max_instruments=len(instruments))
        prom = CollectorRegistry()
        meters = MeterProvider(metric_readers=[PrometheusMetricReader(registry=prom)])
        metrics = ForexMetrics(meters, hub)
        stop_feed, stop_subs = asyncio.Event(), asyncio.Event()
        sub_stats = [Counter(received=0, out_of_order=0, duplicates=0) for _ in range(SUBSCRIBERS)]
        statuses: list[tuple[float, str]] = []
        board_during_outage: list[dict[str, str]] = []
        status_gauge_during_outage: list[float] = []

        tracemalloc.start()
        start = datetime.now(UTC)
        feed = asyncio.create_task(run_feed(settings, sessions, hub, stop_feed, provider=provider, metrics=metrics))
        await asyncio.sleep(3)  # registry, partitions and the first connection
        subs = [
            asyncio.create_task(consume(hub, f"soak-{k}", instruments, stop_subs, sub_stats[k]))
            for k in range(SUBSCRIBERS)
        ]

        async def watch_status() -> None:
            seen = None
            t0 = time.monotonic()
            while not stop_subs.is_set():
                status = hub.feed_status.get("fake")
                if status is not None and status.value != seen:
                    seen = status.value
                    statuses.append((round(time.monotonic() - t0, 1), seen))
                await asyncio.sleep(0.5)

        watcher = asyncio.create_task(watch_status())

        # Phase 1: soak.
        await asyncio.sleep(min(30, args.soak_seconds))
        heap_after_warmup = tracemalloc.get_traced_memory()[0]
        await asyncio.sleep(max(args.soak_seconds - 30, 0))
        heap_after_soak = tracemalloc.get_traced_memory()[0]

        # Phase 2: outage.
        outage_start = datetime.now(UTC)
        provider.down = True
        deadline = time.monotonic() + args.outage_seconds
        while time.monotonic() < deadline:
            await asyncio.sleep(10)
            now = datetime.now(UTC)
            async with sessions() as s:
                board = await quote_board(
                    s, "fake", sorted(instruments), now, quality_policy(settings),
                    timedelta(days=settings.forex_quote_lookback_days), hub,
                )
            board_during_outage.append(
                {"seconds": str(int((now - outage_start).total_seconds())), **dict(Counter(q.freshness for q in board))}
            )
            status_gauge_during_outage += metric_value(generate_latest(prom).decode(), "forex_feed_status")
        provider.down = False
        outage_end = datetime.now(UTC)

        # Phase 3: recovery.
        await asyncio.sleep(args.recovery_seconds)
        end = datetime.now(UTC)
        stop_subs.set()
        stop_feed.set()
        await asyncio.gather(*subs, watcher, return_exceptions=True)
        feed.cancel()
        await asyncio.gather(feed, return_exceptions=True)
        metrics_text = generate_latest(prom).decode()

        async with sessions() as s:
            rows = list(
                (
                    await s.execute(
                        select(ForexQuote).where(ForexQuote.ts_provider >= start, ForexQuote.ts_provider <= end)
                    )
                ).scalars()
            )
            backfilled = list(
                (
                    await s.execute(
                        select(ForexCandle).where(ForexCandle.ts >= outage_start - timedelta(minutes=1), ForexCandle.ts <= end)
                    )
                ).scalars()
            )
        await db.dispose()

    mismatches = [
        r for r in rows
        if (expected := provider.quote_at(r.instrument, r.ts_provider)).bid != r.bid
        or expected.ask != r.ask
        or r.data_type != "simulated"
    ]
    inside_outage = [r for r in rows if outage_start + timedelta(seconds=1) < r.ts_provider < outage_end - timedelta(seconds=1)]
    per_pair: dict[str, int] = defaultdict(int)
    for r in rows:
        per_pair[r.instrument] += 1
    fresh_during_outage = [b for b in board_during_outage if int(b.get("fresh", 0)) > 0]
    status_values = [s for _, s in statuses]
    return {
        "started": start.isoformat(),
        "ended": end.isoformat(),
        "soak_seconds": args.soak_seconds,
        "outage_seconds": args.outage_seconds,
        "recovery_seconds": args.recovery_seconds,
        "pairs": len(instruments),
        "quotes_stored": len(rows),
        "quotes_per_pair_min": min(per_pair.values()) if per_pair else 0,
        "quotes_per_pair_max": max(per_pair.values()) if per_pair else 0,
        "invented_or_altered_prices": len(mismatches),
        "quotes_dated_inside_outage": len(inside_outage),
        "candles_after_recovery": len(backfilled),
        "status_transitions": statuses,
        "degraded_seen": "degraded" in status_values,
        "disconnected_seen": "disconnected" in status_values,
        "connected_at_end": bool(status_values) and status_values[-1] == "connected",
        "board_during_outage": board_during_outage,
        "fresh_on_board_during_outage": len(fresh_during_outage),
        "subscribers": [dict(c) for c in sub_stats],
        "heap_bytes_after_warmup": heap_after_warmup,
        "heap_bytes_after_soak": heap_after_soak,
        "status_gauge_max_during_outage": max(status_gauge_during_outage, default=None),
        "metrics_exposed": sorted(
            {
                line.split("{")[0].split(" ")[0]
                for line in metrics_text.splitlines()
                if line.startswith("forex_")
            }
        ),
        "quotes_stored_counter": sum(metric_value(metrics_text, "forex_quotes_stored_total")),
    }


def verdicts(r: dict[str, Any]) -> list[tuple[str, bool, str]]:
    growth = r["heap_bytes_after_soak"] - r["heap_bytes_after_warmup"]
    return [
        ("Quotes stored for every pair", r["quotes_per_pair_min"] > 0, f"{r['quotes_stored']} quotes, {r['quotes_per_pair_min']} to {r['quotes_per_pair_max']} per pair"),
        ("No invented or altered price (each equals the provider's own price; all simulated)", r["invented_or_altered_prices"] == 0, f"{r['invented_or_altered_prices']} mismatches"),
        ("No quote dated inside the outage", r["quotes_dated_inside_outage"] == 0, f"{r['quotes_dated_inside_outage']} found"),
        ("Feed reported disconnected during the outage (a refused connection is reported at once; degraded is for a silent feed)", r["disconnected_seen"], " -> ".join(s for _, s in r["status_transitions"])),
        ("Feed connected again after recovery", r["connected_at_end"], f"last status: {r['status_transitions'][-1][1] if r['status_transitions'] else 'none'}"),
        ("No fresh price shown at any point of the outage", r["fresh_on_board_during_outage"] == 0, json.dumps(r["board_during_outage"])),
        ("Gap backfilled from the provider after recovery", r["candles_after_recovery"] > 0, f"{r['candles_after_recovery']} one-minute candles"),
        ("Subscribers: no out-of-order or duplicate quote", all(s["out_of_order"] == 0 and s["duplicates"] == 0 for s in r["subscribers"]), ", ".join(str(s["received"]) for s in r["subscribers"]) + " received"),
        ("Python heap stable over the soak (growth under 5 MB)", growth < 5_000_000, f"{growth / 1e6:.2f} MB growth after warm-up"),
        ("Metrics exposed; status gauge read 2 (disconnected) during the outage", r["status_gauge_max_during_outage"] == 2 and r["quotes_stored_counter"] > 0, ", ".join(r["metrics_exposed"])),
    ]


def write(r: dict[str, Any]) -> bool:
    checks = verdicts(r)
    ok = all(passed for _, passed, _ in checks)
    lines = [
        "# P13-T13 forex streaming soak and outage drill",
        "",
        "_Generated by `scripts/forex_soak.py` on the local stack (fresh migrated PostgreSQL database, the real feed,_",
        "_stream client, monitor, storage, backfill and fan-out; the simulated provider, DEC-19)._",
        "",
        f"Run: {r['started']} to {r['ended']}. Soak {r['soak_seconds']} s, provider outage {r['outage_seconds']} s,",
        f"recovery {r['recovery_seconds']} s; {r['pairs']} pairs; {SUBSCRIBERS} subscribers on every pair.",
        "",
        "| Check | Result | Detail |",
        "|---|---|---|",
        *[f"| {name} | {'pass' if passed else '**FAIL**'} | {detail} |" for name, passed, detail in checks],
        "",
        f"**Overall: {'pass' if ok else 'FAIL'}.**",
        "",
        "Limits: simulated data only; a licensed provider's sandbox or delayed feed is not available until",
        "DEC-19 allows one. There is no local Prometheus, Grafana or Alertmanager: the metrics are read from",
        "the app's registry and the alert rules (`infra/docker/otel/forex-alerts.yaml`) are checked against",
        "them by `tests/forex/test_forex_observability.py`; dashboards come with the monitoring stack (P15/P16).",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    OUT.with_suffix(".json").write_text(json.dumps(r, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--soak-seconds", type=int, default=600)
    # Longer than the stream's two-minute gap threshold, so the drill also exercises the backfill.
    parser.add_argument("--outage-seconds", type=int, default=150)
    parser.add_argument("--recovery-seconds", type=int, default=120)
    args = parser.parse_args()
    result = asyncio.run(run(args))
    ok = write(result)
    print(f"wrote {OUT}: {'pass' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
