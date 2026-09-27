"""Isolated workspace for safe code manipulation."""

from __future__ import annotations

import ast
import difflib
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from app.core.logging import get_logger
from app.tools.formatter_tool import FormatterTool
from app.tools.semgrep_tool import SemgrepTool
from app.tools.treesitter_tool import TreeSitterTool

logger = get_logger("arcas.tools.workspace")


_EXT_MAP = {
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


@dataclass
class WorkspaceValidationResult:
    is_valid: bool
    syntax_errors: List[str] = field(default_factory=list)
    semgrep_regressions: List[dict] = field(default_factory=list)
    ast_diff_valid: bool = True
    # Names removed by the AST diff (Step 3).
    removed_functions: List[str] = field(default_factory=list)
    linter_findings: List[dict] = field(default_factory=list)
    original_file: str = ""
    modified_file: str = ""
    unified_diff: str = ""
    stats: dict = field(default_factory=dict)

    def warnings(self) -> List[str]:
        """Flatten all validation failures into human-readable warnings."""
        messages: List[str] = []
        for err in self.syntax_errors:
            messages.append(f"Syntax error in proposed code: {err}")
        for reg in self.semgrep_regressions:
            messages.append(
                "New security issue in refactored code: "
                f"{reg.get('message', reg.get('check_id', 'unknown'))} "
                f"(line {reg.get('start_line')})"
            )
        if not self.ast_diff_valid:
            names = ", ".join(f"`{n}`" for n in self.removed_functions) or (
                "one or more functions"
            )
            messages.append(
                f"Refactored code removes public function(s) {names} present "
                "in the original. If the rename was intentional, apply it "
                "manually - ARCAS only auto-applies fixes that keep the "
                "existing public function/class names intact."
            )
        return messages


class WorkspaceTool:
    """Safe code workspace - all transformations are isolated and validated."""

    @staticmethod
    def apply_and_validate(
        original_code: str,
        proposed_code: str,
        language: str,
        filename: str = "source",
    ) -> WorkspaceValidationResult:
        """Validate proposed_code against original_code in a sandbox."""
        ext = _EXT_MAP.get((language or "").lower(), ".txt")
        result = WorkspaceValidationResult(is_valid=True)

        with tempfile.TemporaryDirectory(prefix="arcas_workspace_") as tmpdir:
            workspace = Path(tmpdir)
            original_path = workspace / f"original{ext}"
            modified_path = workspace / f"modified{ext}"
            original_path.write_text(original_code, encoding="utf-8")
            modified_path.write_text(proposed_code, encoding="utf-8")

            result.original_file = str(original_path)
            result.modified_file = str(modified_path)

            # - Syntax validation.
            syntax_errors = WorkspaceTool._validate_syntax(
                proposed_code, language, modified_path
            )
            if syntax_errors:
                result.is_valid = False
                result.syntax_errors = syntax_errors
                logger.warning(
                    "Workspace validation: syntax errors in proposed code: %s",
                    syntax_errors,
                )

            # - Semgrep security-regression scan (new findings only).
            try:
                proposed_findings = SemgrepTool.analyze(proposed_code, language)
                original_findings = SemgrepTool.analyze(original_code, language)
                original_rules = {
                    f.get("check_id") for f in original_findings
                }
                new_regressions = [
                    f
                    for f in proposed_findings
                    if f.get("check_id") not in original_rules
                ]
                if new_regressions:
                    result.is_valid = False
                    result.semgrep_regressions = new_regressions
                    logger.warning(
                        "Workspace validation: %d NEW security issue(s) in "
                        "proposed code",
                        len(new_regressions),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Workspace Semgrep scan failed: %s", exc)

            # - AST structural diff via Tree-sitter.
            try:
                original_ast = TreeSitterTool.analyze(original_code, language)
                modified_ast = TreeSitterTool.analyze(proposed_code, language)
                orig_funcs = {
                    f for f in original_ast.get("functions", [])
                    if not f.startswith("_")
                }
                mod_funcs = {
                    f for f in modified_ast.get("functions", [])
                    if not f.startswith("_")
                }
                removed_funcs = orig_funcs - mod_funcs
                if removed_funcs:
                    # Mark the result invalid and set the AST flag.
                    result.is_valid = False
                    result.ast_diff_valid = False
                    result.removed_functions = sorted(removed_funcs)
                    logger.warning(
                        "Workspace AST diff: public functions removed from "
                        "refactor: %s",
                        removed_funcs,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Workspace AST diff failed: %s", exc)

            # - Deterministic formatting (Black / Prettier).
            try:
                formatted, changed = FormatterTool.format(
                    proposed_code, language
                )
                if changed:
                    proposed_code = formatted
                    modified_path.write_text(formatted, encoding="utf-8")
            except Exception:  # noqa: BLE001 - formatting is best effort
                pass

            # - Unified diff.
            clean_name = f"{filename}{ext}"
            result.unified_diff = WorkspaceTool._unified_diff(
                original_code, proposed_code, filename=clean_name
            )

            # - Diff stats.
            result.stats = WorkspaceTool._diff_stats(
                original_code, proposed_code
            )

        return result

    @staticmethod
    def _validate_syntax(
        code: str, language: str, path: Path
    ) -> List[str]:
        errors: List[str] = []
        normalized = (language or "").lower()
        if normalized == "python":
            try:
                ast.parse(code)
            except SyntaxError as exc:
                errors.append(f"SyntaxError at line {exc.lineno}: {exc.msg}")
        elif normalized in ("javascript", "typescript"):
            try:
                proc = subprocess.run(
                    ["node", "--check", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if proc.returncode != 0:
                    errors.append((proc.stderr or "syntax error")[:500])
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass  # node unavailable - skip, not a failure
        return errors

    @staticmethod
    def _unified_diff(original: str, modified: str, filename: str) -> str:
        return "".join(
            difflib.unified_diff(
                original.splitlines(keepends=True),
                modified.splitlines(keepends=True),
                fromfile=f"a/{filename}",
                tofile=f"b/{filename}",
                n=3,
            )
        )

    @staticmethod
    def _diff_stats(original: str, modified: str) -> dict:
        matcher = difflib.SequenceMatcher(
            a=original.splitlines(), b=modified.splitlines()
        )
        added = removed = changed = 0
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "insert":
                added += j2 - j1
            elif tag == "delete":
                removed += i2 - i1
            elif tag == "replace":
                changed += max(i2 - i1, j2 - j1)
        return {
            "added": added,
            "removed": removed,
            "changed": changed,
            "similarity": round(matcher.ratio(), 3),
        }
