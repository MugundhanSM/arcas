"""Static linter tool."""

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List

from app.core.logging import get_logger
from app.core.result_cache import ResultCache

logger = get_logger("arcas.tools.linter")


_EXTENSION_BY_LANGUAGE = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
}


class LinterTool:
    """Optional style/quality linting with a deterministic fallback."""

    @staticmethod
    def analyze(code: str, language: str = "python") -> List[Dict]:
        language = (language or "python").lower()

        cached = ResultCache.get_json("linter", code, language)
        if cached is not None:
            return cached

        if language == "python":
            findings = LinterTool._run_pylint(code)
            if findings is None:
                findings = LinterTool._heuristic(code, language)
        elif language in ("javascript", "typescript"):
            findings = LinterTool._run_eslint(code, language)
            if findings is None:
                findings = LinterTool._heuristic(code, language)
        else:
            findings = LinterTool._heuristic(code, language)

        ResultCache.set_json("linter", code, language, findings)
        return findings

    # External linters

    @staticmethod
    def _run_pylint(code: str):
        path = LinterTool._write_temp(code, ".py")
        try:
            result = subprocess.run(
                ["pylint", "--output-format=json", "--score=n", path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            data = json.loads(result.stdout or "[]")
            return [
                {
                    "line": item.get("line"),
                    "symbol": item.get("symbol"),
                    "message": item.get("message"),
                    "severity": item.get("type"),
                }
                for item in data
            ]
        except FileNotFoundError:
            logger.info("pylint not installed; using heuristic linting.")
            return None
        except (json.JSONDecodeError, OSError) as exc:  # noqa: BLE001
            logger.warning("pylint run failed: %s", exc)
            return None
        finally:
            LinterTool._cleanup(path)

    @staticmethod
    def _run_eslint(code: str, language: str):
        suffix = _EXTENSION_BY_LANGUAGE.get(language, ".js")
        path = LinterTool._write_temp(code, suffix)
        try:
            result = subprocess.run(
                ["eslint", "--format", "json", "--no-eslintrc", path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            data = json.loads(result.stdout or "[]")
            findings = []
            for file_report in data:
                for msg in file_report.get("messages", []):
                    findings.append(
                        {
                            "line": msg.get("line"),
                            "symbol": msg.get("ruleId"),
                            "message": msg.get("message"),
                            "severity": (
                                "error"
                                if msg.get("severity") == 2
                                else "warning"
                            ),
                        }
                    )
            return findings
        except FileNotFoundError:
            logger.info("eslint not installed; using heuristic linting.")
            return None
        except (json.JSONDecodeError, OSError) as exc:  # noqa: BLE001
            logger.warning("eslint run failed: %s", exc)
            return None
        finally:
            LinterTool._cleanup(path)

    # Deterministic fallback heuristics

    @staticmethod
    def _heuristic(code: str, language: str) -> List[Dict]:
        findings: List[Dict] = []
        for idx, line in enumerate(code.splitlines(), start=1):
            stripped = line.rstrip("\n")
            if len(stripped) > 100:
                findings.append(
                    {
                        "line": idx,
                        "symbol": "line-too-long",
                        "message": (
                            f"Line exceeds 100 characters "
                            f"({len(stripped)})."
                        ),
                        "severity": "convention",
                    }
                )
            if stripped != stripped.rstrip():
                findings.append(
                    {
                        "line": idx,
                        "symbol": "trailing-whitespace",
                        "message": "Trailing whitespace.",
                        "severity": "convention",
                    }
                )
            lowered = stripped.lower()
            if "todo" in lowered or "fixme" in lowered:
                findings.append(
                    {
                        "line": idx,
                        "symbol": "fixme",
                        "message": "Unresolved TODO/FIXME marker.",
                        "severity": "warning",
                    }
                )
            if "\t" in line:
                findings.append(
                    {
                        "line": idx,
                        "symbol": "mixed-indentation",
                        "message": "Tab character used for indentation.",
                        "severity": "convention",
                    }
                )
        return findings

    # Helpers

    @staticmethod
    def _write_temp(code: str, suffix: str) -> str:
        with tempfile.NamedTemporaryFile(
            suffix=suffix, mode="w", encoding="utf-8", delete=False
        ) as fh:
            fh.write(code)
            fh.flush()
            return fh.name

    @staticmethod
    def _cleanup(path: str) -> None:
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
