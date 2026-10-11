# Background jobs (Celery on RabbitMQ)

Status: Implemented in P08-T04. Code: `backend/app/worker/`. Used by price and FX ingestion (P08-T05) and alert evaluation (P08-T07).

## 1. Running it

With the compose stack up (`make up`):

| Command | What |
|---|---|
| `make worker` | A worker on the `default` queue |
| `make beat` | The scheduler (`app/worker/schedule.py`) |
| `make dead-letters` | Open failed jobs (`python -m app.worker.cli failures`; `--all`, `ack <id>`) |

**RabbitMQ 4 caveat.** Celery's mingle, gossip and heartbeat features declare transient non-exclusive queues, which RabbitMQ 4 refuses; the worker then restarts in a loop. Always start workers with `--without-mingle --without-gossip --without-heartbeat` (the Makefile does) and keep `worker_enable_remote_control=False` (set in the app). The embedded test worker already runs without them.

Settings come from the environment (`RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `RABBITMQ_HOST`, `RABBITMQ_PORT`); the broker URL contains the password and is never logged (Celery's own log line shows it as `[REDACTED]`).

## 2. Reliability

- **Acknowledge late:** a task is acknowledged after it finishes, so a worker that dies mid-task does not lose it; it is redelivered. `prefetch_multiplier=1`, time limits (soft 120 s, hard 180 s) so a hung provider call cannot hold a worker.
- **JSON only**, no pickle.
- **Queues:** `default` is declared with a dead-letter exchange `dlx` routing to `dead_letter`. A message the broker rejects (an unknown task, a poison message) lands there. Changing a queue's arguments needs the queue deleted first (the broker refuses a redeclaration with different arguments).

## 3. Retry and dead letters (`jobs.py`)

Every job uses `JobTask`:

- Transient errors (`ProviderUnavailable`, `ConnectionError`, `TimeoutError`) are retried with exponential backoff and jitter (cap 5 minutes), up to 5 times. Other errors fail at once.
- A job that fails for good is a **dead letter**: a row in `job_failures` (job, error type, truncated message, attempts), a message in `dead_letter` with the task name, id, arguments and error type (so it can be replayed), and a count in the `worker_job_failures_total{job}` metric.
- Recording and publishing each log and carry on if they fail: a broken database or broker never hides the original failure.
- Visible: `make dead-letters`, the `dead_letter` queue in the RabbitMQ management UI, the metric.

**Logging.** Workers use the same redacting JSON logging as the API. Our own lines name the job, id and error type only. Celery's own lines include a task's arguments and an exception's text, and the redactor only removes credential-shaped values, so **jobs take identifiers and dates, never secrets or personal data, as arguments, and exceptions never carry them**. The provider adapters keep keys out of every error message.

## 4. Idempotent jobs (`idempotency.py`)

A job claims the key it is about to process (for example `price-ingest:2026-10-12`) with one atomic `INSERT ... ON CONFLICT DO UPDATE ... WHERE` on a unique (job, key) in `job_runs`:

| State of the key | Result |
|---|---|
| no row | inserted `running`: this worker does the work |
| `done` | skipped |
| `failed` | taken again (attempts + 1): a retry |
| `running`, older than the lock timeout (15 min) | taken over: the earlier worker died |
| `running`, recent | skipped: another worker is on it |

`run_once` marks the run `done` or `failed` (with a truncated error). Two workers claiming at the same moment cannot both win (tested with 8 concurrent claims). This guarantees the claim; the work itself must be an upsert, so a crash between the work and `done` re-runs it safely.

## 5. Schedule and heartbeat

`schedule.py` holds the beat schedule. Today it has one entry: `worker-heartbeat` every 60 s writes a timestamp to Redis (`worker:heartbeat`, 180 s TTL); if the key expires, the worker or beat is not running.

## 6. Tests

- `tests/worker/test_celery_app.py`: settings, queues with dead-letter arguments, schedule, registered jobs.
- `tests/worker/test_idempotency.py` (database): claim rules, takeover, concurrency, run-once.
- `tests/worker/test_jobs.py`: retries, dead-lettering, payload, log content, resilience to a broken database or broker.
- `tests/worker/test_failures_visible.py` (database): the failure table and CLI.
- `tests/worker/test_broker_integration.py`: a real worker against the compose RabbitMQ runs a job and dead-letters a failing one with its arguments; skipped when no broker is reachable (CI has none).
