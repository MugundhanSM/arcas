"""LangGraph node functions."""

import asyncio
import re

from app.agents.documentation_agent import DocumentationAgent
from app.agents.metrics_agent import MetricsAgent
from app.agents.refactor_agent import RefactorAgent
from app.agents.review_agent import ReviewAgent
from app.agents.risk_agent import RiskAgent
from app.agents.security_agent import SecurityAgent
from app.agents.test_generation_agent import TestGenerationAgent
from app.core.concurrency import llm_semaphore
from app.core.output_guardrails import OutputGuardrails
from app.core.selfcheck import SelfCheckGPT
from app.orchestration import substep_narrator as narrate
from app.orchestration.review_state import should_run
from app.orchestration.substep_emitter import emit_substep
from app.tools.diff_tool import DiffTool
from app.tools.llm_tool import LLMTool
from app.tools.workspace_tool import WorkspaceTool

_SECTION_RE = re.compile(
    r"\n*#{1,6}\s*COMPLETE\s+REFACTORED\s+FILE.*$",
    re.IGNORECASE | re.DOTALL,
)


async def review_node(state):
    emit_substep("review_agent", "Initialising AST parser…")

    def _run():
        emit_substep("review_agent", "Parsing code structure with tree-sitter…")
        result = ReviewAgent.analyze_with_trace(
            state["source_code"],
            state.get("language", "python"),
        )
        emit_substep("review_agent", narrate.narrate_structure(result[0]))
        return result

    review_findings, trace = await asyncio.to_thread(_run)

    return {
        "review_findings": review_findings,
        "react_traces": {"review_agent": trace},
    }


async def security_node(state):
    if not should_run(state, "security_agent"):
        return {"security_findings": []}

    emit_substep("security_agent", "Loading OWASP Top-10 vulnerability patterns…")

    def _run():
        emit_substep("security_agent", "Running Semgrep static analysis scanner…")
        result = SecurityAgent.analyze_with_trace(
            state["source_code"],
            state.get("language", "python"),
            state.get("deep_scan", False),
        )
        emit_substep("security_agent", narrate.narrate_security(result[0]))
        return result

    security_findings, trace = await asyncio.to_thread(_run)

    return {
        "security_findings": security_findings,
        "react_traces": {"security_agent": trace},
    }


async def refactor_node(state):
    if not should_run(state, "refactor_agent"):
        return {
            "refactor_recommendations": "",
            "refactor_diff": "",
            "refactored_code": "",
            "workspace_warnings": [],
            "output_guardrail": {},
        }

    language = state.get("language", "python")
    emit_substep(
        "refactor_agent",
        narrate.narrate_refactor_plan(
            state.get("security_findings", []), state.get("review_findings", {})
        ),
    )

    def _run():
        emit_substep("refactor_agent", "Calling AI model for refactoring guidance…")
        result = RefactorAgent.analyze_with_trace(
            source_code=state["source_code"],
            language=language,
            review_findings=state["review_findings"],
            security_findings=state.get("security_findings", []),
            risk_analysis=state.get("risk_analysis", {}),
            metrics=state.get("metrics", {}),
            intent=state.get("intent", "full_review"),
        )
        emit_substep("refactor_agent", "Applying SOLID and DRY principle suggestions…")
        return result

    async with llm_semaphore:
        recommendations, trace = await asyncio.to_thread(_run)

    candidate = DiffTool.extract_refactored_file(recommendations)

    workspace_warnings: list[str] = []
    refactored_code = ""

    if candidate:
        emit_substep("refactor_agent", "Validating semantic equivalence of refactor…")
        validation = await asyncio.to_thread(
            WorkspaceTool.apply_and_validate,
            original_code=state["source_code"],
            proposed_code=candidate,
            language=language,
        )
        refactor_diff = validation.unified_diff
        refactored_code = candidate if validation.is_valid else ""
        workspace_warnings = validation.warnings()
        emit_substep("refactor_agent", narrate.narrate_diff(refactor_diff))
        emit_substep(
            "refactor_agent",
            narrate.narrate_validation(workspace_warnings, validation.is_valid),
        )
    else:
        refactor_diff = ""
        workspace_warnings = [
            "Could not extract a complete refactored file from the agent output."
        ]

    if not refactor_diff:
        refactor_diff = (
            "(diff unavailable - the refactored file was not properly extracted)"
        )

    display_recommendations = _SECTION_RE.sub("", recommendations).rstrip()

    # SelfCheckGPT.
    selfcheck_result = None
    if SelfCheckGPT.enabled() and LLMTool.is_available():
        emit_substep(
            "refactor_agent",
            "Resampling the model to check answer consistency…",
        )
        selfcheck_result = await asyncio.to_thread(
            SelfCheckGPT.check,
            RefactorAgent.build_selfcheck_prompt(
                source_code=state["source_code"],
                language=language,
                review_findings=state.get("review_findings", {}),
                security_findings=state.get("security_findings", []),
            ),
            recommendations,
        )
        if selfcheck_result.ran:
            emit_substep(
                "refactor_agent",
                f"Consistency across {selfcheck_result.samples_used} resamples: "
                f"{selfcheck_result.consistency:.0%} "
                f"({selfcheck_result.risk_level} hallucination risk)",
            )

    guardrail = OutputGuardrails.check(
        generated_text=recommendations,
        source_code=state["source_code"],
        review_findings=state.get("review_findings", {}),
        language=language,
        selfcheck_result=selfcheck_result,
    )

    return {
        "refactor_recommendations": display_recommendations,
        "refactor_diff": refactor_diff,
        "refactored_code": refactored_code,
        "workspace_warnings": workspace_warnings,
        "react_traces": {"refactor_agent": trace},
        "output_guardrail": guardrail.as_dict(),
    }


