"""OpenTelemetry tracing and metrics.

Traces and metrics are always collected in-process. They are exported over OTLP/HTTP only when
OTEL_EXPORTER_OTLP_ENDPOINT is set. Metrics are additionally exposed in Prometheus format on
the token-protected /metrics endpoint (see app/api/metrics.py).
"""

from collections.abc import Sequence

from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricReader, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CollectorRegistry, generate_latest

from app.core.config import Settings

# Health probes and the metrics endpoint itself are not traced or measured.
EXCLUDED_URLS = "/health/,/metrics"


class Telemetry:
    def __init__(self, settings: Settings, span_processors: Sequence[SpanProcessor] = ()) -> None:
        resource = Resource.create(
            {
                "service.name": settings.otel_service_name,
                "service.version": "0.1.0",
                "deployment.environment.name": settings.environment,
            }
        )
        self.registry = CollectorRegistry()
        self.tracer_provider = TracerProvider(resource=resource)
        for processor in span_processors:
            self.tracer_provider.add_span_processor(processor)

        readers: list[MetricReader] = [PrometheusMetricReader(registry=self.registry)]
        endpoint = settings.otel_exporter_otlp_endpoint.rstrip("/")
        if endpoint:
            self.tracer_provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces"))
            )
            readers.append(
                PeriodicExportingMetricReader(
                    OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics"),
                    export_interval_millis=settings.otel_metric_export_interval_ms,
                )
            )
        self.meter_provider = MeterProvider(resource=resource, metric_readers=readers)

    def instrument(self, app: FastAPI) -> None:
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
            excluded_urls=EXCLUDED_URLS,
        )

    def render_metrics(self) -> bytes:
        return generate_latest(self.registry)

    def shutdown(self) -> None:
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()
