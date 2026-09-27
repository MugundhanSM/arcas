"""Risk scoring agent."""

import re

_SEVERITY_WEIGHTS = {
    "ERROR": 40, "CRITICAL": 40, "HIGH": 40,
    "WARNING": 20, "MEDIUM": 20,
    "INFO": 10, "LOW": 10,
}

_AI_SEVERITY_WEIGHTS = {
    "CRITICAL": 20, "HIGH": 20,
    "MEDIUM": 10,
    "LOW": 5, "INFO": 5,
}

# Matches numbered findings under the refactor agent's mandated "Security Issues" heading, e.g. "1.
_SECURITY_SECTION_RE = re.compile(
    r"security\s+issues\b(.*?)(?=\n#{0,6}\s*code\s+quality\s+issues\b|\Z)",
    re.IGNORECASE | re.DOTALL,
)
_FINDING_LINE_RE = re.compile(
    r"^\s*\d+\.\s*(.+?)\s*\((CRITICAL|HIGH|MEDIUM|LOW)\)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _level_for_score(score: int) -> str:
    if score >= 80:
        return "CRITICAL"
    if score >= 50:
        return "HIGH"
    if score >= 20:
        return "MEDIUM"
    return "LOW"


class RiskAgent:
    """Aggregates security findings and metrics into a risk assessment."""

    @staticmethod
    def analyze(security_findings, metrics=None):

        metrics = metrics or {}
        score = 0

        for finding in security_findings:

            severity = (finding.get("severity") or "").upper()
            score += _SEVERITY_WEIGHTS.get(severity, 0)

        # Complexity contributes to risk: hard-to-review code is more likely to hide defects.
        complexity = metrics.get("cyclomatic_complexity", 0)
        if complexity > 30:
            score += 15
        elif complexity > 15:
            score += 8

        # Poor maintainability slightly increases risk.
        maintainability = metrics.get("maintainability_index", 100)
        if maintainability < 35:
            score += 10
        elif maintainability < 50:
            score += 5

        score = min(score, 100)

        return {
            "risk_score": score,
            "risk_level": _level_for_score(score),
            "finding_count": len(security_findings),
        }

    @staticmethod
    def extract_ai_security_issues(refactor_markdown: str) -> list:
        """Parse severity-tagged findings from the refactor agent's "Security Issues" section."""
        if not refactor_markdown or not refactor_markdown.strip():
            return []

        section_match = _SECURITY_SECTION_RE.search(refactor_markdown)
        if not section_match:
            return []

        section_text = section_match.group(1)
        issues = []
        for title, severity in _FINDING_LINE_RE.findall(section_text):
            issues.append({
                "title": title.strip(),
                "severity": severity.upper(),
            })
        return issues

    @staticmethod
    def finalize(risk_analysis: dict, refactor_markdown: str = "") -> dict:
        base = dict(risk_analysis or {})
        static_score = base.get("risk_score", 0)
        static_level = base.get("risk_level", _level_for_score(static_score))
        static_finding_count = base.get("finding_count", 0)

        ai_issues = RiskAgent.extract_ai_security_issues(refactor_markdown)
        ai_contribution = sum(
            _AI_SEVERITY_WEIGHTS.get(issue["severity"], 0)
            for issue in ai_issues
        )

        final_score = min(100, static_score + ai_contribution)
        final_level = _level_for_score(final_score)

        base.update({
            "risk_score": final_score,
            "risk_level": final_level,
            "finding_count": static_finding_count + len(ai_issues),
            "static_risk_score": static_score,
            "static_risk_level": static_level,
            "static_finding_count": static_finding_count,
            "ai_finding_count": len(ai_issues),
            "ai_findings": ai_issues,
            "ai_augmented": True,
        })
        return base
