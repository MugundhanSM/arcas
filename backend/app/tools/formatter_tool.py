"""Code formatter tool."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Tuple

from app.core.logging import get_logger

logger = get_logger("arcas.tools.formatter")

_EXT_MAP = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
}

_PRETTIER_PARSER = {
    "javascript": "babel",
    "typescript": "typescript",
}


class FormatterTool:
    """Deterministic code formatting via Black / Prettier."""

    @staticmethod
    def format(code: str, language: str) -> Tuple[str, bool]:
        """Return (formatted_code, was_changed)."""
        normalized = (language or "").lower()
        if normalized == "python":
            return FormatterTool._black(code)
        if normalized in ("javascript", "typescript"):
            return FormatterTool._prettier(code, normalized)
        return code, False

    @staticmethod
    def _black(code: str) -> Tuple[str, bool]:
        return FormatterTool._run(
            code,
            language="python",
            argv=["black", "--quiet"],
        )

    @staticmethod
    def _prettier(code: str, language: str) -> Tuple[str, bool]:
        parser = _PRETTIER_PARSER.get(language, "babel")
        return FormatterTool._run(
            code,
            language=language,
            argv=["prettier", "--write", "--parser", parser],
        )

    @staticmethod
    def _run(code: str, language: str, argv: list) -> Tuple[str, bool]:
        suffix = _EXT_MAP.get(language, ".txt")
        tmp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=suffix,
                mode="w",
                encoding="utf-8",
                delete=False,
            ) as handle:
                handle.write(code)
                handle.flush()
                tmp_path = Path(handle.name)

            result = subprocess.run(
                [*argv, str(tmp_path)],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode != 0:
                logger.debug(
                    "%s formatter exited %d: %s",
                    argv[0],
                    result.returncode,
                    (result.stderr or "")[:200],
                )
                return code, False

            formatted = tmp_path.read_text(encoding="utf-8")
            return formatted, formatted != code

        except FileNotFoundError:
            logger.info(
                "Formatter '%s' not installed; skipping formatting.", argv[0]
            )
            return code, False
        except subprocess.TimeoutExpired:
            logger.warning("Formatter '%s' timed out.", argv[0])
            return code, False
        except OSError as exc:  # noqa: BLE001
            logger.debug("Formatter '%s' failed: %s", argv[0], exc)
            return code, False
        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass
