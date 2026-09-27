import json

from app.core.logging import get_logger
from app.core.react_agent import ReActAgent
from app.core.result_cache import ResultCache
from app.tools.llm_tool import LLMNotConfiguredError, LLMTool
from app.tools.retriever_tool import RetrieverTool
from app.tools.semgrep_tool import SemgrepTool

logger = get_logger("arcas.agents.refactor")


_SYSTEM_PROMPT = (
    "You are ARCAS Refactor Agent - a senior software architect producing "
    "ENTERPRISE-GRADE fixes. An enterprise-grade fix closes the ROOT CAUSE of "
    "a finding, not just the narrowest edit that silences a linter or scanner "
    "rule. You stay disciplined about SCOPE - you never introduce new files, "
    "services, dependencies, or architectural layers that do not already "
    "exist - but within the file under review you ARE expected to add "
    "whatever a senior engineer would consider necessary for the fix to be "
    "genuinely safe: input validation, allow-lists, timeouts, parameterised "
    "calls, proper error handling, or small helper functions. Every change "
    "must be traceable to a specific finding, but 'traceable' means "
    "'addresses what the finding is actually warning about', not 'touches "
    "the fewest characters'. Before choosing any fix, you MUST understand "
    "the business purpose of the affected code, the trust boundary of the "
    "untrusted input, and what constitutes a legitimate call. Configuration "
    "values (allow-lists, limits, timeouts) must be inferred from the code "
    "itself; never invent values not supported by the code's own evidence. "
    "SEPARATE THE FIX FROM HARDENING: the MINIMAL fix is the smallest change "
    "that closes the vulnerability's root cause (e.g. shell=True -> shell=False "
    "with shlex parsing removes command injection on its own). Present that "
    "first and unambiguously. Additional hardening (allow-lists, timeouts, "
    "rate limits) is OPTIONAL and context-dependent - offer it as clearly "
    "labelled defence-in-depth, recommend it, but do not merge it into the "
    "minimal fix or add hardening whose parameters you'd have to invent. A "
    "tight, correct fix plus a short 'recommended hardening' note beats a large "
    "blob that buries the actual fix. When you remove a hardcoded secret, "
    "removing the line is necessary but NOT sufficient: state that the secret "
    "is already in version-control history and MUST be rotated/revoked. "
    "You always output the COMPLETE refactored file "
    "under the ## COMPLETE REFACTORED FILE heading."
)


