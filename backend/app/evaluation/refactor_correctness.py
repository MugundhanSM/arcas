"""Refactoring correctness."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger("arcas.evaluation.refactor_correctness")

_MODULE_NAME = "subject"
_DEFAULT_TIMEOUT = 60


@dataclass
class TestOutcome:
    """Result of one test across both versions."""

    test_id: str
    passed_before: bool
    passed_after: bool

    @property
    def classification(self) -> str:
        if self.passed_before and self.passed_after:
            return "preserved"
        if self.passed_before and not self.passed_after:
            return "regression"
        if not self.passed_before and self.passed_after:
            return "repaired"
        return "still_failing"


@dataclass
class CorrectnessResult:
    ran: bool
    correctness: float = 0.0
    outcomes: List[TestOutcome] = field(default_factory=list)
    skip_reason: str = ""
    error: str = ""

    @property
    def counts(self) -> Dict[str, int]:
        buckets = {
            "preserved": 0,
            "regression": 0,
            "repaired": 0,
            "still_failing": 0,
        }
        for outcome in self.outcomes:
            buckets[outcome.classification] += 1
        return buckets

    def as_dict(self) -> dict:
        counts = self.counts
        return {
            "ran": self.ran,
            "skip_reason": self.skip_reason or None,
            "error": self.error or None,
            "correctness": round(self.correctness, 3),
            "tests_total": len(self.outcomes),
            **counts,
            "regressions": [
                o.test_id for o in self.outcomes
                if o.classification == "regression"
            ],
            "repaired_tests": [
                o.test_id for o in self.outcomes
                if o.classification == "repaired"
            ],
        }


def _strip_markdown(text: str) -> str:
    """Extract Python from a fenced block, or return the text unchanged."""
    blocks = re.findall(r"```(?:python|py)?\n(.*?)```", text or "", re.DOTALL)
    if blocks:
        return max(blocks, key=len)
    return text or ""


def _rewrite_imports(test_code: str) -> str:
    code = re.sub(
        r"^\s*from\s+[\w.]+\s+import\s+",
        f"from {_MODULE_NAME} import ",
        test_code,
        flags=re.MULTILINE,
    )
    code = re.sub(
        r"^\s*import\s+(?!pytest|unittest|sys|os|re|json|math|typing)[\w.]+\s*$",
        f"import {_MODULE_NAME}",
        code,
        flags=re.MULTILINE,
    )
    return code


def _run_pytest(
    implementation: str,
    test_code: str,
    timeout: int,
) -> Optional[Dict[str, bool]]:
    with tempfile.TemporaryDirectory(prefix="arcas-correctness-") as tmp:
        root = Path(tmp)
        (root / f"{_MODULE_NAME}.py").write_text(implementation, encoding="utf-8")
        (root / "test_subject.py").write_text(test_code, encoding="utf-8")
        report_path = root / "report.json"

        # Network-free, proxy-free, no site-packages writes.
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(root),
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(root),
            "no_proxy": "*",
            "NO_PROXY": "*",
        }

        try:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "test_subject.py",
                    "-q",
                    "--no-header",
                    "-p",
                    "no:cacheprovider",
                    f"--report-log={report_path}",
                ],
                cwd=root,
                env=env,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            logger.warning("Correctness run timed out after %ss.", timeout)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Correctness run failed to start: %s", exc)
            return None

        if not report_path.exists():
            # pytest-reportlog absent - fall back to parsing terminal output.
            return _parse_terminal_fallback(root, env, timeout)

        results: Dict[str, bool] = {}
        for line in report_path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("$report_type") != "TestReport":
                continue
            if record.get("when") != "call":
                # Setup errors mean the test never ran; record as failed.
                if record.get("when") == "setup" and record.get("outcome") == "error":
                    results.setdefault(record.get("nodeid", "?"), False)
                continue
            results[record.get("nodeid", "?")] = record.get("outcome") == "passed"
        return results or None


def _parse_terminal_fallback(
    root: Path, env: dict, timeout: int
) -> Optional[Dict[str, bool]]:
    """Per-test results without pytest-reportlog, via -v output parsing."""
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "test_subject.py",
                "-v",
                "--no-header",
                "-p",
                "no:cacheprovider",
            ],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return None

    results: Dict[str, bool] = {}
    for line in completed.stdout.splitlines():
        match = re.match(r"^(test_subject\.py::\S+)\s+(PASSED|FAILED|ERROR)", line)
        if match:
            results[match.group(1)] = match.group(2) == "PASSED"
    return results or None


def measure_refactoring_correctness(
    original_code: str,
    refactored_code: str,
    test_code: str,
    language: str = "python",
    timeout: int = _DEFAULT_TIMEOUT,
) -> CorrectnessResult:
    """Differentially test original_code against refactored_code."""
    if language.lower() not in ("python", "py"):
        return CorrectnessResult(
            ran=False,
            skip_reason=(
                f"Differential test execution is implemented for Python only; "
                f"'{language}' was skipped."
            ),
        )

    if not refactored_code or not refactored_code.strip():
        return CorrectnessResult(
            ran=False, skip_reason="No refactored code was produced."
        )

    tests = _rewrite_imports(_strip_markdown(test_code))
    if "def test" not in tests:
        return CorrectnessResult(
            ran=False, skip_reason="No executable test functions were found."
        )

    before = _run_pytest(original_code, tests, timeout)
    if before is None:
        return CorrectnessResult(
            ran=False,
            skip_reason="The suite could not be collected against the original code.",
        )

    after = _run_pytest(refactored_code, tests, timeout)
    if after is None:
        return CorrectnessResult(
            ran=True,
            correctness=0.0,
            outcomes=[
                TestOutcome(test_id=tid, passed_before=passed, passed_after=False)
                for tid, passed in before.items()
            ],
            error="The refactored code could not be imported or collected.",
        )

    outcomes = [
        TestOutcome(
            test_id=test_id,
            passed_before=passed,
            passed_after=after.get(test_id, False),
        )
        for test_id, passed in before.items()
    ]

    counts = {"preserved": 0, "regression": 0}
    for outcome in outcomes:
        classification = outcome.classification
        if classification in counts:
            counts[classification] += 1

    denominator = counts["preserved"] + counts["regression"]
    correctness = counts["preserved"] / denominator if denominator else 1.0

    result = CorrectnessResult(ran=True, correctness=correctness, outcomes=outcomes)
    logger.info(
        "Refactoring correctness %.2f (%s)", correctness, result.counts
    )
    return result
