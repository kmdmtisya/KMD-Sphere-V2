"""Worker metrics (Prometheus client; exposed by whatever scrapes the worker process)."""

from prometheus_client import Counter

JOB_FAILURES = Counter(
    "worker_job_failures_total",
    "Jobs that failed after all retries (dead letters).",
    ["job"],
)