async def risk_node(state):
    if not should_run(state, "risk_agent"):
        return {"risk_analysis": {}}

    emit_substep("risk_agent", "Mapping technical debt surface…")

    risk_analysis = RiskAgent.analyze(
        state.get("security_findings", []),
        state.get("metrics", {}),
    )
    emit_substep("risk_agent", narrate.narrate_risk(risk_analysis))

    return {"risk_analysis": risk_analysis}


async def risk_finalize_node(state):
    if not should_run(state, "risk_finalize_agent"):
        return {}

    emit_substep("risk_finalize_agent", "Weighting AI findings against static analysis…")

    ai_issues = RiskAgent.extract_ai_security_issues(
        state.get("refactor_recommendations", "")
    )
    finalized = RiskAgent.finalize(
        state.get("risk_analysis", {}),
        state.get("refactor_recommendations", ""),
    )
    emit_substep("risk_finalize_agent", narrate.narrate_risk_finalize(finalized, ai_issues))
    return {"risk_analysis": finalized}


async def metrics_node(state):
    if not should_run(state, "metrics_agent"):
        return {"metrics": {}}

    emit_substep("metrics_agent", "Counting lines of code and blank lines…")

    def _run():
        emit_substep("metrics_agent", "Measuring cyclomatic complexity per function…")
        result = MetricsAgent.analyze(
            state["source_code"],
            state.get("review_findings", {}),
            state.get("language", "python"),
        )
        emit_substep("metrics_agent", narrate.narrate_metrics(result))
        return result

    metrics = await asyncio.to_thread(_run)

    return {"metrics": metrics}


async def documentation_node(state):
    if not should_run(state, "documentation_agent"):
        return {"documentation": ""}

    emit_substep("documentation_agent", "Inferring module purpose and context…")

    def _run():
        emit_substep("documentation_agent", "Calling AI model for docstring generation…")
        result = DocumentationAgent.analyze(
            source_code=state["source_code"],
            language=state.get("language", "python"),
            review_findings=state.get("review_findings", {}),
            intent=state.get("intent", "full_review"),
        )
        emit_substep("documentation_agent", narrate.narrate_documentation(result))
        return result

    async with llm_semaphore:
        documentation = await asyncio.to_thread(_run)

    return {"documentation": documentation}


async def test_generation_node(state):
    if not should_run(state, "test_generation_agent"):
        return {"generated_tests": ""}

    language = state.get("language", "python")
    emit_substep("test_generation_agent", "Analysing function signatures and return types…")

    if language == "python":
        try:
            from app.agents.signature_introspector import (
                build_call_arguments,
                extract_signatures,
            )
            target = state.get("refactored_code") or state["source_code"]
            sigs = extract_signatures(target)
            if sigs:
                names = ", ".join(s.qualified_name for s in sigs[:6])
                emit_substep(
                    "test_generation_agent",
                    f"Introspected {len(sigs)} callable(s): {names}"
                    + ("…" if len(sigs) > 6 else ""),
                )
                for s in sigs[:5]:
                    args, _ = build_call_arguments(s)
                    emit_substep(
                        "test_generation_agent",
                        f"Synthesising dummy input for {s.name}({args})",
                    )
        except Exception:  # noqa: BLE001 - narration must never break the run
            pass

    def _run():
        emit_substep("test_generation_agent", "Calling AI model to scaffold test suite…")
        result = TestGenerationAgent.analyze(
            source_code=state["source_code"],
            language=language,
            review_findings=state.get("review_findings", {}),
            security_findings=state.get("security_findings", []),
            refactored_code=state.get("refactored_code", ""),
            intent=state.get("intent", "full_review"),
        )
        emit_substep("test_generation_agent", narrate.narrate_test_plan(result))
        return result

    async with llm_semaphore:
        generated_tests = await asyncio.to_thread(_run)

    # Attempt to execute the tests (Python only) and append results
    if language == "python" and generated_tests:
        emit_substep(
            "test_generation_agent",
            "Running tests in a network-free sandbox (dummy inputs + generated cases)…",
        )

        def _execute():
            return TestGenerationAgent.execute_tests(
                source_code=state["source_code"],
                generated_tests_markdown=generated_tests,
                language=language,
                refactored_code=state.get("refactored_code", ""),
            )

        execution_result = await asyncio.to_thread(_execute)
        emit_substep("test_generation_agent", narrate.narrate_test_execution(execution_result))

        if execution_result.get("ran"):
            generated_tests = TestGenerationAgent.append_execution_result(
                generated_tests, execution_result
            )

    return {"generated_tests": generated_tests}