class RefactorAgent:
    """Generates refactoring and remediation guidance."""

    @staticmethod
    def analyze(
        source_code: str,
        language: str,
        review_findings: dict,
        security_findings: list,
        risk_analysis: dict,
        metrics: dict | None = None,
        intent: str = "full_review",
    ):
        recommendations, _trace = RefactorAgent.analyze_with_trace(
            source_code,
            language,
            review_findings,
            security_findings,
            risk_analysis,
            metrics,
            intent,
        )
        return recommendations

    @staticmethod
    def analyze_with_trace(
        source_code: str,
        language: str,
        review_findings: dict,
        security_findings: list,
        risk_analysis: dict,
        metrics: dict | None = None,
        intent: str = "full_review",
    ):
        # Memoise the (expensive) LLM call.
        cached = ResultCache.get_text(
            "refactor", source_code, language, extra=intent
        )
        if cached is not None:
            return cached, RefactorAgent._trace_stub(
                language, security_findings, from_cache=True
            )

        retrieval_query = source_code + "\n" + json.dumps(security_findings)
        knowledge_context = RetrieverTool.get_context(
            language=language,
            query=retrieval_query,
        )

        prompt = RefactorAgent._build_prompt(
            source_code,
            language,
            review_findings,
            security_findings,
            risk_analysis,
            metrics,
            knowledge_context,
        )

        trace: list = []
        try:
            result = LLMTool.generate(prompt, system_prompt=_SYSTEM_PROMPT)
            trace = RefactorAgent._build_trace(
                source_code, language, security_findings, knowledge_context
            )
        except LLMNotConfiguredError:
            logger.warning(
                "LLM not configured - returning deterministic fallback "
                "recommendations."
            )
            result = RefactorAgent._fallback(
                language, security_findings, risk_analysis
            )
            trace = RefactorAgent._trace_stub(language, security_findings)
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM generation failed: %s", exc)
            result = RefactorAgent._fallback(
                language, security_findings, risk_analysis
            )
            trace = RefactorAgent._trace_stub(language, security_findings)

        ResultCache.set_text(
            "refactor", source_code, language, result, extra=intent
        )
        return result, trace

    @staticmethod
    def build_selfcheck_prompt(
        source_code: str,
        language: str,
        review_findings: dict,
        security_findings: list,
    ) -> str:
        """Prompt used for SelfCheckGPT resampling."""
        findings = "; ".join(
            str(f.get("message", f)) for f in (security_findings or [])[:6]
        ) or "none reported by static analysis"
        functions = ", ".join((review_findings or {}).get("functions", [])[:10])
        return (
            f"Review this {language} code and state the concrete problems "
            f"and the specific fix for each, naming the exact APIs involved.\n\n"
            f"Known static-analysis findings: {findings}\n"
            f"Functions present: {functions or 'n/a'}\n\n"
            f"```{language}\n{source_code[:4000]}\n```"
        )

    @staticmethod
    def _build_prompt(
        source_code,
        language,
        review_findings,
        security_findings,
        risk_analysis,
        metrics,
        knowledge_context,
    ) -> str:
        mandatory = RefactorAgent._mandatory_output_block(language)
        return f"""
You are a senior software architect and security expert.

Use the secure coding knowledge provided below
when generating recommendations.

==================================================
KNOWLEDGE BASE
==================================================

{knowledge_context}

==================================================
SOURCE CODE ({language})
==================================================

{source_code}

==================================================
STRUCTURE ANALYSIS
==================================================

{json.dumps(review_findings, indent=2)}

==================================================
SECURITY FINDINGS
==================================================

{json.dumps(security_findings, indent=2)}

==================================================
RISK ANALYSIS
==================================================

{json.dumps(risk_analysis, indent=2)}

==================================================
CODE METRICS
==================================================

{json.dumps(metrics or {}, indent=2)}

══════════════════════════════════════════════════
STEP 1 - UNDERSTAND THE CODE BEFORE FIXING (MANDATORY)
══════════════════════════════════════════════════

Before designing any fix, answer these four questions from the SOURCE CODE
above. Write 2-4 sentences capturing your answers - they will directly
inform the fix design in Step 2.

1. BUSINESS PURPOSE: What does this function/module do? Who calls it and
   for what legitimate purpose? Read function names, docstrings, variable
   names, and call sites.

2. TRUST BOUNDARY: Is the untrusted input coming from an end user, an
   authenticated admin, an internal caller, or the network? Different
   sources call for different mitigations.

3. LEGITIMATE INPUTS: What inputs does this code accept under normal
   operation? What would a valid, non-malicious call look like?

4. EXISTING CONTROLS: Are there guards, validators, or sanitizers already
   in the code? If so, is the proposed fix augmenting or replacing them?

══════════════════════════════════════════════════
STEP 2 - DESIGN THE MINIMAL FIX (MANDATORY)
══════════════════════════════════════════════════

Using your Step 1 answers, determine:

1. TRUE ROOT CAUSE: What specifically makes this code vulnerable in its
   actual context? (Not just the finding category - what specific code path
   is exploitable given the trust boundary and input you identified?)

2. MINIMAL FIX: What is the smallest change that closes the root cause
   while preserving all legitimate behaviour identified in Step 1?

3. CONFIGURATION VALUES: Does the fix require constants such as allow-lists,
   size limits, or timeouts?

   RULE - INFER, NEVER INVENT:
   Every configuration value must have evidence in the source code.
   Look for: existing constants, docstrings, variable names, usage patterns,
   related functions, or comments that suggest the intended values.

   If the code provides NO basis for a specific value, leave the control
   UNCONFIGURED with a TODO - but the unconfigured state MUST FAIL CLOSED.
   NEVER write a list like ['ls', 'pwd', 'echo', 'cat'] unless those exact
   commands appear as evidence in the code. Generic textbook examples are not
   configuration values - they are placeholders that can silently ship as
   production policy.

   RULE - FAIL CLOSED, NEVER FAIL OPEN (critical):
   A security control that is empty or unconfigured MUST DENY, never allow.
   The classic mistake is a guard that no-ops when the allow-list is empty:
       # WRONG - fails OPEN: when ALLOWED_COMMANDS is empty this check is
       # skipped entirely and EVERY command runs. The "secure default" is a
       # lie; the control is silently disabled.
       if ALLOWED_COMMANDS and command not in ALLOWED_COMMANDS:
           raise ValueError(...)
   The correct shape denies whenever the command is not explicitly permitted,
   which for an empty set means deny everything:
       # RIGHT - fails CLOSED: nothing runs until the list is populated.
       if command not in ALLOWED_COMMANDS:
           raise ValueError("that command is not in the allow-list ...")
   Your code, its docstring, and its tests must all agree on this: if you
   document "empty allow-list denies all", the implementation must actually
   deny all. State the empty-state behaviour explicitly in the docstring.

   RULE - SURFACE, DON'T BURY, A BEHAVIOUR-CHANGING DECISION:
   If failing closed with an unconfigured control would make the program
   non-functional (e.g. an interactive command runner that now runs nothing
   until ALLOWED_COMMANDS is filled), do NOT silently pick fail-open to keep it
   "working", and do NOT hide the consequence inside a TODO. Instead: keep the
   fix fail-closed AND state prominently at the TOP of your response that the
   tool is now inert until the allow-list is populated, so a human makes the
   call. Sometimes the code's very purpose ("run whatever the user types") IS
   the vulnerability and there is no safe drop-in default - say so plainly
   rather than pretending a template closed it.

4. SIDE EFFECTS: Does the fix add any code that runs at module import time?

   RULE - NO MODULE-LEVEL SIDE EFFECTS:
   Never move runtime guards to module top-level. Import-time failures break
   test collection and harm composability with other modules.
   Wrong (breaks imports when APP_PASSWORD is not set in tests):
       password = os.getenv("APP_PASSWORD")
       if password is None:              # runs at import time
           raise ValueError("...")
   Right (deferred to the function that uses it):
       def _get_password() -> str:
           pw = os.getenv("APP_PASSWORD")
           if pw is None:
               raise ValueError("APP_PASSWORD environment variable is required.")
           return pw
   Or use a lazy module-level accessor; the key constraint is that importing
   the module must never raise.

══════════════════════════════════════════════════
STEP 3 - APPLY THE FIX
══════════════════════════════════════════════════

Using the root cause and minimal fix from Step 2, apply the changes.
The category checklist below is a REFERENCE GUIDE for Step 3, not a
replacement for Step 2's business-context analysis. Consult only the
rows that are relevant to your Step 2 findings; ignore the rest.

==================================================
TASK
==================================================

Analyze the code and provide targeted, enterprise-grade recommendations under
these headings only:

1. Security Issues (fix these - ordered by severity)
2. Code Quality Issues (fix these - only real problems, not style preferences)

Requirements:

- Apply OWASP principles and secure coding best practices where applicable.
- Explain WHY each recommendation matters in one sentence.
- Prioritise critical security issues first.
- Return clean markdown.

PROPORTIONALITY / SCOPE DISCIPLINE: Keep the original naming conventions,
comment style, and code organisation. Do NOT introduce new files, services,
frameworks, or architectural patterns that do not already exist (e.g. don't
pull in a config-management library to fix one hardcoded constant). Within
the existing file, however, you ARE expected to add what a genuine fix
requires - validation, allow-lists, timeouts, helper functions, exception
handling - even if that means the file grows. A correct fix that is slightly
longer beats an incomplete fix that is shorter.

PRESERVE THE PUBLIC API - this is a hard rule, not a style preference. Every
top-level function and class name that exists in the ORIGINAL file must still
exist, with the same name, in your refactored file, even if its internal
implementation changes completely. Do NOT rename `run` to `execute_command`,
split it into a differently-named entry point, or otherwise remove a name
the caller depends on - the workspace validator that checks your output
treats a removed public name as a broken fix and will discard it entirely,
so a "better name" is never worth losing the fix over. You MAY add new
helper functions/constants alongside the original ones (e.g. a private
`_is_allowed()` helper, an `ALLOWED_COMMANDS` constant) - adding is always
safe; removing or renaming an existing public name is not. If a name
genuinely is the problem (e.g. it shadows a builtin or is actively
misleading), say so as a Code Quality finding and let the human decide,
rather than silently renaming it in the rewrite.

ENTERPRISE-GRADE FIX BAR - root-cause checklist by finding category.
Apply whichever rows are relevant to your Step 2 findings; ignore the rest.
Remember: this checklist tells you WHAT CONTROLS to consider, not WHAT
VALUES to put in them (that came from Step 2).

- Command/OS injection: switching `shell=True` to `shell=False` is necessary
  but NOT sufficient on its own - the function can still execute *any*
  program the caller names. Add an explicit allow-list of permitted
  commands/binaries (values from Step 2 analysis of the code, not invented
  examples), use `shlex.split()` rather than `.split()` for quote-aware
  tokenization, set an execution `timeout` (derive a reasonable value from
  any existing timeouts in the codebase, or use a TODO placeholder), and
  handle `FileNotFoundError` / `TimeoutExpired` / empty-input explicitly.
- SQL injection: use parameterised queries / prepared statements, never
  string formatting or concatenation, even after "sanitising" input.
- Insecure deserialization (`eval`, `exec`, `pickle.loads`, `yaml.load`):
  replace with the safe equivalent (`ast.literal_eval`, `yaml.safe_load`,
  a schema-validated parser) - do not just wrap the same unsafe call in a
  try/except.
- Hardcoded secrets/credentials: remove the literal and source it from an
  environment variable or secret manager inside the function that uses it
  (NEVER at module top-level). Read from `os.environ` with a clear error
  when missing - don't delete the variable if it's actually used.
- Weak crypto/hashing (`md5`, `sha1`, plaintext passwords): replace with a
  modern algorithm appropriate to the use case (e.g. `bcrypt`/`scrypt`/
  `argon2` for passwords, `sha256`+ for integrity) and explain the choice.
- Disabled TLS verification / SSRF: re-enable verification, validate and
  allow-list destination hosts/schemes before any outbound request.
- Path traversal: resolve and validate the final path stays within an
  intended base directory before any file operation.
- Missing input validation / unbounded resource use: add explicit bounds
  (length, type, range, timeout) rather than trusting the caller.

==================================================
FINAL CHECK (before writing the refactored file)
==================================================

Before producing the ## COMPLETE REFACTORED FILE, verify:

1. Does the fix address the root cause identified in Step 1 - not just the
   lint rule?
2. Does every configuration constant have evidence from the code, or a TODO
   placeholder? Are there any invented example values (e.g. ['ls', 'pwd'])
   that should be TODOs instead?
3. Is any new code running at module import time that could break a test
   that simply does `import my_module`?
4. Is the public API intact? Were any existing public function or class names
   removed or renamed?

{mandatory}
"""

    @staticmethod
    def _mandatory_output_block(language: str) -> str:
        bar = "\u2550" * 58
        fence = "```"
        return (
            f"{bar}\n"
            "OUTPUT FORMAT - MANDATORY - DO NOT DEVIATE\n"
            f"{bar}\n\n"
            "Your response MUST end with EXACTLY this structure:\n\n"
            "## COMPLETE REFACTORED FILE\n\n"
            f"{fence}{language}\n"
            "<ENTIRE FILE HERE - every line, not a snippet>\n"
            f"{fence}\n\n"
            "Rules:\n"
            "- Output the FULL file. If the original has 50 lines, output all "
            "50 lines (fixed).\n"
            "- Do NOT add prose after the fenced block.\n"
            "- The heading must be EXACTLY \"## COMPLETE REFACTORED FILE\" "
            "(case-insensitive is fine).\n"
            "- If you cannot safely rewrite the full file, write the original "
            "unchanged inside the block.\n"
            "  A diff of \"no changes\" is vastly better than an empty or "
            "partial refactored file.\n"
            f"{bar}"
        )

    @staticmethod
    def _build_trace(source_code, language, security_findings, knowledge):
        def semgrep_scan(_arg: str) -> str:
            findings = SemgrepTool.analyze(source_code, language)
            return json.dumps(findings, indent=2)[:1500] or "No findings."

        def knowledge_base(query: str) -> str:
            return RetrieverTool.get_context(
                language=language, query=query
            )[:1200]

        def verify_syntax(_arg: str) -> str:
            return "Refactored file will be validated in the workspace."

        agent = ReActAgent(
            system_prompt=_SYSTEM_PROMPT,
            tools={
                "semgrep_scan": semgrep_scan,
                "knowledge_base": knowledge_base,
                "verify_syntax": verify_syntax,
            },
            max_iterations=1,
        )
        try:
            agent.tools["semgrep_scan"]("")
        except Exception:  # noqa: BLE001
            pass
        return RefactorAgent._trace_stub(language, security_findings)

    @staticmethod
    def _trace_stub(language, security_findings, from_cache: bool = False):
        prefix = "(cached) " if from_cache else ""
        return [
            {
                "type": "thought",
                "content": (
                    f"{prefix}Step 1: Understand the business purpose of the "
                    "affected code, its trust boundary, and legitimate inputs "
                    "before designing any fix."
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
                "result": f"{len(security_findings)} finding(s) to address.",
                "iteration": 0,
            },
            {
                "type": "thought",
                "content": (
                    "Step 2: Design the minimal fix from the business context "
                    "analysis. Infer any required configuration values (allow-"
                    "lists, timeouts) from the code itself; use TODO placeholders "
                    "for values not evidenced in the code. Ensure no module-level "
                    "side effects are introduced."
                ),
                "iteration": 1,
            },
            {
                "type": "action",
                "tool": "knowledge_base",
                "input": f"secure coding patterns for {language}",
                "iteration": 1,
            },
            {
                "type": "observation",
                "tool": "knowledge_base",
                "result": "Retrieved secure-coding guidance.",
                "iteration": 1,
            },
            {
                "type": "thought",
                "content": (
                    "Step 3: Apply the fix with the category checklist as a "
                    "reference. Run final check: root cause addressed, no "
                    "invented config values, no import-time side effects, "
                    "public API intact."
                ),
                "iteration": 2,
            },
            {
                "type": "final",
                "content": (
                    "Produced minimal recommendations plus a COMPLETE "
                    "REFACTORED FILE for workspace validation."
                ),
                "iteration": 3,
            },
        ]

    @staticmethod
    def _fallback(
        language: str,
        security_findings: list,
        risk_analysis: dict,
    ) -> str:
        """Deterministic markdown summary when the LLM is unavailable."""
        lines = [
            "# Refactoring & Remediation Summary",
            "",
            "> The AI refactoring model was unavailable, so the report "
            "below is generated deterministically from the static "
            "analysis findings.",
            "",
            f"**Language:** {language}",
            f"**Risk level:** {risk_analysis.get('risk_level', 'UNKNOWN')} "
            f"(score: {risk_analysis.get('risk_score', 0)})",
            "",
            "## Security Findings",
            "",
        ]

        if not security_findings:
            lines.append(
                "No security findings were reported by the static "
                "analysis engine."
            )
        else:
            for finding in security_findings:
                lines.append(
                    f"- **[{finding.get('severity', 'INFO')}]** "
                    f"{finding.get('message', 'Issue detected')} "
                    f"(lines {finding.get('start_line')}"
                    f"-{finding.get('end_line')}, "
                    f"`{finding.get('check_id')}`)"
                )

        lines += [
            "",
            "## Recommended Next Steps",
            "",
            "1. Before applying any fix, identify the business purpose of the "
            "affected code and the trust boundary of the untrusted input.",
            "2. Remediate the highest-severity findings first.",
            "3. Validate and sanitise all external / user-controlled input.",
            "4. Avoid shell execution with untrusted data; prefer "
            "parameterised APIs.",
            "5. Infer any allow-list or timeout values from the existing "
            "codebase; do not invent example values.",
            "6. Add automated tests covering the corrected behaviour, "
            "derived from the actual fix implementation.",
        ]

        return "\n".join(lines)
