"""Output guardrails layer."""

import ast
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from app.core.logging import get_logger
from app.tools.semgrep_tool import SemgrepTool

logger = get_logger("arcas.guardrails.output")


_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+")


def _tokenize(text: str) -> List[str]:
    return [tok.lower() for tok in _WORD_RE.findall(text or "")]


# Dangerous code patterns that must never appear in a suggested fix.
_DANGEROUS_PATTERNS = [
    (r"shell\s*=\s*True", "Suggests subprocess with shell=True"),
    (r"\beval\s*\(", "Suggests use of eval()"),
    (r"\bexec\s*\(", "Suggests use of exec()"),
    (r"pickle\.loads?\s*\(", "Suggests unsafe pickle deserialization"),
    (r"verify\s*=\s*False", "Suggests disabling TLS verification"),
    (r"\bos\.system\s*\(", "Suggests os.system() shell execution"),
    (r"yaml\.load\s*\(", "Suggests unsafe yaml.load()"),
    (r"hashlib\.(md5|sha1)\b", "Suggests a weak hash algorithm"),
    (r"\bmd5\b|\bsha1\b", "Suggests a weak hash algorithm"),
    (r"DROP\s+TABLE", "Contains a destructive SQL statement"),
]


@dataclass
class OutputGuardrailResult:
    confidence: float
    passed: bool
    security_regressions: List[str] = field(default_factory=list)
    hallucination_warnings: List[str] = field(default_factory=list)
    syntax_warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    # Populated when SelfCheckGPT ran.
    selfcheck: Optional[dict] = None

    def as_dict(self) -> dict:
        return {
            "confidence": self.confidence,
            "passed": self.passed,
            "security_regressions": self.security_regressions,
            "hallucination_warnings": self.hallucination_warnings,
            "syntax_warnings": self.syntax_warnings,
            "notes": self.notes,
            "selfcheck": self.selfcheck,
        }


class OutputGuardrails:
    """Validates LLM-generated artefacts before they reach the client."""

    @staticmethod
    def check(
        generated_text: str,
        source_code: str,
        review_findings: dict,
        language: str = "python",
        selfcheck_result=None,
    ) -> OutputGuardrailResult:
        result = OutputGuardrailResult(confidence=1.0, passed=True)

        if not generated_text or not generated_text.strip():
            result.confidence = 0.0
            result.passed = False
            result.notes.append("Generated content was empty.")
            return result

        text = generated_text

        # Security regression check on suggested code.
        for pattern, message in _DANGEROUS_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                result.security_regressions.append(message)

        code_blocks = re.findall(r"```(\w*)\n(.*?)```", text, re.DOTALL)

        if code_blocks:
            largest_block = max(code_blocks, key=lambda x: len(x[1]))[1]
            if largest_block.strip():
                try:
                    semgrep_findings = SemgrepTool.analyze(
                        largest_block, language, deep_scan=False
                    )
                    critical = [
                        f
                        for f in semgrep_findings
                        if (f.get("severity") or "").upper()
                        in ("ERROR", "WARNING", "CRITICAL")
                    ]
                    for finding in critical:
                        result.security_regressions.append(
                            f"Semgrep [{finding.get('severity')}]: "
                            f"{finding.get('message', 'issue')} at line "
                            f"{finding.get('start_line')}"
                        )
                except Exception:  # noqa: BLE001
                    pass  # Semgrep unavailable - regex check is the fallback

        known = set(
            (review_findings.get("functions") or [])
            + (review_findings.get("classes") or [])
        )
        referenced = set()
        for _lang, block in code_blocks:
            referenced.update(
                re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", block)
            )

        # Builtins / common library calls we should not flag.
        ignore = {
            "print", "len", "range", "str", "int", "list", "dict", "set",
            "assert", "open", "input", "super", "isinstance", "test",
            "describe", "it", "expect", "import", "return", "if", "for",
            "while", "def", "class", "self", "main",
        }
        suspicious = [
            name
            for name in referenced
            if name not in known
            and name not in ignore
            and name not in source_code
        ]
        # Only treat it as a hallucination signal if many unknown symbols.
        if len(suspicious) > 8:
            result.hallucination_warnings.append(
                f"{len(suspicious)} referenced symbol(s) not found in the "
                "source; verify the suggestion before applying."
            )

        # AST validity check on suggested Python code blocks.
        for lang, block in code_blocks:
            if lang.lower() in ("python", "py", ""):
                snippet = block.strip()
                # Skip obvious diff/markdown fragments.
                if not snippet or snippet.startswith(("+", "-", "@@", "//")):
                    continue
                try:
                    ast.parse(snippet)
                except SyntaxError:
                    # Only flag when it really looks like Python.
                    if re.search(r"\b(def|class|import|return)\b", snippet):
                        result.syntax_warnings.append(
                            "A suggested Python code block does not parse "
                            "cleanly; review before applying."
                        )
                        break

        # Calibrated confidence.
        result.security_regressions = list(
            dict.fromkeys(result.security_regressions)
        )
        if selfcheck_result is not None and getattr(selfcheck_result, "ran", False):
            result.selfcheck = selfcheck_result.as_dict()
            result.hallucination_warnings.extend(selfcheck_result.warnings)

        confidence = 1.0
        confidence -= 0.25 * len(result.security_regressions)
        confidence -= 0.15 * len(result.hallucination_warnings)
        confidence -= 0.10 * len(result.syntax_warnings)

        if result.selfcheck is not None:
            consistency = max(0.35, float(selfcheck_result.consistency))
            confidence *= consistency

        result.confidence = round(max(0.0, min(1.0, confidence)), 2)

        # The artefact "fails" hard only on a security regression.
        result.passed = len(result.security_regressions) == 0

        if not result.passed:
            logger.warning(
                "Output guardrails flagged security regression(s): %s",
                result.security_regressions,
            )

        return result

    @staticmethod
    def selfcheck_consistency(
        prompt: str,
        primary_response: str,
        num_samples: int = 3,
        language: str = "python",
        sampler=None,
        system_prompt: str = "",
    ):
        """Run SelfCheckGPT hallucination detection."""
        from app.core.selfcheck import SelfCheckGPT

        return SelfCheckGPT.check(
            prompt=prompt,
            primary_response=primary_response,
            num_samples=num_samples,
            sampler=sampler,
            system_prompt=system_prompt,
        )

    @staticmethod
    def selfcheck_tuple(
        prompt: str,
        primary_response: str,
        num_samples: int = 3,
        language: str = "python",
    ) -> Tuple[float, List[str]]:
        """Backwards-compatible (consistency, warnings) accessor."""
        result = OutputGuardrails.selfcheck_consistency(
            prompt, primary_response, num_samples, language
        )
        return result.consistency, result.warnings
