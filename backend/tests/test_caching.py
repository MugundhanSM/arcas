import asyncio
import time

import pytest

from app.agents.refactor_agent import RefactorAgent
from app.orchestration.checkpointer import thread_config
from app.orchestration.review_graph import review_graph
from app.tools import semgrep_tool
from app.tools.semgrep_tool import SemgrepTool

pytestmark = pytest.mark.unit


class _FakeCompleted:
    returncode = 0
    stdout = "{}"
    stderr = ""


def test_llm_agent_output_is_cached(monkeypatch, vulnerable_python):
    # First call populates the cache (LLM disabled -> deterministic fallback).
    first = RefactorAgent.analyze(
        source_code=vulnerable_python,
        language="python",
        review_findings={},
        security_findings=[],
        risk_analysis={},
        metrics={},
    )

    # Poison the fallback: a second call that recomputed would now blow up.
    def _boom(*_args, **_kwargs):
        raise AssertionError(
            "result was recomputed instead of served from cache"
        )

    monkeypatch.setattr(RefactorAgent, "_fallback", staticmethod(_boom))

    second = RefactorAgent.analyze(
        source_code=vulnerable_python,
        language="python",
        review_findings={},
        security_findings=[],
        risk_analysis={},
        metrics={},
    )

    assert second == first


def _configs_of(cmd):
    return [cmd[i + 1] for i, arg in enumerate(cmd) if arg == "--config"]


def test_semgrep_always_includes_the_offline_ruleset(monkeypatch):
    captured = {}

    def _fake_run(cmd, **_kwargs):
        captured["configs"] = _configs_of(cmd)
        return _FakeCompleted()

    monkeypatch.setattr(semgrep_tool.subprocess, "run", _fake_run)
    monkeypatch.setattr(semgrep_tool, "_registry_reachable", lambda: False)

    SemgrepTool.analyze("print(1)\n", "python")

    assert captured["configs"] == [str(semgrep_tool._LOCAL_RULES)]


def test_semgrep_adds_language_scoped_registry_when_reachable(monkeypatch):
    captured = {}

    def _fake_run(cmd, **_kwargs):
        captured["configs"] = _configs_of(cmd)
        return _FakeCompleted()

    monkeypatch.setattr(semgrep_tool.subprocess, "run", _fake_run)
    monkeypatch.setattr(semgrep_tool, "_registry_reachable", lambda: True)

    SemgrepTool.analyze("print(2)\n", "python")

    assert "p/python" in captured["configs"]
    assert str(semgrep_tool._LOCAL_RULES) in captured["configs"]


def test_semgrep_deep_scan_uses_audit_ruleset(monkeypatch):
    captured = {}

    def _fake_run(cmd, **_kwargs):
        captured["configs"] = _configs_of(cmd)
        return _FakeCompleted()

    monkeypatch.setattr(semgrep_tool.subprocess, "run", _fake_run)
    monkeypatch.setattr(semgrep_tool, "_registry_reachable", lambda: True)

    SemgrepTool.analyze("print(3)\n", "python", deep_scan=True)

    assert "p/security-audit" in captured["configs"]


def test_semgrep_result_is_cached(monkeypatch):
    calls = {"n": 0}

    def _fake_run(cmd, **_kwargs):
        calls["n"] += 1
        return _FakeCompleted()

    monkeypatch.setattr(semgrep_tool.subprocess, "run", _fake_run)
    monkeypatch.setattr(semgrep_tool, "_registry_reachable", lambda: False)

    SemgrepTool.analyze("print(cache_probe)\n", "python")
    SemgrepTool.analyze("print(cache_probe)\n", "python")

    # The subprocess must run only once; the second call is a cache hit.
    assert calls["n"] == 1


@pytest.mark.integration
def test_warm_review_completes_quickly(vulnerable_python):
    payload = {
        "source_code": vulnerable_python,
        "language": "python",
        "intent": "full_review",
    }

    t0 = time.perf_counter()
    cold = asyncio.run(review_graph.ainvoke(dict(payload), config=thread_config()))
    cold_s = time.perf_counter() - t0

    t1 = time.perf_counter()
    warm = asyncio.run(review_graph.ainvoke(dict(payload), config=thread_config()))
    warm_s = time.perf_counter() - t1

    print(f"[phase2] cold={cold_s * 1000:.0f}ms warm={warm_s * 1000:.0f}ms")

    # Warm repeat must hit the cache and finish fast, with identical output.
    assert warm_s < 2.0
    assert (
        warm["refactor_recommendations"]
        == cold["refactor_recommendations"]
    )
