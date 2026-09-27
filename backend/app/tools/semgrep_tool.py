import contextlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from app.core.logging import get_logger
from app.core.result_cache import ResultCache

logger = get_logger("arcas.tools.semgrep")


_EXTENSION_BY_LANGUAGE = {
    "python": ".py",
    "java": ".java",
    "javascript": ".js",
    "typescript": ".ts",
    "go": ".go",
    "ruby": ".rb",
    "php": ".php",
    "c": ".c",
    "cpp": ".cpp",
    "csharp": ".cs",
}


# Language-scoped Semgrep registry rulesets.
_CONFIG_BY_LANGUAGE = {
    "python": "p/python",
    "java": "p/java",
    "javascript": "p/javascript",
    "typescript": "p/typescript",
    "go": "p/golang",
    "ruby": "p/ruby",
    "php": "p/php",
    "c": "p/c",
    "cpp": "p/cpp",
    "csharp": "p/csharp",
}

_DEEP_SCAN_CONFIG = "p/security-audit"

# Bundled offline ruleset.
_LOCAL_RULES = (
    Path(__file__).parent.parent / "knowledge" / "semgrep_rules"
)

_registry_available: Optional[bool] = None

# Probe timeout.
_REGISTRY_PROBE_TIMEOUT = 15


def _registry_reachable() -> bool:
    global _registry_available
    if _registry_available is not None:
        return _registry_available

    if os.environ.get("ARCAS_SEMGREP_OFFLINE", "").lower() in ("1", "true", "yes"):
        _registry_available = False
        logger.info("Semgrep registry disabled by ARCAS_SEMGREP_OFFLINE.")
        return False

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", delete=False, encoding="utf-8"
        ) as probe:
            probe.write("x = 1\n")
            probe_path = probe.name
        result = subprocess.run(
            ["semgrep", "scan", "--config", "p/python", "--json",
             "--quiet", "--metrics=off", probe_path],
            capture_output=True, text=True, timeout=_REGISTRY_PROBE_TIMEOUT,
        )
        _registry_available = result.returncode in (0, 1)
    except Exception:  # noqa: BLE001
        _registry_available = False
    finally:
        with contextlib.suppress(OSError):
            os.unlink(probe_path)

    if _registry_available:
        logger.info("Semgrep registry reachable; using registry + local rules.")
    else:
        logger.warning(
            "Semgrep registry unreachable; scanning with the bundled offline "
            "ruleset only. Findings will be a subset of a networked scan."
        )
    return _registry_available


def warm_registry_probe() -> bool:
    """Resolve registry reachability ahead of the first real scan."""
    if shutil.which("semgrep") is None:
        return False
    return _registry_reachable()


def semgrep_status() -> dict:
    """Report scanner availability - surfaced on /health and in the benchmark."""
    return {
        "binary_available": shutil.which("semgrep") is not None,
        "registry_reachable": _registry_reachable()
        if shutil.which("semgrep")
        else False,
        "local_ruleset": str(_LOCAL_RULES),
        "local_rules_present": _LOCAL_RULES.exists(),
    }


def _first(value):
    """Semgrep metadata fields may be a scalar or a list."""
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _normalise_cwe(metadata: dict) -> Optional[str]:
    """Extract a bare CWE-nnn identifier from Semgrep rule metadata."""
    raw = _first(metadata.get("cwe"))
    if not raw:
        return None
    match = re.search(r"CWE-(\d+)", str(raw), re.IGNORECASE)
    return f"CWE-{int(match.group(1))}" if match else None


class SemgrepTool:
    """Semantic static-analysis security scanner (Semgrep)."""

    @staticmethod
    def _resolve_configs(language: str, deep_scan: bool) -> List[str]:
        """Choose rulesets, always including the offline set as a floor."""
        configs: List[str] = []
        if _LOCAL_RULES.exists():
            configs.append(str(_LOCAL_RULES))
        if _registry_reachable():
            configs.append(
                _DEEP_SCAN_CONFIG
                if deep_scan
                else _CONFIG_BY_LANGUAGE.get(language, _DEEP_SCAN_CONFIG)
            )
        return configs

    @staticmethod
    def analyze(code: str, language: str = "python", deep_scan: bool = False):
        normalized = (language or "python").lower()
        suffix = _EXTENSION_BY_LANGUAGE.get(normalized, ".py")

        configs = SemgrepTool._resolve_configs(normalized, deep_scan)
        if not configs:
            logger.warning("No Semgrep ruleset available; skipping scan.")
            return []
        config = ",".join(configs)

        cached = ResultCache.get_json(
            "semgrep", code, normalized, extra=config
        )
        if cached is not None:
            return cached

        with tempfile.NamedTemporaryFile(
            suffix=suffix,
            mode="w",
            encoding="utf-8",
            delete=False,
        ) as temp_file:
            temp_file.write(code)
            temp_file.flush()
            temp_file_path = temp_file.name

        try:
            result = subprocess.run(
                [
                    "semgrep",
                    "scan",
                    *[arg for cfg in configs for arg in ("--config", cfg)],
                    "--json",
                    "--no-git-ignore",
                    "--quiet",
                    "--metrics=off",
                    temp_file_path,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

            if result.returncode not in (0, 1):
                logger.error("Semgrep failed: %s", result.stderr)
                return []

            data = json.loads(result.stdout or "{}")

            findings = []
            for finding in data.get("results", []):
                extra = finding.get("extra", {})
                findings.append(
                    {
                        "check_id": finding.get("check_id"),
                        "message": extra.get("message"),
                        "severity": extra.get("severity"),
                        # Structured labels.
                        "cwe": _normalise_cwe(extra.get("metadata", {})),
                        "owasp": _first(extra.get("metadata", {}).get("owasp")),
                        "start_line": finding.get("start", {}).get("line"),
                        "end_line": finding.get("end", {}).get("line"),
                    }
                )

            logger.info(
                "Semgrep (%s) found %d finding(s) for %s",
                config,
                len(findings),
                normalized,
            )
            ResultCache.set_json(
                "semgrep", code, normalized, findings, extra=config
            )
            return findings

        except FileNotFoundError:
            logger.warning(
                "Semgrep binary not found on PATH; skipping "
                "static security analysis."
            )
            return []
        except json.JSONDecodeError as exc:
            logger.error("Could not parse Semgrep output: %s", exc)
            return []
        finally:
            try:
                Path(temp_file_path).unlink(missing_ok=True)
            except OSError:
                pass
