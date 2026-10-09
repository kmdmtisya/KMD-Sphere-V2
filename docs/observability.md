# Observability

Implemented in P01-T12; production dashboards, alerts and SLOs are P13-T09. Targets: `docs/quality-targets.md`.

## Log schema
Every log line is one JSON object written to stderr:

| Field | Meaning |
|---|---|
| `ts` | UTC ISO 8601 timestamp with milliseconds |
| `level` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `logger` | Python logger name |
| `message` | Message, **scrubbed** |
| `correlation_id` | Request correlation ID (`X-Correlation-ID`), or `null` outside a request |
| `trace_id`, `span_id` | OpenTelemetry IDs when inside a span (join logs to traces) |
| any `extra={...}` field | Structured context, **redacted** |
| `exception` | Formatted traceback, **scrubbed** |

## Redaction (mandatory)
`app/core/redaction.py` is applied to every record by the JSON formatter. It removes:
- credentials and tokens: bearer/basic headers, JWTs, passwords, secrets, API keys, cookies, OTPs, DSNs;
- credentials inside URLs (`scheme://user:password@host`, including `redis://:password@host`);
- sensitive query-string and `key=value` / `"key": "value"` pairs;
- financial values: amount, balance, price, quantity, net worth, fees, taxes, income, holdings, totals and similar, by key name in structured fields and in text.

Over-redaction is preferred to leakage. Add new sensitive field names to the sets in `redaction.py` and extend `tests/test_redaction.py` in the same change. Never put secrets or raw financial payloads in a log message; log identifiers and outcomes instead.

## Tracing
OpenTelemetry SDK with the FastAPI instrumentation. Resource attributes: `service.name` (`wealthsphere-api`), `service.version`, `deployment.environment.name`. `/health/*` and `/metrics` are not traced. Spans are exported over OTLP/HTTP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; otherwise they stay in-process.

## Metrics
OpenTelemetry metrics (`http.server.duration`, `http.server.response.size`, `http.server.active_requests`) are
- exported over OTLP when an endpoint is set (interval `OTEL_METRIC_EXPORT_INTERVAL_MS`, default 15000), and
- exposed in Prometheus format on `GET /metrics`.

`/metrics` is internal: it returns 404 unless `METRICS_TOKEN` is set, requires `Authorization: Bearer <token>`, and is not part of the public OpenAPI contract. Scrape it from inside the private network only.

## Local collector
```bash
docker compose --profile observability up -d otel-collector      # prints received telemetry
export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 OTEL_METRIC_EXPORT_INTERVAL_MS=2000
cd backend && uv run uvicorn app.main:app --port 8000
docker compose logs -f otel-collector                            # spans and metrics appear here
```

## Settings
`OTEL_SERVICE_NAME`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `OTEL_METRIC_EXPORT_INTERVAL_MS`, `METRICS_TOKEN`, `LOG_LEVEL`.
