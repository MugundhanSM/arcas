import json
import os
import re
import subprocess
import sys
import tempfile

from app.agents.signature_introspector import (
    build_call_arguments,
    describe_signatures,
    generate_smoke_tests,
)
from app.core.logging import get_logger
from app.core.result_cache import ResultCache
from app.tools.llm_tool import LLMNotConfiguredError

logger = get_logger("arcas.agents.tests")


_SYSTEM_PROMPT = (
    "You are ARCAS Test Generation Agent. You write enterprise-grade test "
    "suites that BLOCK attacks, not document them, and that prove legitimate "
    "behaviour still works after the fix. For every security finding, write "
    "MULTIPLE attack-payload variants (not just one) and assert each is "
    "rejected. Never write assert True. Always import, never copy "
    "implementations. IMPORTANT: always name the module being imported "
    "'module_under_test' so the test runner can locate it automatically."
)


_BAD_TEST_PATTERNS = [
    (
        r"assert\s+result\s*==\s*0",
        "Test asserts dangerous call returned success (exit code 0) - may "
        "document the vulnerability instead of testing the fix",
    ),
    (
        r"assert\s+\w+\s*is\s+not\s+None.*#.*injection",
        "Potential anti-pattern: assertion may confirm injection worked",
    ),
    (
        r"subprocess\.call.*assert.*==\s*0",
        "Test may verify shell injection succeeds",
    ),
]


def _validate_tests(
    tests_markdown: str, security_findings: list
) -> tuple[str, list]:
    warnings: list[str] = []
    for pattern, message in _BAD_TEST_PATTERNS:
        if re.search(pattern, tests_markdown, re.IGNORECASE):
            warnings.append(f"⚠ Test quality warning: {message}")

    if warnings:
        warning_block = "\n\n> **Test Validation Warnings**\n" + "\n".join(
            f"> {w}" for w in warnings
        )
        tests_markdown = warning_block + "\n\n" + tests_markdown

    return tests_markdown, warnings


_FRAMEWORK = {
    "python": "pytest",
    "java": "JUnit 5",
    "javascript": "Jest",
    "typescript": "Jest",
    "go": "the standard testing package",
    "ruby": "RSpec",
    "php": "PHPUnit",
    "csharp": "xUnit",
    "c": "Unity",
    "cpp": "GoogleTest",
}


def _extract_code_block(markdown: str) -> str:
    python_blocks = re.findall(
        r"```python\s*\n(.*?)```", markdown, re.DOTALL | re.IGNORECASE
    )
    candidates = python_blocks or re.findall(
        r"```\s*\n(.*?)```", markdown, re.DOTALL
    )
    if not candidates:
        return ""

    def _score(block: str) -> tuple[int, int]:
        looks_like_test = bool(
            re.search(r"\bdef\s+test|class\s+Test|^\s*(?:import|from)\s",
                      block, re.MULTILINE)
        )
        return (1 if looks_like_test else 0, len(block))

    return max(candidates, key=_score).strip()


# Stdlib / always-available modules the executor is happy to import.
_SAFE_IMPORTS = frozenset({
    "os", "sys", "re", "json", "math", "time", "datetime", "random",
    "pathlib", "typing", "collections", "itertools", "functools",
    "contextlib", "unittest", "io", "abc", "enum", "dataclasses",
    "subprocess", "shutil", "tempfile", "string", "decimal", "fractions",
    "hashlib", "hmac", "base64", "secrets", "uuid", "copy", "types",
    "module_under_test", "pytest",
})


def _describe_dummy_inputs(sigs) -> str:
    if not sigs:
        return "(no introspectable signatures - snippet may be a fragment)"
    lines = []
    for s in sigs:
        args, _ = build_call_arguments(s)
        recv = f"{s.class_name}()." if (s.class_name and not s.is_static) else ""
        lines.append(f"- {recv}{s.name}({args})")
    return "\n".join(lines)


