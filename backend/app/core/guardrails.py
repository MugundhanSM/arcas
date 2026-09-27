"""Input guardrails layer."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.injection_detector import InjectionDetector, InjectionVerdict
from app.core.logging import get_logger
from app.core.pii_detector import PIIDetector

logger = get_logger("arcas.guardrails")


SUPPORTED_LANGUAGES = {
    "python",
    "java",
    "javascript",
    "typescript",
    "go",
    "ruby",
    "php",
    "c",
    "cpp",
    "csharp",
    "rust",
    "kotlin",
    "scala",
    "bash",
}

_ALIASES = {
    "py": "python",
    "python3": "python",
    "js": "javascript",
    "jsx": "javascript",
    "node": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "c++": "cpp",
    "cxx": "cpp",
    "cc": "cpp",
    "c#": "csharp",
    "cs": "csharp",
    "golang": "go",
    "rs": "rust",
    "kt": "kotlin",
    "rb": "ruby",
    "sh": "bash",
    "shell": "bash",
    "zsh": "bash",
}


# Weighted signatures for language identification.
_LANGUAGE_SIGNATURES: Tuple[Tuple[str, re.Pattern, float], ...] = (
    ("python", re.compile(r"^\s*def\s+\w+\s*\(.*\)\s*(?:->.*)?:", re.M), 3.0),
    ("python", re.compile(r"^\s*from\s+[\w.]+\s+import\s", re.M), 2.5),
    ("python", re.compile(r"^\s*class\s+\w+(?:\([\w, ]*\))?\s*:", re.M), 2.5),
    ("python", re.compile(r"\bself\b|\b__init__\b|\belif\b|\bNone\b"), 1.5),
    ("java", re.compile(r"\b(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?\w+\s+\w+\s*\("), 3.0),
    ("java", re.compile(r"\bSystem\.out\.print|\bpublic\s+class\b|\bpackage\s+[\w.]+;"), 3.0),
    ("javascript", re.compile(r"\b(?:const|let)\s+\w+\s*=|=>|console\.log"), 2.0),
    ("javascript", re.compile(r"\bfunction\s+\w+\s*\(|\brequire\s*\(|\bmodule\.exports\b"), 2.0),
    ("typescript", re.compile(r":\s*(?:string|number|boolean|void|any)\b|\binterface\s+\w+\s*\{"), 3.0),
    ("go", re.compile(r"^\s*package\s+\w+|\bfunc\s+\w*\s*\(|:=|\bgo\s+func\b", re.M), 3.0),
    ("rust", re.compile(r"\bfn\s+\w+\s*\(|\blet\s+mut\b|\buse\s+[\w:]+;|\bimpl\b"), 3.0),
    ("ruby", re.compile(r"^\s*def\s+\w+.*$\n(?:.*\n)*?^\s*end\b", re.M), 2.5),
    ("ruby", re.compile(r"\bputs\b|\brequire\s+['\"]|\bdo\s*\|"), 2.0),
    ("php", re.compile(r"<\?php|\$\w+\s*=|\becho\s+\$"), 3.0),
    ("csharp", re.compile(r"\busing\s+System|\bnamespace\s+[\w.]+|\bConsole\.Write"), 3.0),
    ("cpp", re.compile(r"#include\s*<\w+>|\bstd::|\bnullptr\b|::\w+\s*\("), 2.5),
    ("c", re.compile(r"#include\s*<\w+\.h>|\bprintf\s*\(|\bmalloc\s*\("), 2.0),
    ("bash", re.compile(r"^#!\s*/bin/(?:ba)?sh|\becho\s+\$|\bfi\b|\besac\b", re.M), 2.5),
)


@dataclass
class GuardrailResult:
    """Outcome of the Layer 3 pipeline, including the full evidence trail."""

    allowed: bool
    normalized_language: str = "python"
    sanitized_code: str = ""
    violations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    # Entity types redacted, e.g. ["EMAIL_ADDRESS", "AWS_ACCESS_KEY"].
    pii_redactions: List[str] = field(default_factory=list)
    # Detector provenance, recorded so an audit can reproduce the decision.
    pii_engine: str = "pattern"
    injection_score: float = 0.0
    injection_verdict: str = "clean"
    injection_layers: List[str] = field(default_factory=list)
    language_confidence: float = 1.0
    syntax_valid: Optional[bool] = None

    def as_audit_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "language": self.normalized_language,
            "language_confidence": round(self.language_confidence, 2),
            "pii_engine": self.pii_engine,
            "pii_entities": sorted(set(self.pii_redactions)),
            "injection_score": round(self.injection_score, 3),
            "injection_verdict": self.injection_verdict,
            "injection_layers": self.injection_layers,
            "syntax_valid": self.syntax_valid,
            "violations": self.violations,
            "warnings": self.warnings,
        }


class InputGuardrails:
    """Validates, sanitises and normalises an incoming review request."""

    @staticmethod
    def check(code: str, language: str) -> GuardrailResult:
        from app.core.telemetry import start_span

        with start_span("guardrails.input", layer=3, bytes=len(code or "")):
            return InputGuardrails._check(code, language)

    @staticmethod
    def _check(code: str, language: str) -> GuardrailResult:
        result = GuardrailResult(allowed=True)

        # Payload-level rejection (cheapest checks first)
        if not code or not code.strip():
            result.allowed = False
            result.violations.append("Source code must not be empty.")
            return result

        size = len(code.encode("utf-8"))
        if size > settings.MAX_CODE_SIZE_BYTES:
            result.allowed = False
            result.violations.append(
                f"Source code exceeds the maximum allowed size "
                f"({settings.MAX_CODE_SIZE_BYTES} bytes)."
            )
            return result

        # Check 4. Language identification
        normalized, confidence, warning = InputGuardrails._resolve_language(
            code, language
        )
        result.normalized_language = normalized
        result.language_confidence = confidence
        if warning:
            result.warnings.append(warning)

        sanitized = code

        # Check 1. PII detection and redaction
        redaction = PIIDetector.redact(sanitized)
        result.pii_engine = redaction.engine
        if redaction.findings:
            sanitized = redaction.text
            result.pii_redactions = redaction.entity_types
            summary = PIIDetector.summary(redaction.findings)
            detail = ", ".join(
                f"{entity}×{count}" for entity, count in sorted(summary.items())
            )
            result.warnings.append(
                f"Redacted {len(redaction.findings)} PII/secret value(s) "
                f"before analysis ({detail})."
            )
            logger.warning(
                "PII redacted via %s: %s", redaction.engine, detail
            )

            critical = PIIDetector.critical_findings(redaction.findings)
            if critical:
                result.warnings.append(
                    f"CRITICAL: {len(critical)} live credential(s) detected in "
                    "the submission ("
                    + ", ".join(sorted({f.entity_type for f in critical}))
                    + "). They were redacted before analysis - rotate them."
                )

        # Check 2. Prompt-injection screening
        verdict: InjectionVerdict = InjectionDetector.scan(sanitized)
        result.injection_score = verdict.score
        result.injection_verdict = verdict.verdict
        result.injection_layers = verdict.layers_run

        if verdict.is_injection:
            # A high-confidence injection is refused outright.
            result.allowed = False
            result.violations.append(
                "Request blocked: the submitted content contains a "
                f"prompt-injection attempt (risk score {verdict.score:.2f}). "
                + "; ".join(s.detail for s in verdict.signals if s.score > 0)
            )
            return result

        if verdict.is_suspicious:
            sanitized, count = InjectionDetector.neutralize(
                sanitized, verdict.flagged_lines
            )
            result.warnings.append(
                f"Potential prompt-injection content detected on {count} "
                f"line(s) (risk score {verdict.score:.2f}) and neutralised "
                "before analysis."
            )

        # Check 3. Syntax validation
        syntax_valid, syntax_warning = InputGuardrails._validate_syntax(
            code, normalized
        )
        result.syntax_valid = syntax_valid
        if syntax_warning:
            result.warnings.append(syntax_warning)

        result.sanitized_code = sanitized
        return result

    # Check 4 - language identification

    @staticmethod
    def _resolve_language(code: str, language: str) -> Tuple[str, float, str]:
        claimed = (language or "").strip().lower()
        claimed = _ALIASES.get(claimed, claimed)

        scores = InputGuardrails._score_languages(code)
        detected, detected_score = ("", 0.0)
        if scores:
            detected, detected_score = max(scores.items(), key=lambda kv: kv[1])

        total = sum(scores.values()) or 1.0
        confidence = round(detected_score / total, 3) if detected_score else 0.0

        if claimed in SUPPORTED_LANGUAGES:
            claimed_score = scores.get(claimed, 0.0)
            # Override only on strong, unambiguous contradiction.
            if (
                detected
                and detected != claimed
                and detected_score >= 5.0
                and claimed_score == 0.0
            ):
                return (
                    detected,
                    confidence,
                    f"Declared language '{claimed}' contradicts the source, "
                    f"which parses as '{detected}'; using '{detected}'.",
                )
            return claimed, 1.0 if claimed_score else 0.5, ""

        if detected:
            return (
                detected,
                confidence,
                f"Language '{language}' is not recognised; detected "
                f"'{detected}' from the source instead.",
            )

        return (
            "python",
            0.0,
            f"Language '{language}' is not supported and could not be "
            "identified from the source; falling back to generic analysis.",
        )

    @staticmethod
    def _score_languages(code: str) -> Dict[str, float]:
        scores: Dict[str, float] = {}
        for lang, pattern, weight in _LANGUAGE_SIGNATURES:
            if pattern.search(code):
                scores[lang] = scores.get(lang, 0.0) + weight
        return scores

    # Check 3 - syntax validation

    @staticmethod
    def _validate_syntax(code: str, language: str) -> Tuple[Optional[bool], str]:
        if language == "python":
            try:
                ast.parse(code)
                return True, ""
            except SyntaxError as exc:
                return False, (
                    f"Python syntax error at line {exc.lineno}: {exc.msg}. "
                    "Analysis will continue on a best-effort basis."
                )

        try:
            from app.tools.treesitter_tool import TreeSitterTool

            analysis = TreeSitterTool.analyze(code, language)
            if analysis.get("parser") != "tree-sitter":
                return None, ""
            errors = analysis.get("syntax_errors", 0)
            if errors:
                return False, (
                    f"{errors} syntax error node(s) detected while parsing "
                    f"this {language} source. Analysis will continue on a "
                    "best-effort basis."
                )
            return True, ""
        except Exception as exc:  # noqa: BLE001
            logger.debug("Syntax validation unavailable for %s: %s", language, exc)
            return None, ""

    # Introspection (used by /health and the evaluation harness)

    @staticmethod
    def capabilities() -> dict:
        return {
            "pii_engine": PIIDetector.engine_name(),
            "injection": InjectionDetector.stats(),
            "supported_languages": sorted(SUPPORTED_LANGUAGES),
        }
