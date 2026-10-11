"""Operator commands (P08-T04.3): see and acknowledge failed jobs.

    python -m app.worker.cli failures          # unacknowledged dead letters, newest first
    python -m app.worker.cli failures --all    # include acknowledged ones
    python -m app.worker.cli ack <id>          # mark one as dealt with

The matching messages are visible in the RabbitMQ management UI under the `dead_letter` queue."""

import argparse
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.worker.db import SessionFactory, run_async
from app.worker.models import JobFailure


async def list_failures(sessions: SessionFactory, include_acknowledged: bool) -> list[JobFailure]:
    async with sessions() as session:
        stmt = select(JobFailure).order_by(JobFailure.failed_at.desc())
        if not include_acknowledged:
            stmt = stmt.where(JobFailure.acknowledged_at.is_(None))
        return list((await session.execute(stmt)).scalars())


async def acknowledge(sessions: SessionFactory, failure_id: uuid.UUID) -> bool:
    async with sessions() as session:
        result = await session.execute(
            update(JobFailure)
            .where(JobFailure.id == failure_id, JobFailure.acknowledged_at.is_(None))
            .values(acknowledged_at=datetime.now(UTC))
            .returning(JobFailure.id)
        )
        await session.commit()
        return result.first() is not None


def format_failure(f: JobFailure) -> str:
    state = "acknowledged" if f.acknowledged_at else "OPEN"
    return (
        f"{f.id}  {f.failed_at:%Y-%m-%d %H:%M:%S}Z  {state:<12} {f.job_name}  "
        f"attempts={f.attempts}  {f.error_type}: {f.error_message}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.worker.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("failures", help="list failed jobs")
    listing.add_argument("--all", action="store_true", help="include acknowledged failures")
    ack = sub.add_parser("ack", help="acknowledge a failed job")
    ack.add_argument("id", type=uuid.UUID)
    args = parser.parse_args(argv)

    if args.command == "failures":
        rows = run_async(lambda s: list_failures(s, args.all))
        for row in rows:
            print(format_failure(row))
        print(f"{len(rows)} failure(s)")
        return 0
    done = run_async(lambda s: acknowledge(s, args.id))
    print("acknowledged" if done else "no such open failure")
    return 0 if done else 1


if __name__ == "__main__":
    sys.exit(main())
