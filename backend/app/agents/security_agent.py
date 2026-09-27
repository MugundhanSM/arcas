"""Security analysis agent."""

from __future__ import annotations

import json
import re as _re
from typing import List, Tuple

from app.core.logging import get_logger
from app.core.react_agent import ReActAgent
from app.tools.llm_tool import LLMTool
from app.tools.retriever_tool import RetrieverTool
from app.tools.semgrep_tool import SemgrepTool

logger = get_logger("arcas.agents.security")


_SYSTEM_PROMPT = (
    "You are ARCAS Security Agent - a specialized static application security "
    "testing agent. Your sole responsibility is detecting OWASP Top 10 "
    "vulnerabilities in submitted code. You NEVER guess or invent "
    "vulnerabilities. Every finding you report MUST be backed by evidence from "
    "a tool call (Semgrep scan or knowledge base retrieval). You reason step "
    "by step. For each finding, trace the data flow: identify the source of "
    "untrusted input, the affected function's business purpose, any existing "
    "guards, and only then write a context-specific fix recommendation. "
    "Format all findings with: severity, line number, CWE reference, "
    "and a context-aware fix recommendation."
)


_ENRICHMENT_RULES = [
    (
        ("subprocess", "shell", "command-injection", "os-system"),
        {
            "owasp_reference": "A03:2021 Injection",
            "cwe_reference": (
                "CWE-78: Improper Neutralization of Special Elements used in "
                "an OS Command"
            ),
            "explanation": (
                "Passing user-controlled input to a shell allows an attacker "
                "to inject arbitrary commands (e.g. 'ls; rm -rf /'). "
                "[Fallback - LLM unavailable for code-specific analysis.]"
            ),
            "remediation": (
                "Use shell=False and pass arguments as a list. Add an "
                "allow-list of permitted commands drawn from your business "
                "requirements (not a generic example set). Validate all inputs "
                "and set an execution timeout. "
                "[Fallback - populate allow-list from business requirements.]"
            ),
        },
    ),
    (
        ("sql", "injection", "query", "execute"),
        {
            "owasp_reference": "A03:2021 Injection",
            "cwe_reference": "CWE-89: SQL Injection",
            "explanation": (
                "Building SQL with string interpolation lets an attacker alter "
                "the query and read or modify arbitrary data. "
                "[Fallback - LLM unavailable for code-specific analysis.]"
            ),
            "remediation": (
                "Use parameterised queries / prepared statements; never "
                "concatenate user input into SQL. "
                "[Fallback - identify the specific query and parameter type.]"
            ),
        },
    ),
    (
        ("eval", "exec", "compile", "code-execution"),
        {
            "owasp_reference": "A03:2021 Injection",
            "cwe_reference": "CWE-95: Eval Injection",
            "explanation": (
                "eval/exec on untrusted input executes attacker-supplied code "
                "in your process. "
                "[Fallback - LLM unavailable for code-specific analysis.]"
            ),
            "remediation": (
                "Remove eval/exec; use ast.literal_eval or an explicit, "
                "validated dispatch table instead. "
                "[Fallback - identify what eval is meant to parse.]"
            ),
        },
    ),
    (
        ("hardcoded", "secret", "password", "credential", "token", "api-key"),
        {
            "owasp_reference": (
                "A07:2021 Identification and Authentication Failures"
            ),
            "cwe_reference": "CWE-798: Use of Hard-coded Credentials",
            "explanation": (
                "Hard-coded credentials in source control are trivially "
                "extracted and cannot be rotated without a code change. "
                "[Fallback - LLM unavailable for code-specific analysis.]"
            ),
            "remediation": (
                "Load the secret from an environment variable or secret "
                "manager inside the function that uses it - not at module "
                "top-level (import-time failures break testing). "
                "[Fallback - check whether the variable is used at module "
                "scope or only inside a function.]"
            ),
        },
    ),
    (
        ("pickle", "yaml", "deserial", "marshal"),
        {
            "owasp_reference": (
                "A08:2021 Software and Data Integrity Failures"
            ),
            "cwe_reference": "CWE-502: Deserialization of Untrusted Data",
            "explanation": (
                "Deserialising untrusted data can instantiate arbitrary "
                "objects and execute code. "
                "[Fallback - LLM unavailable for code-specific analysis.]"
            ),
            "remediation": (
                "Use safe loaders (yaml.safe_load, json) and never unpickle "
                "untrusted bytes. "
                "[Fallback - identify the data source and trust level.]"
            ),
        },
    ),
    (
        ("md5", "sha1", "weak-hash", "insecure-hash", "des", "ecb"),
        {
            "owasp_reference": "A02:2021 Cryptographic Failures",
            "cwe_reference": (
                "CWE-327: Use of a Broken or Risky Cryptographic Algorithm"
            ),
            "explanation": (
                "MD5/SHA1 are broken for security use and vulnerable to "
                "collision attacks. "
                "[Fallback - LLM unavailable for code-specific analysis.]"
            ),
            "remediation": (
                "Use SHA-256+ for integrity and bcrypt/argon2 for passwords. "
                "[Fallback - identify whether this is used for passwords or "
                "data integrity.]"
            ),
        },
    ),
    (
        ("verify", "ssl", "tls", "certificate", "insecure-request"),
        {
            "owasp_reference": "A02:2021 Cryptographic Failures",
            "cwe_reference": "CWE-295: Improper Certificate Validation",
            "explanation": (
                "Disabling TLS verification exposes traffic to "
                "man-in-the-middle attacks. "
                "[Fallback - LLM unavailable for code-specific analysis.]"
            ),
            "remediation": (
                "Enable certificate verification (verify=True) and pin CAs "
                "where appropriate. "
                "[Fallback - check which HTTP client and endpoint are used.]"
            ),
        },
    ),
    (
        ("xss", "cross-site", "innerhtml", "render", "autoescape"),
        {
            "owasp_reference": "A03:2021 Injection",
            "cwe_reference": "CWE-79: Cross-site Scripting",
            "explanation": (
                "Reflecting untrusted input into HTML lets attackers run "
                "script in victims' browsers. "
                "[Fallback - LLM unavailable for code-specific analysis.]"
            ),
            "remediation": (
                "Contextually escape output and enable template "
                "auto-escaping; avoid innerHTML with untrusted data. "
                "[Fallback - identify the template engine in use.]"
            ),
        },
    ),
    (
        ("path", "traversal", "open", "file-read"),
        {
            "owasp_reference": "A01:2021 Broken Access Control",
            "cwe_reference": "CWE-22: Path Traversal",
            "explanation": (
                "Unvalidated path input lets an attacker read or write files "
                "outside the intended directory. "
                "[Fallback - LLM unavailable for code-specific analysis.]"
            ),
            "remediation": (
                "Canonicalise and validate paths against an allow-list base "
                "directory. "
                "[Fallback - identify the base directory and file operation.]"
            ),
        },
    ),
]

