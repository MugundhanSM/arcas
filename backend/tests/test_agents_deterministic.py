import pytest

from app.agents.metrics_agent import MetricsAgent
from app.agents.review_agent import ReviewAgent
from app.agents.risk_agent import RiskAgent

pytestmark = pytest.mark.unit


def test_review_agent_extracts_structure(clean_python):
    findings = ReviewAgent.analyze(clean_python, "python")
    assert isinstance(findings, dict)
    # Tree-sitter (or regex fallback) should surface the structural keys.
    for key in ("functions", "classes", "imports"):
        assert key in findings
    assert "add" in findings["functions"]
    assert "Calculator" in findings["classes"]


def test_metrics_agent_counts_lines_and_complexity(vulnerable_python):
    findings = ReviewAgent.analyze(vulnerable_python, "python")
    metrics = MetricsAgent.analyze(vulnerable_python, findings, "python")
    assert metrics["cyclomatic_complexity"] >= 1
    assert metrics["function_count"] >= 2
    assert "maintainability_index" in metrics


def test_risk_agent_scores_high_severity_findings():
    findings = [
        {"severity": "ERROR"},
        {"severity": "HIGH"},
    ]
    risk = RiskAgent.analyze(findings, {"cyclomatic_complexity": 5})
    assert risk["risk_score"] > 0
    assert risk["risk_level"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert risk["finding_count"] == 2


def test_risk_agent_clean_code_is_low_risk():
    risk = RiskAgent.analyze([], {"cyclomatic_complexity": 1})
    assert risk["risk_score"] == 0
    assert risk["risk_level"] == "LOW"


def test_risk_score_is_capped_at_100():
    findings = [{"severity": "CRITICAL"} for _ in range(10)]
    risk = RiskAgent.analyze(findings, {"cyclomatic_complexity": 40})
    assert risk["risk_score"] == 100
    assert risk["risk_level"] == "CRITICAL"
