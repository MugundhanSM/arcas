"""Unified diff tool."""

import difflib
import re
from typing import List

from app.core.logging import get_logger

logger = get_logger("arcas.tools.diff")


class DiffTool:
    """Computes unified diffs between an original and a modified snippet."""

    @staticmethod
    def unified(
        original: str,
        modified: str,
        filename: str = "source",
        context: int = 3,
    ) -> str:
        original_lines = original.splitlines(keepends=True)
        modified_lines = modified.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            n=context,
        )
        return "".join(diff)

    @staticmethod
    def stats(original: str, modified: str) -> dict:
        """Return added/removed/changed line counts between two snippets."""
        original_lines = original.splitlines()
        modified_lines = modified.splitlines()

        matcher = difflib.SequenceMatcher(
            a=original_lines, b=modified_lines
        )

        added = 0
        removed = 0
        changed = 0
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

    _FULL_FILE_HEADING = re.compile(
        r"#+\s*COMPLETE\s+REFACTORED\s+FILE\b", re.IGNORECASE
    )
    _FENCED_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
    # An opening fence, optionally tagged with a language identifier, sitting on its own line.
    _FENCE_OPEN = re.compile(r"^\s*```([A-Za-z0-9_+-]*)\s*$")

    @staticmethod
    def extract_suggested_code(markdown: str) -> List[str]:
        """Pull every fenced code block out of an LLM markdown response."""
        return [
            block.strip()
            for block in DiffTool._FENCED_BLOCK.findall(markdown)
            if block.strip()
        ]

    @staticmethod
    def extract_refactored_file(markdown: str) -> str | None:
        heading = DiffTool._FULL_FILE_HEADING.search(markdown)
        if not heading:
            return None

        lines = markdown.splitlines()
        # Convert the heading's character offset into a line index.
        heading_line = markdown.count("\n", 0, heading.start())

        open_idx = None
        # Scan up to 30 lines past the heading for an opening fence.
        for offset in range(1, 31):
            idx = heading_line + offset
            if idx >= len(lines):
                break
            if DiffTool._FENCE_OPEN.match(lines[idx]):
                open_idx = idx
                break

        if open_idx is None:
            return None

        # Collect everything up to the closing fence.
        body: List[str] = []
        for idx in range(open_idx + 1, len(lines)):
            if lines[idx].strip().startswith("```"):
                break
            body.append(lines[idx])

        block = "\n".join(body).strip("\n")
        if not block.strip():
            return None

        logger.debug(
            "Extracted refactored file: %d lines", len(block.splitlines())
        )
        return block

    @staticmethod
    def is_plausible_full_file(
        original: str,
        candidate: str,
        min_ratio: float = 0.5,
        max_ratio: float = 5.0,
    ) -> bool:
        if not candidate.strip():
            return False

        original_count = len(
            [ln for ln in original.splitlines() if ln.strip()]
        )
        candidate_count = len(
            [ln for ln in candidate.splitlines() if ln.strip()]
        )

        if original_count == 0:
            return candidate_count > 0

        ratio = candidate_count / original_count
        return min_ratio <= ratio <= max_ratio
