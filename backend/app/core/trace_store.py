"""In-process distributed-trace recorder."""

from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger("arcas.tracing")

# How many completed traces to retain for inspection.
MAX_TRACES = 200

# Canonical layer names, used to group spans in the rendered breakdown.
LAYER_NAMES = {
    1: "L1 Presentation",
    2: "L2 API Gateway",
    3: "L3 Input Guardrails",
    4: "L4 Orchestration",
    5: "L5 Agent Pool",
    6: "L6 Tool Layer",
    7: "L7 Knowledge & RAG",
    8: "L8 Output Guardrails",
    9: "L9 Persistence",
}

# Propagated implicitly so a layer deep in the call stack need not be passed a trace id.
_current_trace: ContextVar[Optional[str]] = ContextVar(
    "arcas_trace_id", default=None
)
_current_span: ContextVar[Optional[str]] = ContextVar(
    "arcas_span_id", default=None
)


@dataclass
class Span:
    span_id: str
    name: str
    layer: int
    start_ms: float
    end_ms: Optional[float] = None
    parent_id: Optional[str] = None
    attributes: Dict[str, object] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        if self.end_ms is None:
            return 0.0
        return round(self.end_ms - self.start_ms, 3)

    def as_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "name": self.name,
            "layer": self.layer,
            "layer_name": LAYER_NAMES.get(self.layer, f"L{self.layer}"),
            "duration_ms": self.duration_ms,
            "start_offset_ms": round(self.start_ms, 3),
            "attributes": self.attributes,
            "error": self.error,
        }


@dataclass
class Trace:
    trace_id: str
    started_at: float
    spans: List[Span] = field(default_factory=list)
    origin_ms: float = 0.0

    def _self_times(self) -> Dict[str, float]:
        child_total: Dict[str, float] = {}
        for span in self.spans:
            if span.parent_id:
                child_total[span.parent_id] = (
                    child_total.get(span.parent_id, 0.0) + span.duration_ms
                )
        return {
            span.span_id: max(
                0.0, span.duration_ms - child_total.get(span.span_id, 0.0)
            )
            for span in self.spans
        }

    def layer_breakdown(self) -> List[dict]:
        """Aggregate spans by layer - the table."""
        self_times = self._self_times()
        by_layer: Dict[int, List[Span]] = {}
        for span in self.spans:
            by_layer.setdefault(span.layer, []).append(span)

        rows = []
        for layer in sorted(by_layer):
            spans = by_layer[layer]
            intervals = sorted(
                (s.start_ms, s.end_ms if s.end_ms is not None else s.start_ms)
                for s in spans
            )
            merged: List[List[float]] = []
            for start, end in intervals:
                if merged and start <= merged[-1][1]:
                    merged[-1][1] = max(merged[-1][1], end)
                else:
                    merged.append([start, end])
            wall_ms = sum(end - start for start, end in merged)
            self_ms = sum(self_times.get(s.span_id, 0.0) for s in spans)

            rows.append(
                {
                    "layer": layer,
                    "layer_name": LAYER_NAMES.get(layer, f"L{layer}"),
                    "wall_ms": round(wall_ms, 2),
                    "self_ms": round(self_ms, 2),
                    "span_count": len(spans),
                    "spans": sorted(
                        (
                            {
                                "name": s.name,
                                "duration_ms": s.duration_ms,
                                "self_ms": round(
                                    self_times.get(s.span_id, 0.0), 2
                                ),
                                "error": s.error,
                            }
                            for s in spans
                        ),
                        key=lambda r: -r["duration_ms"],
                    )[:12],
                }
            )
        return rows

    def total_ms(self) -> float:
        if not self.spans:
            return 0.0
        return round(
            max((s.end_ms or s.start_ms) for s in self.spans), 2
        )

    def as_dict(self) -> dict:
        breakdown = self.layer_breakdown()
        total = self.total_ms()
        # Rank by exclusive self time - see _self_times().
        slowest = max(breakdown, key=lambda r: r["self_ms"]) if breakdown else None
        return {
            "trace_id": self.trace_id,
            "started_at": self.started_at,
            "total_ms": total,
            "span_count": len(self.spans),
            "layers": breakdown,
            "bottleneck": (
                {
                    "layer_name": slowest["layer_name"],
                    "self_ms": slowest["self_ms"],
                    "share": (
                        round(slowest["self_ms"] / total, 3) if total else 0.0
                    ),
                }
                if slowest
                else None
            ),
            "waterfall": [s.as_dict() for s in sorted(
                self.spans, key=lambda s: s.start_ms
            )],
        }


