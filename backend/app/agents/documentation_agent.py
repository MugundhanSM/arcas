"""Documentation generation agent."""

import json

from app.core.logging import get_logger
from app.core.react_agent import ReActAgent
from app.core.result_cache import ResultCache
from app.tools.llm_tool import LLMNotConfiguredError, LLMTool
from app.tools.retriever_tool import RetrieverTool

logger = get_logger("arcas.agents.docs")


_SYSTEM_PROMPT = (
    "You are ARCAS Documentation Agent. You generate accurate, concise "
    "developer documentation. You NEVER invent APIs or behaviour that don't "
    "appear in the source code. Every claim you make must be verifiable from "
    "the code."
)


class DocumentationAgent:

    @staticmethod
    def analyze(
        source_code: str,
        language: str,
        review_findings: dict,
        intent: str = "full_review",
    ) -> str:
        cached = ResultCache.get_text(
            "documentation", source_code, language, extra=intent
        )
        if cached is not None:
            return cached

        if LLMTool.is_available():
            try:
                result, _trace = DocumentationAgent._react(
                    source_code, language, review_findings
                )
                ResultCache.set_text(
                    "documentation", source_code, language, result, extra=intent
                )
                return result
            except LLMNotConfiguredError:
                pass
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Documentation ReAct loop failed (%s); falling back to a "
                    "single-shot prompt.",
                    exc,
                )

        prompt = f"""
You are a senior technical writer and software engineer.

Generate clear, accurate developer documentation for the {language} code
below. Use ONLY information that is verifiable from the code; do not invent
APIs or behaviour.

==================================================
SOURCE CODE ({language})
==================================================

{source_code}

==================================================
DETECTED STRUCTURE
==================================================

{json.dumps(review_findings, indent=2)}

==================================================
TASK
==================================================

Produce clean markdown with the following sections:

1. **Overview** - what the module does, in 2-3 sentences.
2. **Public API** - each function/class with purpose, parameters, returns.
3. **Usage Example** - a short, realistic snippet.
4. **Notes & Caveats** - important behaviour, side effects, assumptions.

Be concise and precise. Do not repeat the source code verbatim.
"""

        try:
            result = LLMTool.generate(prompt, system_prompt=_SYSTEM_PROMPT)
        except LLMNotConfiguredError:
            logger.warning(
                "LLM not configured - returning deterministic docs."
            )
            result = DocumentationAgent._fallback(language, review_findings)
        except Exception as exc:  # noqa: BLE001
            logger.error("Documentation generation failed: %s", exc)
            result = DocumentationAgent._fallback(language, review_findings)

        ResultCache.set_text(
            "documentation", source_code, language, result, extra=intent
        )
        return result

    @staticmethod
    def analyze_with_trace(
        source_code: str,
        language: str,
        review_findings: dict,
        intent: str = "full_review",
    ):
        """Return (documentation, reasoning_trace) for the Reasoning tab."""
        if LLMTool.is_available():
            try:
                return DocumentationAgent._react(
                    source_code, language, review_findings
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Documentation ReAct loop failed: %s", exc)
        return (
            DocumentationAgent.analyze(
                source_code, language, review_findings, intent
            ),
            [],
        )

    @staticmethod
    def _react(source_code: str, language: str, review_findings: dict):
        """Thought -> Action -> Observation loop grounded in real signatures."""
        structure_json = json.dumps(review_findings, indent=2)[:1500]

        def inspect_structure(_arg: str) -> str:
            return structure_json

        def read_signatures(_arg: str) -> str:
            """Exact parameter names, kinds, annotations and defaults."""
            if language.lower() not in ("python", "py"):
                return (
                    f"Signature extraction is implemented for Python only; "
                    f"'{language}' is not supported. Use inspect_structure."
                )
            try:
                from app.agents.signature_introspector import (
                    describe_signatures,
                    extract_signatures,
                )

                signatures = extract_signatures(source_code)
                if not signatures:
                    return "No public callables were found."
                return describe_signatures(signatures)[:2000]
            except Exception as exc:  # noqa: BLE001
                return f"Signature extraction unavailable: {exc}"

        def knowledge_base(query: str) -> str:
            return RetrieverTool.get_context(language=language, query=query)[
                :1200
            ]

        agent = ReActAgent(
            system_prompt=_SYSTEM_PROMPT,
            tools={
                "inspect_structure": inspect_structure,
                "read_signatures": read_signatures,
                "knowledge_base": knowledge_base,
            },
            max_iterations=4,
        )
        task = (
            f"Write developer documentation for this {language} code. Call "
            f"inspect_structure for the module layout and read_signatures for "
            f"the exact parameters of each callable BEFORE describing any API "
            f"- never infer a parameter you have not observed. Use "
            f"knowledge_base for documentation conventions. Produce markdown "
            f"with Overview, Public API, Usage Example and Notes & Caveats "
            f"sections.\n\nCODE:\n{source_code[:2000]}"
        )
        return agent.run(task)

    @staticmethod
    def _fallback(language: str, review_findings: dict) -> str:
        functions = review_findings.get("functions", []) or []
        classes = review_findings.get("classes", []) or []
        imports = review_findings.get("imports", []) or []

        lines = [
            "# Documentation",
            "",
            "> Generated deterministically from structural analysis "
            "(LLM unavailable).",
            "",
            f"**Language:** {language}",
            "",
            "## Overview",
            "",
            f"This module defines {len(classes)} class(es) and "
            f"{len(functions)} function(s), and uses "
            f"{len(imports)} import statement(s).",
            "",
            "## Public API",
            "",
        ]

        if classes:
            lines.append("### Classes")
            for name in classes:
                lines.append(f"- `{name}`")
            lines.append("")

        if functions:
            lines.append("### Functions")
            for name in functions:
                lines.append(f"- `{name}(...)`")
            lines.append("")

        if not classes and not functions:
            lines.append("No public classes or functions were detected.")

        return "\n".join(lines)


def documentation_node(state):
    from app.orchestration.review_state import should_run

    if not should_run(state, "documentation_agent"):
        state.setdefault("documentation", "")
        return state

    state["documentation"] = DocumentationAgent.analyze(
        source_code=state["source_code"],
        language=state.get("language", "python"),
        review_findings=state.get("review_findings", {}),
    )
    return state
