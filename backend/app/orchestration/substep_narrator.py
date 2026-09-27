"""Turns real agent output into a specific, grounded progress line."""

import re
from collections import Counter

_PASS_RE = re.compile(r"(\d+)\s+passed")
_FAIL_RE = re.compile(r"(\d+)\s+failed")
_ERROR_RE = re.compile(r"(\d+)\s+error")
_DIFF_LINE_RE = re.compile(r"^[+-](?![+-]{2})", re.MULTILINE)


def _join(parts: list[str]) -> str:
    return " - ".join(p for p in parts if p)


def narrate_structure(findings: dict) -> str:
    """review_agent: AST + linter results."""
    n_func = len(findings.get("functions", []) or [])
    n_class = len(findings.get("classes", []) or [])
    n_import = len(findings.get("imports", []) or [])
    lint = findings.get("linter_findings", []) or []

    shape = f"{n_func} function(s), {n_class} class(es), {n_import} import(s)"
    if lint:
        rules = Counter(
            (f.get("symbol") or f.get("rule") or f.get("code") or "issue")
            for f in lint
        )
        top = ", ".join(f"{name} x{count}" for name, count in rules.most_common(3))
        lint_part = f"linter flagged {len(lint)} issue(s) ({top})"
    else:
        lint_part = "no lint issues raised"

    return _join([f"Parsed {shape}", lint_part])


def narrate_security(findings: list) -> str:
    """security_agent: Semgrep + CWE/OWASP enrichment results."""
    if not findings:
        return "No OWASP/CWE pattern matches in this snippet"

    sev_counts = Counter((f.get("severity") or "INFO").upper() for f in findings)
    sev_part = ", ".join(f"{c} {s}" for s, c in sev_counts.most_common())

    cwes = []
    for f in findings:
        cwe = f.get("cwe_reference") or f.get("check_id")
        if cwe and cwe not in cwes:
            cwes.append(cwe)
    cwe_part = f"top match: {cwes[0]}" if cwes else ""

    return _join([f"{len(findings)} finding(s) ({sev_part})", cwe_part])


def narrate_risk(risk_analysis: dict) -> str:
    """risk_agent / risk_finalize_agent: composite score."""
    score = risk_analysis.get("risk_score")
    level = risk_analysis.get("risk_level")
    count = risk_analysis.get("finding_count")
    if score is None:
        return "Risk score unavailable"
    return f"Composite risk score {score}/100 ({level}) from {count} finding(s)"


def narrate_risk_finalize(risk_analysis: dict, ai_issues: list) -> str:
    score = risk_analysis.get("risk_score")
    level = risk_analysis.get("risk_level")
    if not ai_issues:
        return f"No additional AI-flagged issues - score holds at {score}/100 ({level})"
    sev_counts = Counter(i.get("severity", "?") for i in ai_issues)
    sev_part = ", ".join(f"{c} {s}" for s, c in sev_counts.most_common())
    return f"Folded in {len(ai_issues)} AI-flagged issue(s) ({sev_part}) - score now {score}/100 ({level})"


def narrate_metrics(metrics: dict) -> str:
    """metrics_agent: size + complexity numbers."""
    if not metrics:
        return "Metrics unavailable"
    total = metrics.get("total_lines")
    code = metrics.get("code_lines")
    comment = metrics.get("comment_lines")
    cc = metrics.get("cyclomatic_complexity")
    mi = metrics.get("maintainability_index")
    rating = metrics.get("maintainability_rating")
    return (
        f"{total} line(s) ({code} code, {comment} comment) - "
        f"cyclomatic complexity {cc}, maintainability index "
        f"{round(mi) if isinstance(mi, (int, float)) else mi} ({rating})"
    )


def narrate_refactor_plan(security_findings: list, review_findings: dict) -> str:
    n_sec = len(security_findings or [])
    lint = (review_findings or {}).get("linter_findings", []) or []
    parts = []
    if n_sec:
        crit = sum(
            1 for f in security_findings
            if (f.get("severity") or "").upper() in ("ERROR", "HIGH", "CRITICAL")
        )
        parts.append(
            f"drafting fixes for {n_sec} security finding(s)"
            + (f" ({crit} high-severity)" if crit else "")
        )
    if lint:
        parts.append(f"{len(lint)} lint issue(s)")
    if not parts:
        return "No flagged issues upstream - refactoring for clarity only"
    return "Plan: " + ", ".join(parts)


def narrate_diff(diff_text: str) -> str:
    """refactor_agent: size of the actual generated diff."""
    if not diff_text or diff_text.startswith("(diff unavailable"):
        return "No diff produced - refactor output could not be extracted"
    changed = len(_DIFF_LINE_RE.findall(diff_text))
    return f"Diff touches {changed} line(s)"


def narrate_validation(warnings: list, is_clean: bool) -> str:
    """refactor_agent: WorkspaceTool.apply_and_validate outcome."""
    if is_clean and not warnings:
        return "Validation passed - public API preserved, file still parses"
    if not warnings:
        return "Validation passed with no warnings"
    return f"Validation raised {len(warnings)} warning(s): {warnings[0]}"


def narrate_documentation(documentation: str) -> str:
    """documentation_agent: size of generated docs."""
    if not documentation:
        return "No documentation generated"
    words = len(documentation.split())
    docstring_blocks = documentation.count('"""') // 2
    if docstring_blocks:
        return f"Wrote {docstring_blocks} docstring block(s), {words} word(s) total"
    return f"Wrote {words} word(s) of module documentation"


def narrate_test_plan(generated_tests: str) -> str:
    """test_generation_agent: how many tests were actually scaffolded."""
    if not generated_tests:
        return "No tests generated"
    n_tests = len(re.findall(r"^\s*def\s+test_", generated_tests, re.MULTILINE))
    if n_tests:
        return f"Scaffolded {n_tests} test function(s)"
    return "Scaffolded a test module"


def narrate_test_execution(execution_result: dict) -> str:
    """test_generation_agent: real pytest outcome, parsed from stdout."""
    if not execution_result.get("ran"):
        reason = execution_result.get("reason", "unknown reason")
        return f"Could not execute tests - {reason}"

    stdout = execution_result.get("stdout", "")
    passed = _PASS_RE.search(stdout)
    failed = _FAIL_RE.search(stdout)
    errored = _ERROR_RE.search(stdout)

    bits = []
    if passed:
        bits.append(f"{passed.group(1)} passed")
    if failed:
        bits.append(f"{failed.group(1)} failed")
    if errored:
        bits.append(f"{errored.group(1)} error(s)")

    prefix = ""
    smoke = execution_result.get("smoke_count")
    if smoke:
        prefix = f"{smoke} signature-derived smoke test(s) + generated cases - "
    if execution_result.get("healed"):
        prefix = "Self-healed to structural smoke suite - "

    if bits:
        return prefix + "test run: " + ", ".join(bits)
    return (prefix + "tests passed") if execution_result.get("passed") else (prefix + "tests failed")