_DEFAULT_ENRICHMENT = {
    "owasp_reference": "OWASP Top 10 (2021)",
    "cwe_reference": "CWE - see linked Semgrep rule",
    "explanation": (
        "Semgrep flagged this pattern as a likely security weakness; review "
        "it against secure-coding guidance. "
        "[Fallback - LLM unavailable for code-specific analysis.]"
    ),
    "remediation": (
        "Follow the secure-coding pattern for this issue and validate all "
        "untrusted input. "
        "[Fallback - LLM unavailable for code-specific analysis.]"
    ),
}

_SEVERITY_CONFIDENCE = {
    "ERROR": 0.95,
    "CRITICAL": 0.95,
    "HIGH": 0.9,
    "WARNING": 0.8,
    "MEDIUM": 0.75,
    "INFO": 0.6,
    "LOW": 0.6,
}


class SecurityAgent:
    """Static application security testing agent with ReAct reasoning."""

    @staticmethod
    def analyze(
        code: str,
        language: str = "python",
        deep_scan: bool = False,
        review_findings: dict | None = None,
    ) -> List[dict]:
        """Backward-compatible entry point: returns the enriched findings."""
        findings, _trace = SecurityAgent.analyze_with_trace(
            code, language, deep_scan, review_findings
        )
        return findings

    @staticmethod
    def analyze_with_trace(
        code: str,
        language: str = "python",
        deep_scan: bool = False,
        review_findings: dict | None = None,
    ) -> Tuple[List[dict], list]:
        """Run the two-phase enrichment pipeline and return (findings, trace)."""
        raw_findings = SemgrepTool.analyze(code, language, deep_scan=deep_scan)

        # deterministic enrichment - always runs, provides fallbacks.
        enriched = [SecurityAgent._enrich(f, language) for f in raw_findings]

        if enriched and LLMTool.is_available():
            try:
                enriched = SecurityAgent._llm_enrich_findings(
                    code, language, enriched, review_findings or {}
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Phase 2 LLM enrichment failed (%s); keeping Phase 1 "
                    "fallback values.",
                    exc,
                )

        trace = SecurityAgent._build_trace(
            code, language, enriched, review_findings or {}
        )
        return enriched, trace

    # - deterministic enrichment

    @staticmethod
    def _enrich(finding: dict, language: str) -> dict:
        """Apply keyword-based OWASP/CWE classification (Phase 1 seed)."""
        check_id = (finding.get("check_id") or "").lower()
        message = (finding.get("message") or "").lower()
        haystack = f"{check_id} {message}"

        mapping = _DEFAULT_ENRICHMENT
        for keywords, data in _ENRICHMENT_RULES:
            if any(kw in haystack for kw in keywords):
                mapping = data
                break

        severity = (finding.get("severity") or "INFO").upper()
        confidence = _SEVERITY_CONFIDENCE.get(severity, 0.7)

        return {
            **finding,
            "owasp_reference": mapping["owasp_reference"],
            "cwe_reference": mapping["cwe_reference"],
            "explanation": mapping["explanation"],  # Phase 1 fallback
            "remediation": mapping["remediation"],  # Phase 1 fallback
            "confidence": confidence,
            "data_flow_context": {},  # populated by Phase 2
            "data_flow_summary": "",  # populated by Phase 2
        }

    # - context-aware LLM enrichment

    @staticmethod
    def _trace_data_flow(code: str, finding: dict) -> dict:
        start_line = finding.get("start_line") or 0
        lines = code.splitlines()
        n = len(lines)

        # Context window around the vulnerability (±5 lines)
        ctx_start = max(0, start_line - 6)
        ctx_end = min(n, start_line + 4)
        call_site_context = "\n".join(lines[ctx_start:ctx_end])

        # Walk backwards to find the enclosing function definition
        affected_function = "module-level"
        untrusted_params: list[str] = []
        for i in range(min(start_line - 1, n - 1), -1, -1):
            m = _re.match(
                r"(\s*)def\s+(\w+)\s*\(([^)]*)\)", lines[i]
            )
            if m:
                affected_function = m.group(2)
                raw_params = [
                    p.strip().split(":")[0].strip().split("=")[0].strip()
                    for p in m.group(3).split(",")
                    if p.strip()
                ]
                untrusted_params = [
                    p for p in raw_params if p not in ("self", "cls", "")
                ]
                break

        # Collect guard / validation lines between function entry and sink
        guard_keywords = (
            "if ", "assert ", "validate", "sanitize", "escape",
            "allow", "whitelist", "deny", "block", "check",
            "raise ", "not in", "not allowed",
        )
        existing_guards: list[str] = []
        for ln in lines[ctx_start : max(0, start_line - 1)]:
            if any(kw in ln.lower() for kw in guard_keywords):
                stripped = ln.strip()
                if stripped and stripped not in existing_guards:
                    existing_guards.append(stripped)

        return {
            "affected_function": affected_function,
            "untrusted_params": untrusted_params,
            "existing_guards": existing_guards,
            "call_site_context": call_site_context,
        }

    @staticmethod
    def _llm_enrich_findings(
        code: str,
        language: str,
        seed_findings: list,
        review_findings: dict,
    ) -> list:
        if not seed_findings:
            return seed_findings

        # Build data-flow context for every finding
        flow_data = [SecurityAgent._trace_data_flow(code, f) for f in seed_findings]

        # Construct the per-finding payload for the LLM
        payload = []
        for finding, flow in zip(seed_findings, flow_data):
            payload.append({
                "check_id": finding.get("check_id"),
                "severity": finding.get("severity"),
                "message": finding.get("message"),
                "line": finding.get("start_line"),
                "owasp_reference": finding.get("owasp_reference"),
                "cwe_reference": finding.get("cwe_reference"),
                "data_flow": flow,
            })

        known_fns = review_findings.get("functions", []) or []
        known_cls = review_findings.get("classes", []) or []

        prompt = f"""You are a security expert performing root-cause analysis on code.

CODE ({language}):
```
{code[:3000]}
```

MODULE STRUCTURE:
- Functions: {known_fns}
- Classes:   {known_cls}

FINDINGS WITH DATA-FLOW CONTEXT:
{json.dumps(payload, indent=2)}

For EACH finding, reason about:
1. The business purpose of the affected function (infer from its name, params,
   docstring, and call sites in the code).
2. Which parameter carries untrusted data and from where (user input, network,
   file system, environment).
3. Actual exploitability given the data-flow context - is the path reachable?
   Are there existing guards that already partially mitigate the risk?
4. The most specific, minimal remediation for THIS code. Do not apply generic
   templates. If an allow-list is needed, note that the permitted values must
   be defined from business requirements (add a TODO placeholder if unclear).

Respond with ONLY a JSON array - no markdown fences, no prose, no preamble:
[
  {{
    "check_id": "<same as in input>",
    "explanation": "<2-3 sentences specific to this code, referencing the actual function name, parameter, and data source>",
    "remediation": "<specific steps for this code; if an allow-list is needed, note that values must come from business requirements and write a TODO placeholder instead of inventing example values>",
    "data_flow_summary": "<one sentence describing: source of untrusted input → [any existing guards] → vulnerable sink>"
  }}
]"""

        raw = LLMTool.generate(prompt)
        # Strip markdown code fences if the model wraps the JSON anyway
        raw = _re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=_re.MULTILINE)
        raw = _re.sub(r"\s*```\s*$", "", raw.strip(), flags=_re.MULTILINE)
        enrichments = json.loads(raw.strip())

        if not isinstance(enrichments, list):
            logger.warning("LLM enrichment returned unexpected type; keeping seed.")
            return [
                {**f, "data_flow_context": flow}
                for f, flow in zip(seed_findings, flow_data)
            ]

        # Build a lookup so we can merge by check_id (order may differ)
        enrich_map = {
            e["check_id"]: e
            for e in enrichments
            if isinstance(e, dict) and "check_id" in e
        }

        result = []
        for finding, flow in zip(seed_findings, flow_data):
            cid = finding.get("check_id")
            e = enrich_map.get(cid, {})
            result.append({
                **finding,
                # Override Phase 1 fallbacks with LLM context-aware text
                "explanation": e.get("explanation") or finding.get("explanation"),
                "remediation": e.get("remediation") or finding.get("remediation"),
                "data_flow_summary": e.get("data_flow_summary", ""),
                "data_flow_context": flow,
            })
        return result

    # Reasoning trace

    @staticmethod
    def _build_trace(
        code: str,
        language: str,
        findings: List[dict],
        review_findings: dict,
    ) -> list:
        if LLMTool.is_available():
            try:
                return SecurityAgent._react_trace(
                    code, language, findings, review_findings
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Security ReAct loop failed (%s); using deterministic trace.", exc
                )
        return SecurityAgent._deterministic_trace(language, findings)

    @staticmethod
    def _react_trace(
        code: str,
        language: str,
        findings: List[dict],
        review_findings: dict,
    ) -> list:
        scan_summary = json.dumps(
            [
                {
                    "check_id": f.get("check_id"),
                    "severity": f.get("severity"),
                    "line": f.get("start_line"),
                    "message": f.get("message"),
                }
                for f in findings
            ],
            indent=2,
        )[:2000]

        def semgrep_scan(_arg: str) -> str:
            return scan_summary or "No findings."

        def knowledge_base(query: str) -> str:
            return RetrieverTool.get_context(
                language=language, query=query
            )[:1500]

        def trace_data_flow(check_id_or_query: str) -> str:
            """Trace untrusted-input data flow to the vulnerability sink."""
            # Match by check_id first, then by message substring
            for f in findings:
                if (
                    str(f.get("check_id", "")) == check_id_or_query
                    or check_id_or_query.lower() in str(f.get("message", "")).lower()
                ):
                    flow = SecurityAgent._trace_data_flow(code, f)
                    return json.dumps(flow, indent=2)
            # Default: return context for the first finding
            if findings:
                return json.dumps(
                    SecurityAgent._trace_data_flow(code, findings[0]), indent=2
                )
            return "{}"

        agent = ReActAgent(
            system_prompt=_SYSTEM_PROMPT,
            tools={
                "semgrep_scan": semgrep_scan,
                "knowledge_base": knowledge_base,
                "trace_data_flow": trace_data_flow,
            },
            max_iterations=5,
        )
        task = (
            f"Analyze the following {language} code for OWASP Top 10 vulnerabilities. "
            "STEP 1: Call semgrep_scan to get concrete findings. "
            "STEP 2: For each finding, call trace_data_flow with the check_id to "
            "understand the business purpose of the affected function, which "
            "parameter carries untrusted data, and whether any guards already exist. "
            "STEP 3: Call knowledge_base for the relevant OWASP/CWE guidance. "
            "STEP 4: Write a concise security report with context-aware explanations "
            "and remediations specific to THIS code (not generic patterns). "
            "Explicitly note if a recommended control (e.g. an allow-list) requires "
            "business-requirement input that cannot be inferred from the code."
            f"\n\nCODE:\n{code[:2000]}"
        )
        _final, trace = agent.run(task)
        return trace

    @staticmethod
    def _deterministic_trace(language: str, findings: List[dict]) -> list:
        owasp = (
            ", ".join(
                sorted({f.get("owasp_reference", "") for f in findings})
            )
            or "none"
        )
        return [
            {
                "type": "thought",
                "content": (
                    "I should scan the code with Semgrep to find concrete "
                    "vulnerabilities before drawing any conclusions."
                ),
                "iteration": 0,
            },
            {
                "type": "action",
                "tool": "semgrep_scan",
                "input": "source code",
                "iteration": 0,
            },
            {
                "type": "observation",
                "tool": "semgrep_scan",
                "result": (
                    f"Found {len(findings)} finding(s)."
                    + (
                        " "
                        + "; ".join(
                            f"{f.get('check_id')} (line {f.get('start_line')})"
                            for f in findings[:5]
                        )
                        if findings
                        else " Code is clean of known patterns."
                    )
                ),
                "iteration": 0,
            },
            {
                "type": "thought",
                "content": (
                    "Now I trace the data flow for each finding to understand "
                    "the business purpose, untrusted parameter, and existing guards."
                ),
                "iteration": 1,
            },
            {
                "type": "action",
                "tool": "trace_data_flow",
                "input": "first finding check_id",
                "iteration": 1,
            },
            {
                "type": "observation",
                "tool": "trace_data_flow",
                "result": (
                    "Extracted affected function, untrusted parameters, and "
                    "existing guards for each finding. "
                    "(Deterministic fallback - LLM unavailable.)"
                ),
                "iteration": 1,
            },
            {
                "type": "thought",
                "content": (
                    "Now I retrieve the relevant OWASP guidance for these "
                    "findings to ground my remediation advice."
                ),
                "iteration": 2,
            },
            {
                "type": "action",
                "tool": "knowledge_base",
                "input": "OWASP guidance for detected findings",
                "iteration": 2,
            },
            {
                "type": "observation",
                "tool": "knowledge_base",
                "result": f"Mapped findings to: {owasp}.",
                "iteration": 2,
            },
            {
                "type": "final",
                "content": (
                    f"I have sufficient evidence. Reporting {len(findings)} "
                    "finding(s), each with an OWASP reference, CWE, "
                    "code-specific explanation, remediation, and confidence score."
                ),
                "iteration": 3,
            },
        ]
