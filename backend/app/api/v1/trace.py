"""Trace inspection endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.core.telemetry import telemetry_status
from app.core.trace_store import TraceStore

router = APIRouter()


def _render_text(trace_dict: dict) -> str:
    """Render the arrow notation from a recorded trace."""
    parts = []
    for row in trace_dict["layers"]:
        seconds = row["self_ms"] / 1000.0
        parts.append(f"{row['layer_name']} ({seconds:.2f}s)")
    chain = " → ".join(parts)

    bottleneck = trace_dict.get("bottleneck")
    lines = [
        f"trace {trace_dict['trace_id']}",
        f"total {trace_dict['total_ms'] / 1000.0:.2f}s "
        f"across {trace_dict['span_count']} spans",
        "",
        chain,
    ]
    if bottleneck:
        lines += [
            "",
            f"bottleneck: {bottleneck['layer_name']} - "
            f"{bottleneck['self_ms'] / 1000.0:.2f}s "
            f"({bottleneck['share']:.0%} of total)",
        ]

    if bottleneck:
        slowest = next(
            (
                row
                for row in trace_dict["layers"]
                if row["layer_name"] == bottleneck["layer_name"]
            ),
            None,
        )
        if slowest and slowest["spans"]:
            lines.append("")
            lines.append(f"  {bottleneck['layer_name']} breakdown:")
            for span in slowest["spans"]:
                lines.append(
                    f"    {span['name']:<40s} "
                    f"{span['duration_ms'] / 1000.0:>7.3f}s"
                    + (f"  ERROR: {span['error']}" if span.get("error") else "")
                )
    return "\n".join(lines)


@router.get("/trace/{trace_id}", tags=["Observability"])
def get_trace(
    trace_id: str,
    format: str = Query("json", pattern="^(json|text)$"),
):
    """Return the nine-layer execution breakdown for one request."""
    trace = TraceStore.get(trace_id)
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "Unknown trace id. Traces are held in a bounded in-memory "
                "buffer and are lost on restart."
            ),
        )

    payload = trace.as_dict()
    if format == "text":
        from fastapi.responses import PlainTextResponse

        return PlainTextResponse(_render_text(payload))
    return payload


@router.get("/traces", tags=["Observability"])
def list_traces(limit: int = Query(20, ge=1, le=200)):
    """List recent traces, newest first."""
    return {
        "telemetry": telemetry_status(),
        "traces": TraceStore.recent(limit),
    }
