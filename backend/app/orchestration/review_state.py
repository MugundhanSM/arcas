from typing import Annotated, TypedDict


def _merge_dicts(a: dict, b: dict) -> dict:
    return {**(a or {}), **(b or {})}


class ReviewState(TypedDict, total=False):

    source_code: str

    language: str

    intent: str

    review_findings: dict

    security_findings: list

    risk_analysis: dict

    metrics: dict

    refactor_recommendations: str

    refactor_diff: str

    # The validated, complete refactored file.
    refactored_code: str

    documentation: str

    generated_tests: str

    output_guardrail: dict

    # Warnings raised by the isolated WorkspaceTool when validating the proposed refactored code.
    workspace_warnings: list

    # Per-agent ReAct reasoning trace. Merged across nodes.
    react_traces: Annotated[dict, _merge_dicts]


# Conditional routing map.
INTENT_AGENTS = {
    "full_review": {
        "review_agent",
        "metrics_agent",
        "security_agent",
        "risk_agent",
        "refactor_agent",
        "risk_finalize_agent",
        "documentation_agent",
        "test_generation_agent",
    },
    "auto": {
        "review_agent",
        "metrics_agent",
        "security_agent",
        "risk_agent",
        "refactor_agent",
        "risk_finalize_agent",
        "documentation_agent",
        "test_generation_agent",
    },
    "security_audit": {
        "review_agent",
        "metrics_agent",
        "security_agent",
        "risk_agent",
        "refactor_agent",
        "risk_finalize_agent",
    },
    "refactor": {
        "review_agent",
        "metrics_agent",
        "security_agent",
        "risk_agent",
        "refactor_agent",
        "risk_finalize_agent",
    },
    "documentation": {
        "review_agent",
        "documentation_agent",
    },
    "test_generation": {
        "review_agent",
        "security_agent",
        "test_generation_agent",
    },
    "metrics": {
        "review_agent",
        "metrics_agent",
    },
}


def should_run(state, agent_name: str) -> bool:
    """Return True when agent_name is required for the state's intent."""
    intent = (state.get("intent") or "full_review")
    allowed = INTENT_AGENTS.get(intent, INTENT_AGENTS["full_review"])
    return agent_name in allowed
