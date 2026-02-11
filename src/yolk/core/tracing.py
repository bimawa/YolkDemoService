from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from yolk.config import settings


def setup_tracing() -> TracerProvider:
    resource = Resource.create({"service.name": "yolk-api", "service.version": "0.1.0"})
    provider = TracerProvider(resource=resource)

    if settings.otlp_enabled:
        otlp_exporter = OTLPSpanExporter(endpoint=settings.otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    return provider


def instrument_app(app: object) -> None:
    FastAPIInstrumentor.instrument_app(app)  # type: ignore[arg-type]
    HTTPXClientInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument(enable_commenter=True)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)
