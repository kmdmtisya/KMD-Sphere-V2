"""A real worker against the real RabbitMQ (the compose stack): a job runs, a failing job lands in
the dead-letter queue with its arguments (P08-T04 verification: local worker run). Skipped when no
broker is reachable (CI has none)."""

import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
from celery.contrib.testing.worker import start_worker
from kombu import Connection

import app.worker.jobs as jobs
from app.core.config import get_settings
from app.worker.celery_app import celery_app
from app.worker.jobs import JobTask
from app.worker.queues import DEAD_LETTER_QUEUE, DEFAULT_QUEUE

pytestmark = pytest.mark.integration

RAN: list[str] = []
RECORDED: list[str] = []


@celery_app.task(base=JobTask, name="test.broker.remember")
def remember(value: str) -> None:
    RAN.append(value)


@celery_app.task(base=JobTask, name="test.broker.explode", max_retries=0)
def explode(value: str) -> None:
    raise ValueError("planned failure")


def broker_is_up() -> bool:
    cfg = get_settings()
    if not cfg.rabbitmq_user or not cfg.rabbitmq_password.get_secret_value():
        return False
    try:
        with Connection(cfg.broker_url, connect_timeout=3) as conn:
            conn.ensure_connection(max_retries=1)
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def worker() -> Iterator[None]:
    if not broker_is_up():
        pytest.skip("no RabbitMQ reachable")
    cfg = get_settings()
    # Start from fresh queues: a leftover message cannot fool the test, and the worker declares
    # them with the dead-letter arguments (a queue declared without them would be refused).
    with Connection(cfg.broker_url) as conn:
        for name in (DEFAULT_QUEUE, DEAD_LETTER_QUEUE):
            conn.default_channel.queue_delete(name)  # type: ignore[attr-defined]
    with start_worker(
        celery_app,
        perform_ping_check=False,
        pool="solo",
        queues=[DEFAULT_QUEUE],
        loglevel="WARNING",
    ):
        yield


def wait_for(predicate: Any, seconds: float = 15.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.2)
    return False


def test_a_job_sent_to_the_broker_is_run_by_a_worker(worker: None) -> None:
    remember.delay("from-the-broker")
    assert wait_for(lambda: "from-the-broker" in RAN)


def test_a_failing_job_is_dead_lettered_with_its_arguments(
    worker: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        jobs, "_record_failure", lambda task_id, job, *_: RECORDED.append(f"{job}:{task_id}")
    )
    result = explode.delay("replay-me")
    cfg = get_settings()
    message: dict[str, Any] = {}

    def fetch() -> bool:
        with Connection(cfg.broker_url) as conn:
            queue = conn.SimpleQueue(DEAD_LETTER_QUEUE)
            try:
                got = queue.get(block=True, timeout=1)
            except Exception:
                return False
            finally:
                queue.close()
            message.update(got.payload)
            got.ack()
            return True

    assert wait_for(fetch), "the failed job reached the dead_letter queue"
    assert message["task"] == "test.broker.explode"
    assert message["args"] == ["replay-me"]
    assert message["error_type"] == "ValueError"
    assert message["id"] == result.id
    assert wait_for(lambda: any(r.startswith("test.broker.explode") for r in RECORDED))


def test_the_default_queue_has_a_dead_letter_exchange(worker: None) -> None:
    import base64
    import json
    import urllib.request

    cfg = get_settings()
    from os import environ

    ui_port = environ.get("RABBITMQ_UI_PORT", "15673")
    request = urllib.request.Request(
        f"http://{cfg.rabbitmq_host}:{ui_port}/api/queues/%2F/{DEFAULT_QUEUE}"
    )
    token = base64.b64encode(
        f"{cfg.rabbitmq_user}:{cfg.rabbitmq_password.get_secret_value()}".encode()
    ).decode()
    request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 (local http)
            info = json.load(response)
    except Exception:
        pytest.skip("management API not reachable")
    assert info["arguments"]["x-dead-letter-exchange"] == "dlx"


_ = threading  # imported for start_worker's thread; kept explicit
