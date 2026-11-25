"""OpenTelemetry tracing for the multi-agent pipeline.

Wraps each agent step in a named span with token/latency attributes.
Exports to console by default (swap ConsoleSpanExporter for OTLPSpanExporter
to ship to Jaeger/Grafana Tempo).
"""
from __future__ import annotations

import functools
import os
import time
from contextlib import contextmanager
from typing import Any, Generator

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

# One-time init — console export only when explicitly requested (OTEL_EXPORTER=console).
_provider = TracerProvider()
if os.getenv("OTEL_EXPORTER", "").lower() == "console":
    _provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(_provider)

tracer = trace.get_tracer("sentinel_ai", "2.0.0")


@contextmanager
def agent_span(
    agent_name: str,
    subtask_id: str = "",
    **attrs: Any,
) -> Generator[trace.Span, None, None]:
    """Context manager that creates a named span for an agent step."""
    with tracer.start_as_current_span(
        f"{agent_name}.run",
        attributes={
            "agent.name": agent_name,
            "subtask.id": subtask_id,
            **{k: str(v) for k, v in attrs.items()},
        },
    ) as span:
        yield span