class TraceStore:
    """Bounded, thread-safe store of recent traces."""

    _traces: "OrderedDict[str, Trace]" = OrderedDict()
    _lock = threading.Lock()

    @classmethod
    def start_trace(cls, trace_id: Optional[str] = None) -> str:
        trace_id = trace_id or uuid.uuid4().hex
        with cls._lock:
            cls._traces[trace_id] = Trace(
                trace_id=trace_id,
                started_at=time.time(),
                origin_ms=time.perf_counter() * 1000.0,
            )
            while len(cls._traces) > MAX_TRACES:
                cls._traces.popitem(last=False)
        _current_trace.set(trace_id)
        return trace_id

    @classmethod
    def get(cls, trace_id: str) -> Optional[Trace]:
        with cls._lock:
            return cls._traces.get(trace_id)

    @classmethod
    def recent(cls, limit: int = 20) -> List[dict]:
        with cls._lock:
            traces = list(cls._traces.values())[-limit:]
        return [
            {
                "trace_id": t.trace_id,
                "started_at": t.started_at,
                "total_ms": t.total_ms(),
                "span_count": len(t.spans),
            }
            for t in reversed(traces)
        ]

    @classmethod
    def record(cls, span: Span, trace_id: str) -> None:
        with cls._lock:
            trace = cls._traces.get(trace_id)
            if trace is not None:
                trace.spans.append(span)

    @classmethod
    def clear(cls) -> None:
        with cls._lock:
            cls._traces.clear()

    @classmethod
    def current_trace_id(cls) -> Optional[str]:
        return _current_trace.get()


class SpanRecorder:
    """Context manager that times a block and files it under the active trace."""

    def __init__(self, name: str, layer: int, **attributes: object) -> None:
        self.name = name
        self.layer = layer
        self.attributes = attributes
        self.span: Optional[Span] = None
        self._trace_id: Optional[str] = None
        self._token = None

    def __enter__(self) -> "SpanRecorder":
        self._trace_id = _current_trace.get()
        if self._trace_id is None:
            return self

        trace = TraceStore.get(self._trace_id)
        if trace is None:
            self._trace_id = None
            return self

        now = time.perf_counter() * 1000.0
        self.span = Span(
            span_id=uuid.uuid4().hex[:12],
            name=self.name,
            layer=self.layer,
            start_ms=now - trace.origin_ms,
            parent_id=_current_span.get(),
            attributes=dict(self.attributes),
        )
        self._token = _current_span.set(self.span.span_id)
        return self

    def set_attribute(self, key: str, value: object) -> None:
        if self.span is not None:
            self.span.attributes[key] = value

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self.span is None or self._trace_id is None:
            if self._token is not None:
                _current_span.reset(self._token)
            return False

        trace = TraceStore.get(self._trace_id)
        if trace is not None:
            self.span.end_ms = time.perf_counter() * 1000.0 - trace.origin_ms
            if exc is not None:
                self.span.error = f"{exc_type.__name__}: {exc}"
            TraceStore.record(self.span, self._trace_id)

        if self._token is not None:
            _current_span.reset(self._token)
        return False  # never swallow the exception


def set_current_trace(trace_id: Optional[str]) -> None:
    """Re-attach a trace id, e.g. inside a worker thread."""
    _current_trace.set(trace_id)
