"""Code review agent."""

from __future__ import annotations

import json
from typing import Tuple

from app.core.logging import get_logger
from app.core.react_agent import ReActAgent
from app.tools.linter_tool import LinterTool
from app.tools.llm_tool import LLMTool
from app.tools.retriever_tool import RetrieverTool
from app.tools.treesitter_tool import TreeSitterTool

logger = get_logger("arcas.agents.review")


_SYSTEM_PROMPT = (
    "You are ARCAS Code Review Agent - the primary analysis agent. You "
    "identify bugs, code smells, and maintainability issues using AST analysis "
    "and linting tools as your evidence base. Think step by step. Ground every "
    "observation in the tool output; do not invent issues that the tools did "
    "not surface."
)


class ReviewAgent:
    """Structural + reasoning code review agent."""

    @staticmethod
    def analyze(code: str, language: str = "python") -> dict:
        """Backward-compatible entry point: returns the structured findings."""
        findings, _trace = ReviewAgent.analyze_with_trace(code, language)
        return findings

    @staticmethod
    def analyze_with_trace(
        code: str, language: str = "python"
    ) -> Tuple[dict, list]:
        """Return (review_findings, reasoning_trace)."""
        structure = TreeSitterTool.analyze(code, language)
        try:
            linter_findings = LinterTool.analyze(code, language)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Linter failed: %s", exc)
            linter_findings = []

        findings = {
            "imports": structure.get("imports", []),
            "classes": structure.get("classes", []),
            "functions": structure.get("functions", []),
            "linter_findings": linter_findings,
        }

        report, trace = ReviewAgent._reason(
            code, language, structure, linter_findings
        )
        findings["review_report"] = report
        return findings, trace

    @staticmethod
    def _reason(code, language, structure, linter_findings):
        if LLMTool.is_available():
            try:
                return ReviewAgent._react(
                    code, language, structure, linter_findings
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Review ReAct loop failed (%s); using deterministic "
                    "summary.",
                    exc,
                )
        return ReviewAgent._deterministic(structure, linter_findings)

    @staticmethod
    def _react(code, language, structure, linter_findings):
        structure_json = json.dumps(structure, indent=2)[:1500]
        linter_json = json.dumps(linter_findings, indent=2)[:1500]

        def parse_ast(_arg: str) -> str:
            return structure_json

        def run_linter(_arg: str) -> str:
            return linter_json or "No linter findings."

        def knowledge_base(query: str) -> str:
            return RetrieverTool.get_context(
                language=language, query=query
            )[:1200]

        agent = ReActAgent(
            system_prompt=_SYSTEM_PROMPT,
            tools={
                "parse_ast": parse_ast,
                "run_linter": run_linter,
                "knowledge_base": knowledge_base,
            },
            max_iterations=4,
        )
        task = (
            f"Review the following {language} code. Use parse_ast to "
            f"understand structure, run_linter for quality issues, and "
            f"knowledge_base for clean-code guidance, then produce a concise "
            f"markdown review report.\n\nCODE:\n{code[:2000]}"
        )
        report, trace = agent.run(task)
        return report, trace

    @staticmethod
    def _deterministic(structure, linter_findings):
        funcs = structure.get("functions", []) or []
        classes = structure.get("classes", []) or []
        lines = [
            "## Code Review",
            "",
            f"Detected {len(classes)} class(es) and {len(funcs)} function(s).",
            "",
        ]
        if linter_findings:
            lines.append(f"### Linter findings ({len(linter_findings)})")
            for item in linter_findings[:15]:
                lines.append(
                    f"- Line {item.get('line')}: {item.get('message')} "
                    f"(`{item.get('symbol')}`)"
                )
        else:
            lines.append("No linter findings reported.")
        report = "\n".join(lines)

        trace = [
            {
                "type": "thought",
                "content": (
                    "First I parse the AST to understand the code structure."
                ),
                "iteration": 0,
            },
            {
                "type": "action",
                "tool": "parse_ast",
                "input": "source code",
                "iteration": 0,
            },
            {
                "type": "observation",
                "tool": "parse_ast",
                "result": (
                    f"{len(classes)} class(es), {len(funcs)} function(s)."
                ),
                "iteration": 0,
            },
            {
                "type": "thought",
                "content": "Now run the linter for style/quality issues.",
                "iteration": 1,
            },
            {
                "type": "action",
                "tool": "run_linter",
                "input": "source code",
                "iteration": 1,
            },
            {
                "type": "observation",
                "tool": "run_linter",
                "result": f"{len(linter_findings)} linter finding(s).",
                "iteration": 1,
            },
            {
                "type": "final",
                "content": "Compiled the structural review report.",
                "iteration": 2,
            },
        ]
        return report, trace
