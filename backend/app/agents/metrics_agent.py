"""Code metrics agent."""

import re

from app.orchestration.review_state import ReviewState

_DECISION_KEYWORDS = [
    r"\bif\b",
    r"\belif\b",
    r"\belse\s+if\b",
    r"\bfor\b",
    r"\bwhile\b",
    r"\bcase\b",
    r"\bcatch\b",
    r"\bexcept\b",
    r"&&",
    r"\|\|",
    r"\?",
]

_COMMENT_PREFIXES = ("#", "//", "/*", "*", "--")


class MetricsAgent:
    """Computes maintainability / complexity metrics for a snippet."""

    @staticmethod
    def analyze(
        source_code: str,
        review_findings: dict,
        language: str = "python",
    ) -> dict:
        lines = source_code.splitlines()
        total_lines = len(lines)

        code_lines = 0
        comment_lines = 0
        blank_lines = 0

        for raw in lines:
            stripped = raw.strip()
            if not stripped:
                blank_lines += 1
            elif stripped.startswith(_COMMENT_PREFIXES):
                comment_lines += 1
            else:
                code_lines += 1

        decision_points = 0
        for pattern in _DECISION_KEYWORDS:
            decision_points += len(re.findall(pattern, source_code))

        # Approximate cyclomatic complexity = decision points + 1
        cyclomatic_complexity = decision_points + 1

        functions = review_findings.get("functions", []) or []
        classes = review_findings.get("classes", []) or []
        imports = review_findings.get("imports", []) or []

        function_count = len(functions)
        comment_ratio = (
            round(comment_lines / code_lines, 3) if code_lines else 0.0
        )
        avg_complexity_per_function = (
            round(cyclomatic_complexity / function_count, 2)
            if function_count
            else cyclomatic_complexity
        )

        maintainability = MetricsAgent._maintainability_index(
            code_lines, cyclomatic_complexity, comment_ratio
        )

        # Style / quality lint findings.
        from app.tools.linter_tool import LinterTool

        lint_findings = LinterTool.analyze(source_code, language)

        return {
            "total_lines": total_lines,
            "code_lines": code_lines,
            "comment_lines": comment_lines,
            "blank_lines": blank_lines,
            "comment_ratio": comment_ratio,
            "function_count": function_count,
            "class_count": len(classes),
            "import_count": len(imports),
            "cyclomatic_complexity": cyclomatic_complexity,
            "avg_complexity_per_function": avg_complexity_per_function,
            "maintainability_index": maintainability,
            "maintainability_rating": MetricsAgent._rating(maintainability),
            "lint_issue_count": len(lint_findings),
            "lint_findings": lint_findings[:50],
        }

    @staticmethod
    def _maintainability_index(
        code_lines: int,
        complexity: int,
        comment_ratio: float,
    ) -> float:
        """A normalised 0-100 maintainability score (higher is better)."""
        if code_lines == 0:
            return 100.0

        # Heuristic: penalise size and complexity, reward documentation.
        import math

        score = (
            100.0
            - (math.log(code_lines + 1) * 6)
            - (complexity * 1.5)
            + (comment_ratio * 10)
        )
        return round(max(0.0, min(100.0, score)), 1)

    @staticmethod
    def _rating(index: float) -> str:
        if index >= 80:
            return "A"
        if index >= 65:
            return "B"
        if index >= 50:
            return "C"
        if index >= 35:
            return "D"
        return "E"


def metrics_node(state: ReviewState) -> ReviewState:
    from app.orchestration.review_state import should_run

    if not should_run(state, "metrics_agent"):
        state.setdefault("metrics", {})
        return state

    state["metrics"] = MetricsAgent.analyze(
        source_code=state["source_code"],
        review_findings=state.get("review_findings", {}),
        language=state.get("language", "python"),
    )
    return state
