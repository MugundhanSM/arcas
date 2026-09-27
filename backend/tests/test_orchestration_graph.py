import asyncio

import pytest

from app.orchestration.review_graph import review_graph
from app.tools.semgrep_tool import SemgrepTool

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def stub_semgrep(monkeypatch):
    def _fake_analyze(code, language="python", deep_scan=False):
        findings = []
        if "shell=True" in code or "subprocess" in code:
            findings.append(
                {
                    "check_id": "stub.command-injection",
                    "message": "Possible command injection",
                    "severity": "ERROR",
                    "start_line": 1,
                    "end_line": 1,
                }
            )
        return findings

    monkeypatch.setattr(SemgrepTool, "analyze", staticmethod(_fake_analyze))


def test_full_review_graph_runs_end_to_end(vulnerable_python):
    result = asyncio.run(
        review_graph.ainvoke(  # noqa: E501
            {
                "source_code": vulnerable_python,
                "language": "python",
                "intent": "full_review",
            }
        )
    )

    # Structural review always runs.
    assert "review_findings" in result
    assert isinstance(result["review_findings"], dict)

    # Metrics + risk are deterministic and should be populated.
    assert "metrics" in result
    assert "risk_analysis" in result
    assert result["risk_analysis"].get("risk_level") in {
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    }
    # The stubbed command-injection finding should raise the risk above LOW.
    assert result["risk_analysis"]["finding_count"] >= 1
    assert result["risk_analysis"]["risk_score"] > 0


def test_intent_routing_skips_unneeded_agents():
    # A documentation-only intent should not populate test generation.
    result = asyncio.run(
        review_graph.ainvoke(  # noqa: E501
            {
                "source_code": "def f():\n    return 1\n",
                "language": "python",
                "intent": "documentation",
            }
        )
    )
    assert "review_findings" in result
    # generated_tests should be absent or empty when not requested.
    assert not result.get("generated_tests")


def test_graph_streaming_emits_progress(vulnerable_python):
    async def _collect():
        events = []
        async for event in review_graph.astream(
            {
                "source_code": vulnerable_python,
                "language": "python",
                "intent": "full_review",
            }
        ):
            events.append(event)
        return events

    events = asyncio.run(_collect())
    assert len(events) >= 1
