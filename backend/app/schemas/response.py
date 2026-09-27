from typing import Any, Dict, List

from pydantic import BaseModel


class ReviewResponse(BaseModel):

    session_id: str

    language: str

    review_findings: Dict[str, Any]

    security_findings: List[Dict[str, Any]]

    risk_analysis: dict

    metrics: Dict[str, Any]

    refactor_recommendations: str

    refactor_diff: str = ""

    # The validated, complete refactored file for the Monaco diff + Apply action.
    refactored_code: str = ""

    documentation: str = ""

    generated_tests: str = ""

    output_guardrail: Dict[str, Any] = {}

    # Warnings from the isolated workspace validation.
    workspace_warnings: List[str] = []

    # Per-agent ReAct reasoning trace for the Reasoning tab.
    react_traces: Dict[str, Any] = {}

    warnings: List[str] = []

    # Echoed back so the History tab can restore the editor + intent.
    source_code: str = ""

    intent: str = "full_review"

    intent_confidence: float | None = None

    intent_signals: List[str] = []

    message: str