class TestGenerationAgent:

    @staticmethod
    def analyze(
        source_code: str,
        language: str,
        review_findings: dict,
        security_findings: list,
        refactored_code: str = "",
        intent: str = "full_review",
    ) -> str:
        cache_extra = f"{intent}:{refactored_code}"
        cached = ResultCache.get_text(
            "test_generation", source_code, language, extra=cache_extra
        )
        if cached is not None:
            return cached

        framework = _FRAMEWORK.get(language, "an idiomatic test framework")

        # The code the tests actually run against - the fix if we have one.
        target_code = refactored_code or source_code

        # Deterministic signature context (Python)
        signature_summary = ""
        dummy_summary = ""
        if language == "python":
            sigs = generate_smoke_tests(target_code)[1]
            if sigs:
                signature_summary = describe_signatures(sigs)
                dummy_summary = _describe_dummy_inputs(sigs)

        if refactored_code:
            refactored_block = f"""
==================================================
REFACTORED CODE - THE ACTUAL IMPLEMENTED FIX
==================================================

This is the code that will actually run. Generate tests against THIS
implementation. IMPORTANT: import everything from 'module_under_test'
(this is the filename the test runner will use).

{refactored_code}
"""
        else:
            refactored_block = """
==================================================
REFACTORED CODE
==================================================

Not available for this run - generate tests against SOURCE CODE and
SECURITY FINDINGS only. IMPORTANT: import everything from 'module_under_test'.
"""

        signature_block = ""
        if signature_summary:
            signature_block = f"""
==================================================
EXTRACTED SIGNATURES (ground truth - import & call EXACTLY these)
==================================================

{signature_summary}

Structurally-valid example calls with dummy inputs of the expected shape
(use these as the basis for your NORMAL-case tests so every test is runnable):
{dummy_summary}
"""

        prompt = f"""
You are a senior test engineer. Your job is to write correct, meaningful unit
tests for the {language} code shown below using {framework}.

CRITICAL IMPORT RULE: You MUST import from 'module_under_test' (exactly that
name). The test runner saves the source code as 'module_under_test.py'.

==================================================
SOURCE CODE ({language}) - ORIGINAL, BEFORE THE FIX
==================================================

{source_code}

==================================================
DETECTED STRUCTURE
==================================================

{json.dumps(review_findings, indent=2)}
{signature_block}
==================================================
SECURITY FINDINGS (write regression tests that BLOCK these)
==================================================

{json.dumps(security_findings, indent=2)}
{refactored_block}
==================================================
TASK
==================================================

Return clean markdown with:
1. A short paragraph (2-3 sentences) describing the test strategy.
2. A single fenced code block containing the complete, runnable test file.
3. A bullet list of additional edge-case tests worth adding later.

==================================================
RULES - FOLLOW EXACTLY
==================================================

RULE 1 - IMPORT FROM 'module_under_test':
    from module_under_test import run   # CORRECT - exactly this module name

RULE 2 - MATCH THE REAL SIGNATURES ABOVE. Call every function with the exact
parameters it declares. Use the dummy-input examples as your happy-path inputs
so each normal-case test actually executes.

RULE 3 - SECURITY REGRESSION TESTS ASSERT ATTACKS ARE NEUTRALISED:
Write PARAMETRIZED tests covering AT LEAST 2-3 attack-payload variants per
finding. "Blocked" has TWO forms - assert whichever one the ACTUAL FIX uses:
  (a) REJECTED: the fix raises/returns an error for the payload. Assert the
      exception.
  (b) NEUTRALISED: the fix lets the call proceed but strips the payload of its
      power (e.g. shell=False + shlex makes `a; rm -rf /` a literal argument, so
      no second command runs). Do NOT assert an exception here - there is none.
      Assert the payload was rendered inert: the parsed argument vector contains
      the metacharacters as literal data, and the dangerous command never
      executes.
Read the REFACTORED CODE and decide which case applies BEFORE writing the
assertion. Asserting a raise for a neutralising fix (or vice-versa) is a bug.

RULE 4 - NO assert True PLACEHOLDERS, AND DO NOT MOCK AWAY WHAT YOU TEST:
A security test that patches out `subprocess.run` and then only checks
`shell=False` proves NOTHING about whether injection executes - it tests the
mock. Prefer asserting on the real parsed argument vector, and include at least
ONE end-to-end test that runs a genuinely safe command for real (e.g. `echo`)
and checks the injected portion did not execute (no extra file created, output
is the literal string). Mock only to avoid genuinely unsafe or slow side
effects, never to manufacture a green result.

RULE 5 - ATTACK THE CONTROL ITSELF, NOT JUST PAYLOADS:
If the fix adds an allow-list or similar control, test the control's own
weaknesses: its UNCONFIGURED/empty state (it MUST fail closed - assert that an
empty allow-list denies, never allows), basename-vs-path bypasses
(`/bin/echo` vs `echo`), and the catastrophic case of allow-listing an
interpreter (`bash -c`, `python -c`). These are the tests that find real holes.

RULE 6 - YOUR TESTS WILL BE EXECUTED AGAINST THE FIX.
Every test you write is run against the REFACTORED CODE above and a failure is
reported as a fix/test disagreement you own. Before finalising, mentally execute
each test against that code: does the empty allow-list actually raise, or run?
does that payload actually raise, or get neutralised? Make the assertion match
the real behaviour. Do not assert intended behaviour the code does not implement.

RULE 7 - NO assert True PLACEHOLDERS.

RULE 8 - TEST GROUPS:
  class TestNormalCases:
  class TestEdgeCases:
  class TestSecurityRegressions:
"""

        try:
            # ReAct loop.
            raw = TestGenerationAgent._react(
                prompt=prompt,
                target_code=target_code,
                language=language,
                security_findings=security_findings,
            )
            tests_markdown, _ = _validate_tests(raw, security_findings)
            result = tests_markdown
        except LLMNotConfiguredError:
            result = _scaffold_fallback(
                language, security_findings, framework, target_code
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Test generation LLM call failed: %s", exc)
            result = _scaffold_fallback(
                language, security_findings, framework, target_code
            )

        ResultCache.set_text(
            "test_generation", source_code, language, result, extra=cache_extra
        )
        return result

    # ReAct reasoning
    @staticmethod
    def _react(
        prompt: str,
        target_code: str,
        language: str,
        security_findings: list,
    ) -> str:
        from app.core.react_agent import ReActAgent
        from app.tools.retriever_tool import RetrieverTool

        def read_signatures(_arg: str) -> str:
            if language != "python":
                return f"Signature extraction is Python-only; got '{language}'."
            try:
                sigs = generate_smoke_tests(target_code)[1]
                return describe_signatures(sigs) if sigs else "No callables found."
            except Exception as exc:  # noqa: BLE001
                return f"Signature extraction unavailable: {exc}"

        def run_candidate_tests(candidate: str) -> str:
            if language != "python":
                return f"Sandbox execution is Python-only; got '{language}'."
            if not candidate or "def test" not in candidate:
                return (
                    "No test functions found in the candidate. Pass the full "
                    "test source to this tool."
                )
            try:
                outcome = TestGenerationAgent.execute_tests(
                    source_code=target_code,
                    generated_tests_markdown=candidate,
                    language=language,
                    refactored_code=target_code,
                )
                return json.dumps(
                    {
                        key: outcome.get(key)
                        for key in ("summary", "passed", "failed", "errors")
                        if key in outcome
                    },
                    default=str,
                )[:1500]
            except Exception as exc:  # noqa: BLE001
                return f"Sandbox execution failed: {exc}"

        def knowledge_base(query: str) -> str:
            return RetrieverTool.get_context(language=language, query=query)[:1000]

        agent = ReActAgent(
            system_prompt=_SYSTEM_PROMPT,
            tools={
                "read_signatures": read_signatures,
                "run_candidate_tests": run_candidate_tests,
                "knowledge_base": knowledge_base,
            },
            max_iterations=5,
        )
        answer, _trace = agent.run(prompt)
        return answer

    # Execution + self-verification
    @staticmethod
    def execute_tests(
        source_code: str,
        generated_tests_markdown: str,
        language: str = "python",
        timeout: int = 45,
        refactored_code: str = "",
    ) -> dict:
        if language != "python":
            return {
                "ran": False,
                "reason": f"Automatic test execution is not yet supported for "
                          f"{language}. Copy the generated test file and run it "
                          f"locally.",
            }

        module_code = refactored_code.strip() or source_code
        against_fix = bool(refactored_code.strip())

        llm_test_code = _extract_code_block(generated_tests_markdown)
        smoke_code, sigs = generate_smoke_tests(module_code)

        if not llm_test_code and not smoke_code:
            return {
                "ran": False,
                "reason": "Could not extract a runnable code block and no "
                          "introspectable signatures were found.",
            }

        import importlib.util
        if importlib.util.find_spec("pytest") is None:
            return {
                "ran": False,
                "reason": "pytest is not installed in the runtime environment, "
                          "so tests could not be executed automatically. The "
                          "generated tests above are still valid - run them "
                          "locally with `pytest`.",
            }

        try:
            with tempfile.TemporaryDirectory(prefix="arcas_tests_") as tmpdir:
                self = TestGenerationAgent
                self._write_module(tmpdir, module_code)

                # Report (do not install) any non-stdlib imports.
                third_party = self._third_party_imports(llm_test_code)

                # Combined run: LLM tests + smoke tests.
                wrote_llm = False
                if llm_test_code:
                    self._write(tmpdir, "test_generated.py", llm_test_code)
                    wrote_llm = True
                already_smoke = "Auto-generated structural smoke tests (ARCAS)" in llm_test_code
                if smoke_code and not already_smoke:
                    self._write(tmpdir, "test_smoke_structural.py", smoke_code)

                result = self._run_pytest(tmpdir, timeout)

                healed = False
                smoke_only = False
                consistency = None  # "verified" | "mismatch" | None
                smoke_baseline_passed = None

                # Collection failure (exit 2/3/4) usually means the LLM test file doesn't import cleanly.
                collection_failed = result.returncode in (2, 3, 4) or (
                    "ERROR" in result.stdout and "collected 0 items" in result.stdout
                )
                if wrote_llm and smoke_code and collection_failed:
                    logger.info(
                        "LLM tests failed to collect - self-healing with smoke suite."
                    )
                    os.remove(os.path.join(tmpdir, "test_generated.py"))
                    result = self._run_pytest(tmpdir, timeout)
                    healed = True
                    smoke_only = True

                elif wrote_llm and against_fix:
                    consistency = "verified" if result.returncode == 0 else "mismatch"
                    if consistency == "mismatch" and smoke_code:
                        llm_path = os.path.join(tmpdir, "test_generated.py")
                        if os.path.exists(llm_path):
                            os.remove(llm_path)
                            smoke_result = self._run_pytest(tmpdir, timeout)
                            smoke_baseline_passed = smoke_result.returncode == 0
                        logger.info(
                            "Self-consistency mismatch: generated tests fail against "
                            "the generated fix (smoke baseline passed=%s).",
                            smoke_baseline_passed,
                        )

                return {
                    "ran": True,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "passed": result.returncode == 0,
                    "healed": healed,
                    "smoke_only": smoke_only,
                    "smoke_count": len(sigs),
                    "third_party_imports": third_party,
                    "against_fix": against_fix,
                    "consistency": consistency,
                    "smoke_baseline_passed": smoke_baseline_passed,
                }

        except subprocess.TimeoutExpired:
            return {"ran": False, "reason": f"Test execution timed out ({timeout}s limit)."}
        except Exception as exc:  # noqa: BLE001
            logger.warning("Test execution failed: %s", exc)
            return {"ran": False, "reason": str(exc)}

    # execution helpers
    @staticmethod
    def _write(tmpdir: str, name: str, content: str) -> None:
        with open(os.path.join(tmpdir, name), "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def _write_module(tmpdir: str, code: str) -> None:
        TestGenerationAgent._write(tmpdir, "module_under_test.py", code)

    @staticmethod
    def _third_party_imports(test_code: str) -> list[str]:
        if not test_code:
            return []
        imports = re.findall(r"^(?:import|from)\s+(\w+)", test_code, re.MULTILINE)
        return sorted({
            pkg for pkg in imports
            if pkg not in _SAFE_IMPORTS and not pkg.startswith("_")
        })

    @staticmethod
    def _run_pytest(tmpdir: str, timeout: int) -> subprocess.CompletedProcess:
        # A minimal, network-free environment.
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": tmpdir,
            "HOME": tmpdir,
            "NO_PROXY": "*",
            "PYTHONHASHSEED": "0",  # <- the actual crash fix
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "LC_ALL": "C.UTF-8",
            "LANG": "C.UTF-8",
        }
        # Preserve start-up-critical / temp vars when present (harmless when not).
        for _key in ("SYSTEMROOT", "TEMP", "TMP", "TMPDIR"):
            _val = os.environ.get(_key)
            if _val:
                env[_key] = _val
        return subprocess.run(
            [sys.executable, "-m", "pytest", tmpdir, "-v", "--tb=short",
             "--no-header", "-p", "no:cacheprovider", "-rN"],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=tmpdir,
            env=env,
        )

    # Rendering
    @staticmethod
    def append_execution_result(
        tests_markdown: str, execution_result: dict
    ) -> str:
        if not execution_result.get("ran"):
            reason = execution_result.get("reason", "Unknown error")
            return (
                tests_markdown
                + f"\n\n---\n\n## ⚡ Test Execution\n\n"
                  f"> ℹ️ Automatic execution skipped: {reason}\n"
            )

        passed = execution_result.get("passed", False)
        returncode = execution_result.get("returncode", -1)
        stdout = (execution_result.get("stdout") or "").strip()
        stderr = (execution_result.get("stderr") or "").strip()
        healed = execution_result.get("healed", False)
        smoke_only = execution_result.get("smoke_only", False)
        smoke_count = execution_result.get("smoke_count", 0)
        third_party = execution_result.get("third_party_imports", [])
        against_fix = execution_result.get("against_fix", False)
        consistency = execution_result.get("consistency")
        smoke_baseline_passed = execution_result.get("smoke_baseline_passed")

        if consistency == "mismatch":
            status_icon = "⚠️"
            status_label = "Self-consistency check FAILED"
        elif consistency == "verified":
            status_icon = "✅"
            status_label = "Self-consistency verified"
        else:
            status_icon = "✅" if passed else "❌"
            status_label = (
                "All tests passed" if passed
                else f"Tests failed (exit {returncode})"
            )

        notes = []
        if consistency == "verified":
            notes.append(
                "The AI-generated tests were executed **against the AI-generated "
                "fix** and all passed - the fix, its tests, and its documented "
                "behaviour agree."
            )
        elif consistency == "mismatch":
            notes.append(
                "> ⚠️ The AI-generated tests were executed **against the "
                "AI-generated fix** and did **not** all pass. This means the "
                "fix, its docstring, or its tests describe different behaviour "
                "(a common cause: a security control whose default or edge-case "
                "handling differs from what the tests assert). **Review both "
                "before trusting either** - do not assume the fix is correct "
                "just because it was generated. See the failing cases below."
            )
            if smoke_baseline_passed is True:
                notes.append(
                    "> ✅ The deterministic structural smoke baseline still "
                    "passes, so the fix is at least structurally sound (every "
                    "callable is reachable with inputs of the expected shape); "
                    "the disagreement is in the behavioural assertions."
                )
            elif smoke_baseline_passed is False:
                notes.append(
                    "> ❌ The structural smoke baseline also fails against the "
                    "fix - the fix may not be structurally sound. Treat this "
                    "refactor as unverified."
                )

        if smoke_count:
            notes.append(
                f"Synthesised {smoke_count} structural smoke test(s) from the "
                f"real function signatures and verified each callable runs with "
                f"dummy input of the expected shape."
            )
        if healed:
            notes.append(
                "> ⚠️ The AI-authored tests did not import cleanly, so ARCAS "
                "self-healed and re-ran the guaranteed-valid smoke suite alone. "
                "Review the AI tests above before relying on them."
            )
        if smoke_only:
            notes.append("> ℹ️ Results below reflect the structural smoke suite only.")
        if third_party:
            notes.append(
                "> 🔒 The AI tests referenced third-party package(s) "
                f"`{', '.join(third_party)}` which ARCAS does **not** auto-install "
                "for supply-chain safety. Install them locally to run those cases."
            )

        notes_block = ("\n\n" + "\n\n".join(notes)) if notes else ""

        output_section = ""
        if stdout:
            output_section += f"\n\n**pytest output:**\n```\n{stdout[:3000]}\n```"
        if stderr and not passed:
            output_section += f"\n\n**stderr:**\n```\n{stderr[:1000]}\n```"

        return (
            tests_markdown
            + f"\n\n---\n\n## ⚡ Test Execution Results\n\n"
              f"{status_icon} **{status_label}**"
              f"{notes_block}"
              f"{output_section}\n"
        )


def _scaffold_fallback(
    language: str, security_findings: list, framework: str, target_code: str = ""
) -> str:
    findings_list = "\n".join(
        f"    # TODO: write regression test for: {f.get('title', 'finding')}"
        for f in security_findings[:5]
    )
    if not findings_list:
        findings_list = "    # TODO: add security regression tests"

    if language == "python":
        smoke_code, sigs = generate_smoke_tests(target_code)
        if smoke_code:
            sig_desc = describe_signatures(sigs)
            return f"""## Test Strategy

The LLM gateway was unavailable, so ARCAS generated a **deterministic structural
test suite** directly from the source. Every public callable below is invoked
with dummy input shaped to match its real signature and asserted to be callable.
These run and pass as-is; extend them with the behavioural cases noted afterwards.

**Signatures under test:**
```
{sig_desc}
```

```python
{smoke_code}

# ----------------------------------------------------------------------------
# TODO - behavioural & security-regression tests to add on top of the smoke suite
# ----------------------------------------------------------------------------
class TestSecurityRegressions:
{findings_list}
    pass
```

## Additional tests to consider

- Null / empty inputs
- Extremely long inputs (buffer limits)
- Unicode and special characters
- Concurrent / repeated invocation
"""
        # No introspectable signatures - minimal honest scaffold.
        return f"""## Test Strategy

Import functions from `module_under_test` and assert that security findings
are blocked, not documented. (No introspectable signatures were found, so no
structural smoke tests could be synthesised.)

```python
import pytest
from module_under_test import *  # noqa: F401,F403


class TestSecurityRegressions:
{findings_list}
    pass
```
"""
    return (
        f"## Test Strategy\n\nWrite {framework} tests covering the detected "
        f"security findings.\n"
    )
