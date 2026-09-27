"""Heuristic intent classifier."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from app.core.logging import get_logger

logger = get_logger("arcas.orchestration.intent")


@dataclass
class IntentClassification:
    """Result of classifying a request into an orchestration intent."""

    intent: str
    confidence: float  # 0.0 - 1.0
    signals: List[str] = field(default_factory=list)
    scores: Dict[str, float] = field(default_factory=dict)


# Keyword -> weight maps per intent.
_INTENT_KEYWORDS: Dict[str, Dict[str, float]] = {
    "security_audit": {
        "security": 3.0,
        "vulnerability": 3.0,
        "vulnerabilities": 3.0,
        "exploit": 2.5,
        "injection": 2.5,
        "owasp": 3.0,
        "cve": 2.5,
        "secure": 2.0,
        "insecure": 2.5,
        "xss": 2.5,
        "sql injection": 4.0,
        "security audit": 5.0,
        "find vulnerabilities": 4.5,
        "pen test": 3.0,
        "penetration": 2.5,
        "sanitize": 2.0,
        "attack": 2.0,
    },
    "refactor": {
        "refactor": 4.0,
        "refactoring": 4.0,
        "clean up": 3.0,
        "cleanup": 3.0,
        "improve": 2.0,
        "rewrite": 2.5,
        "simplify": 2.5,
        "optimize": 2.0,
        "optimise": 2.0,
        "restructure": 3.0,
        "readability": 2.0,
        "code smell": 3.0,
        "technical debt": 3.0,
        "modernize": 2.5,
        "modernise": 2.5,
    },
    "documentation": {
        "document": 3.5,
        "documentation": 4.0,
        "docstring": 4.0,
        "docstrings": 4.0,
        "comment": 2.5,
        "comments": 2.5,
        "explain": 2.5,
        "readme": 3.0,
        "api docs": 3.5,
        "write docs": 4.0,
        "annotate": 2.0,
    },
    "test_generation": {
        "test": 3.0,
        "tests": 3.0,
        "unit test": 4.5,
        "unit tests": 4.5,
        "pytest": 3.5,
        "junit": 3.5,
        "jest": 3.5,
        "coverage": 3.0,
        "test case": 4.0,
        "test cases": 4.0,
        "generate tests": 5.0,
        "write tests": 5.0,
        "mock": 2.0,
        "assertion": 2.5,
    },
    "metrics": {
        "metric": 3.0,
        "metrics": 3.5,
        "complexity": 3.0,
        "cyclomatic": 4.0,
        "maintainability": 3.5,
        "quality score": 3.5,
        "lines of code": 2.5,
        "measure": 2.0,
        "halstead": 4.0,
    },
    "full_review": {
        "full review": 5.0,
        "review everything": 4.5,
        "complete review": 4.5,
        "comprehensive": 3.0,
        "thorough": 2.5,
        "review": 1.5,
        "analyze": 1.5,
        "analyse": 1.5,
        "everything": 1.5,
    },
}

_CODE_SIGNALS: Dict[str, List[Tuple[re.Pattern, float, str]]] = {
    "security_audit": [
        (re.compile(r"\b(subprocess|os\.system|eval|exec)\b"), 1.5,
         "dangerous call site present"),
        (re.compile(r"(password|secret|api_?key|token)\s*=", re.I), 1.5,
         "hard-coded credential pattern"),
        (re.compile(r"shell\s*=\s*True"), 1.5, "shell=True usage"),
        (re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE)\b.*[\"'].*%|\bformat\("),
         1.0, "string-built SQL"),
    ],
    "documentation": [
        (re.compile(r"^\s*(def|class)\s", re.M), 0.4,
         "definitions lacking docstrings"),
    ],
    "test_generation": [
        (re.compile(r"^\s*def\s+\w+\(", re.M), 0.3, "testable functions"),
    ],
}

_PHRASE_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_+#.-]*")


class IntentClassifier:
    """Infer an orchestration intent from request text and source code."""

    DEFAULT_INTENT = "full_review"

    @staticmethod
    def classify(
        source_code: str = "",
        language: str = "python",
        request_text: str = "",
    ) -> IntentClassification:
        """Return the most likely intent with a confidence and rationale."""
        text = (request_text or "").lower()
        scores: Dict[str, float] = {k: 0.0 for k in _INTENT_KEYWORDS}
        signals: List[str] = []

        # Natural-language keyword / phrase scoring.
        if text:
            for intent, keywords in _INTENT_KEYWORDS.items():
                for phrase, weight in keywords.items():
                    if " " in phrase:
                        if phrase in text:
                            scores[intent] += weight
                            signals.append(
                                f"matched phrase '{phrase}' (+{weight})"
                            )
                    else:
                        # Word-boundary match for single tokens.
                        if re.search(rf"\b{re.escape(phrase)}\b", text):
                            scores[intent] += weight

        # Structural code signals (weak prior).
        if source_code:
            for intent, rules in _CODE_SIGNALS.items():
                for pattern, weight, label in rules:
                    if pattern.search(source_code):
                        scores[intent] += weight
                        signals.append(f"code signal: {label} (+{weight})")

        # Resolve winner.
        best_intent = IntentClassifier.DEFAULT_INTENT
        best_score = 0.0
        for intent, score in scores.items():
            if score > best_score:
                best_intent, best_score = intent, score

        total = sum(scores.values())
        if best_score <= 0.0 or total <= 0.0:
            result = IntentClassification(
                intent=IntentClassifier.DEFAULT_INTENT,
                confidence=0.25,
                signals=["no strong signal - defaulting to full_review"],
                scores=scores,
            )
            logger.info(
                "Intent classified: %s (conf=%.2f, default)",
                result.intent, result.confidence,
            )
            return result

        # A narrow intent skips agents, so only commit to one when the evidence is meaningful.
        _MIN_COMMIT_SCORE = 2.0
        if best_score < _MIN_COMMIT_SCORE:
            result = IntentClassification(
                intent=IntentClassifier.DEFAULT_INTENT,
                confidence=0.3,
                signals=(
                    signals[:6]
                    + ["weak signal - defaulting to full_review"]
                ),
                scores={k: round(v, 2) for k, v in scores.items()},
            )
            logger.info(
                "Intent classified: %s (conf=%.2f, weak->default)",
                result.intent, result.confidence,
            )
            return result

        # Confidence = winning share of total evidence, lightly smoothed.
        confidence = round(min(0.99, 0.4 + 0.6 * (best_score / total)), 2)

        result = IntentClassification(
            intent=best_intent,
            confidence=confidence,
            signals=signals[:8],
            scores={k: round(v, 2) for k, v in scores.items()},
        )
        logger.info(
            "Intent classified: %s (conf=%.2f) from %d signal(s)",
            result.intent, result.confidence, len(signals),
        )
        return result
