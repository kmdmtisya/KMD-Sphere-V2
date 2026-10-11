"""Retry, dead-lettering and visibility of failed jobs (P08-T04.3). No broker needed: tasks run
eagerly and the producer is replaced."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

import app.worker.jobs as jobs
from app.modules.market_data.providers.errors import ProviderUnavailable
from app.worker.celery_app import celery_app
from app.worker.jobs import JobTask
from app.worker.metrics import JOB_FAILURES
from app.worker.tasks import HEARTBEAT_KEY, HEARTBEAT_TTL_SECONDS, ping, write_heartbeat

MARKER = "argument-marker-for-log-test"


class FakeProducer:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    def publish(self, body: dict[str, Any], **options: Any) -> None:
        self.published.append({"body": body, **options})


@pytest.fixture
def producer(monkeypatch: pytest.MonkeyPatch) -> FakeProducer:
    fake = FakeProducer()

    @contextmanager
    def acquire() -> Iterator[FakeProducer]:
        yield fake

    monkeypatch.setattr(celery_app, "producer_or_acquire", acquire)
    return fake


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, str, int]]:
    rows: list[tuple[str, str, str, int]] = []

    def record(
        task_id: str, job: str, error: BaseException, attempts: int, failed_at: datetime
    ) -> None:
        rows.append((task_id, job, type(error).__name__, attempts))

    monkeypatch.setattr(jobs, "_record_failure", record)
    return rows


def failures(job: str) -> float:
    return JOB_FAILURES.labels(job=job)._value.get()  # type: ignore[no-any-return]


def make_task(name: str, error: Exception, retries: int = 2) -> tuple[Any, list[int]]:
    calls: list[int] = []

    @celery_app.task(base=JobTask, name=name, max_retries=retries)
    def failing(secret: str) -> None:
        calls.append(1)
        raise error

    return failing, calls


class TestJobTask:
    def test_a_job_runs(self) -> None:
        assert ping.apply().get() == "pong"

    def test_transient_errors_are_retried_with_backoff_and_jitter(self) -> None:
        assert ProviderUnavailable in JobTask.autoretry_for
        assert ConnectionError in JobTask.autoretry_for
        assert TimeoutError in JobTask.autoretry_for
        assert JobTask.retry_backoff is True
        assert JobTask.retry_jitter is True
        assert JobTask.max_retries >= 3
        assert JobTask.retry_backoff_max <= 600

    def test_a_transient_error_is_retried_then_dead_lettered_once(
        self, producer: FakeProducer, recorded: list[tuple[str, str, str, int]]
    ) -> None:
        task, calls = make_task("test.transient", ProviderUnavailable("down"), retries=2)
        before = failures("test.transient")
        result = task.apply(args=(MARKER,))
        assert result.state == "FAILURE"
        assert len(calls) == 3, "the first try and two retries"
        assert len(recorded) == 1
        assert recorded[0][1:3] == ("test.transient", "ProviderUnavailable")
        assert len(producer.published) == 1
        assert failures("test.transient") == before + 1

    def test_an_error_that_is_not_transient_fails_at_once(
        self, producer: FakeProducer, recorded: list[tuple[str, str, str, int]]
    ) -> None:
        task, calls = make_task("test.permanent", ValueError("bad input"))
        task.apply(args=(MARKER,))
        assert len(calls) == 1
        assert len(recorded) == 1
        assert len(producer.published) == 1

    def test_the_dead_letter_message_can_be_replayed(
        self, producer: FakeProducer, recorded: list[tuple[str, str, str, int]]
    ) -> None:
        task, _ = make_task("test.replay", ValueError("x"))
        task.apply(args=("a",), kwargs={})
        sent = producer.published[0]
        assert sent["exchange"].name == "dlx"
        assert sent["routing_key"] == "dead_letter"
        assert sent["serializer"] == "json"
        body = sent["body"]
        assert body["task"] == "test.replay"
        assert body["args"] == ["a"]
        assert body["error_type"] == "ValueError"
        assert body["id"]
        assert datetime.fromisoformat(body["failed_at"]).tzinfo is UTC

    def test_our_log_lines_carry_no_arguments_and_no_error_text(
        self,
        producer: FakeProducer,
        recorded: list[tuple[str, str, str, int]],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.DEBUG)
        task, _ = make_task("test.logs", ValueError(f"leaks {MARKER}"))
        task.apply(args=(MARKER,))
        # Our own log lines name the job and the error type, never the arguments or the text.
        ours = [r.getMessage() for r in caplog.records if r.name.startswith("app.worker")]
        assert ours, "the failure is logged"
        assert all(MARKER not in line for line in ours)
        assert any("test.logs" in line and "ValueError" in line for line in ours)

    def test_a_broken_database_does_not_hide_the_failure_or_skip_the_dead_letter(
        self,
        producer: FakeProducer,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        def broken(*_: object) -> None:
            raise OSError("database is down")

        monkeypatch.setattr(jobs, "_record_failure", broken)
        task, _ = make_task("test.dbdown", ValueError("x"))
        result = task.apply(args=("a",))
        assert result.state == "FAILURE"
        assert len(producer.published) == 1
        assert "could not record" in caplog.text

    def test_a_broken_broker_does_not_hide_the_failure_or_skip_the_record(
        self,
        monkeypatch: pytest.MonkeyPatch,
        recorded: list[tuple[str, str, str, int]],
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        @contextmanager
        def broken() -> Iterator[FakeProducer]:
            raise OSError("broker is down")
            yield FakeProducer()  # pragma: no cover

        monkeypatch.setattr(celery_app, "producer_or_acquire", broken)
        task, _ = make_task("test.brokerdown", ValueError("x"))
        task.apply(args=("a",))
        assert len(recorded) == 1
        assert "could not dead-letter" in caplog.text


class TestHeartbeat:
    def test_it_writes_a_timestamp_that_expires(self) -> None:
        class Client:
            def __init__(self) -> None:
                self.calls: list[tuple[str, str, int]] = []

            def set(self, key: str, value: str, ex: int) -> None:
                self.calls.append((key, value, ex))

        client = Client()
        now = datetime(2026, 10, 12, 12, tzinfo=UTC)
        stamp = write_heartbeat(client, now)  # type: ignore[arg-type]
        assert stamp == now.isoformat()
        assert client.calls == [(HEARTBEAT_KEY, now.isoformat(), HEARTBEAT_TTL_SECONDS)]
