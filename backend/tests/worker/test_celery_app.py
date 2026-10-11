"""The Celery app's reliability settings, queues and schedule (P08-T04.1)."""

from pydantic import SecretStr

from app.core.config import Settings
from app.worker.celery_app import create_celery_app
from app.worker.jobs import JobTask
from app.worker.queues import DEAD_LETTER_EXCHANGE, DEAD_LETTER_QUEUE, DEFAULT_QUEUE
from app.worker.schedule import HEARTBEAT_EVERY_SECONDS, build_schedule


def app_with() -> object:
    return create_celery_app(
        Settings(
            environment="test",
            rabbitmq_user="ws",
            rabbitmq_password=SecretStr("s3cret-pass"),
            rabbitmq_host="broker.test",
            rabbitmq_port=5999,
        )
    )


def test_broker_url_is_built_from_settings_and_escapes_the_password() -> None:
    cfg = Settings(
        environment="test",
        rabbitmq_user="w s",
        rabbitmq_password=SecretStr("p@ss/word"),
        rabbitmq_host="h",
        rabbitmq_port=1,
    )
    assert cfg.broker_url == "amqp://w+s:p%40ss%2Fword@h:1//"


def test_the_password_is_not_in_the_settings_repr() -> None:
    cfg = Settings(environment="test", rabbitmq_password=SecretStr("hunter2"))
    assert "hunter2" not in repr(cfg)
    assert "hunter2" not in str(cfg.model_dump())


def test_a_task_is_acknowledged_only_after_it_finishes() -> None:
    conf = app_with().conf  # type: ignore[attr-defined]
    assert conf.task_acks_late is True
    assert conf.task_reject_on_worker_lost is True
    assert conf.worker_prefetch_multiplier == 1


def test_messages_are_json_only() -> None:
    conf = app_with().conf  # type: ignore[attr-defined]
    assert conf.task_serializer == "json"
    assert list(conf.accept_content) == ["json"]


def test_the_default_queue_dead_letters_to_the_dead_letter_queue() -> None:
    conf = app_with().conf  # type: ignore[attr-defined]
    queues = {q.name: q for q in conf.task_queues}
    default = queues[DEFAULT_QUEUE]
    assert default.queue_arguments["x-dead-letter-exchange"] == DEAD_LETTER_EXCHANGE
    assert default.queue_arguments["x-dead-letter-routing-key"] == DEAD_LETTER_QUEUE
    dead = queues[DEAD_LETTER_QUEUE]
    assert dead.exchange.name == DEAD_LETTER_EXCHANGE
    assert dead.routing_key == DEAD_LETTER_QUEUE
    assert conf.task_default_queue == DEFAULT_QUEUE


def test_a_hung_job_is_stopped() -> None:
    conf = app_with().conf  # type: ignore[attr-defined]
    assert 0 < conf.task_soft_time_limit < conf.task_time_limit


def test_beat_runs_the_heartbeat() -> None:
    schedule = build_schedule()
    assert schedule["worker-heartbeat"]["task"] == "app.worker.tasks.heartbeat"
    assert schedule["worker-heartbeat"]["schedule"] == HEARTBEAT_EVERY_SECONDS
    conf = app_with().conf  # type: ignore[attr-defined]
    assert "worker-heartbeat" in conf.beat_schedule


def test_every_scheduled_task_is_registered() -> None:
    import app.worker.tasks  # noqa: F401  (registers the jobs)
    from app.worker.celery_app import celery_app

    for entry in build_schedule().values():
        assert entry["task"] in celery_app.tasks


def test_registered_jobs_use_the_job_base_class() -> None:
    import app.worker.tasks  # noqa: F401
    from app.worker.celery_app import celery_app

    for name in ("app.worker.tasks.ping", "app.worker.tasks.heartbeat"):
        assert isinstance(celery_app.tasks[name], JobTask)
