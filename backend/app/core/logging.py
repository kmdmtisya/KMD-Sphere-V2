"""Structured JSON logging with correlation and trace IDs and mandatory redaction."""

import json
import logging
from datetime import UTC, datetime

from opentelemetry import trace

from app.core.correlation import get_correlation_id
from app.core.redaction import redact, scrub_text

_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "correlation_id"}


class CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "correlation_id", None):
            record.correlation_id = get_correlation_id()
        return True


class JsonFormatter(logging.Formatter):
    """Log schema (docs/observability.md): ts, level, logger, message, correlation_id,
    trace_id, span_id, optional extra fields, optional exception. Everything is redacted."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": scrub_text(record.getMessage()),
            "correlation_id": getattr(record, "correlation_id", None),
        }
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            payload["trace_id"] = format(ctx.trace_id, "032x")
            payload["span_id"] = format(ctx.span_id, "016x")
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = redact(value, key)
        if record.exc_info:
            payload["exception"] = scrub_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(CorrelationIdFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True
