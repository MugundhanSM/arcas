import asyncio

import pytest

from app.services.review_service import ReviewService


async def _collect(gen):
    events = []
    async for event in gen:
        events.append(event)
    return events


def _run(intent, code, monkeypatch):
    monkeypatch.setattr(
        ReviewService,
        "_finalize",
        staticmethod(lambda *a, **k: {"session_id": "test-session"}),
    )

    return asyncio.run(
        _collect(
            ReviewService.process_review_streaming(
                db=None,
                language="python",
                source_code=code,
                intent=intent,
            )
        )
    )


@pytest.mark.unit
def test_full_review_streams_real_stage_events(monkeypatch, vulnerable_python):
    events = _run("full_review", vulnerable_python, monkeypatch)

    # First event is the structural review starting; last is completion.
    assert events[0]["stage"] == "review_agent"
    assert events[0]["status"] == "running"
    assert events[-1]["stage"] == "complete"
    assert events[-1]["data"]["session_id"] == "test-session"

    stages = [e for e in events if e["stage"] != "complete"]
    running = [e["stage"] for e in stages if e["status"] == "running"]
    done = [e["stage"] for e in stages if e["status"] == "done"]

    # Every announced "running" stage is later reported "done" (no orphans).
    assert set(running) == set(done)
    assert len(running) == len(done)

    # All seven graph stages plus the output-guardrail sub-stage are surfaced.
    assert set(running) == {
        "review_agent",
        "metrics_agent",
        "security_agent",
        "risk_agent",
        "refactor_agent",
        "documentation_agent",
        "test_generation_agent",
        "risk_finalize_agent",
        "output_guardrails",
    }


@pytest.mark.unit
def test_join_stage_waits_for_both_branches(monkeypatch, vulnerable_python):
    events = _run("full_review", vulnerable_python, monkeypatch)
    order = [
        (e["stage"], e["status"]) for e in events if e["stage"] != "complete"
    ]

    risk_running = order.index(("risk_agent", "running"))
    metrics_done = order.index(("metrics_agent", "done"))
    security_done = order.index(("security_agent", "done"))

    # risk_agent only starts once BOTH upstream branches have completed.
    assert risk_running > metrics_done
    assert risk_running > security_done


@pytest.mark.unit
def test_running_precedes_done_for_every_stage(monkeypatch, vulnerable_python):
    events = _run("full_review", vulnerable_python, monkeypatch)
    order = [(e["stage"], e["status"]) for e in events if e["stage"] != "complete"]

    for stage in {s for s, _ in order}:
        first_running = order.index((stage, "running"))
        first_done = order.index((stage, "done"))
        assert first_running < first_done, stage


@pytest.mark.unit
def test_narrow_intent_only_streams_active_stages(monkeypatch, clean_python):
    events = _run("metrics", clean_python, monkeypatch)

    stages = {e["stage"] for e in events if e["stage"] != "complete"}

    assert stages == {"review_agent", "metrics_agent"}
    # The generative / security stages are not surfaced for a metrics request.
    assert "security_agent" not in stages
    assert "refactor_agent" not in stages
    assert "output_guardrails" not in stages
