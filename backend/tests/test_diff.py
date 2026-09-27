import pytest

from app.tools.diff_tool import DiffTool

ORIGINAL = """\
import subprocess


def run(cmd):
    return subprocess.call(cmd, shell=True)


def digest(value):
    import hashlib
    return hashlib.md5(value.encode()).hexdigest()
"""

FULL_REWRITE = """\
import subprocess
import hashlib


def run(cmd):
    # Avoid shell=True; pass an argument list instead.
    return subprocess.call(cmd)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()
"""


@pytest.mark.unit
def test_extract_refactored_file_returns_block_under_heading():
    markdown = (
        "# Recommendations\n\n"
        "Here is a small illustrative snippet:\n\n"
        "```python\nreturn hashlib.sha256(...)\n```\n\n"
        "## COMPLETE REFACTORED FILE\n\n"
        f"```python\n{FULL_REWRITE}```\n"
    )

    extracted = DiffTool.extract_refactored_file(markdown)

    assert extracted is not None
    assert "sha256" in extracted
    assert "def run(cmd):" in extracted


@pytest.mark.unit
def test_extract_refactored_file_returns_none_without_heading():
    markdown = (
        "# Recommendations\n\n"
        "Use sha256 instead of md5:\n\n"
        "```python\nreturn hashlib.sha256(value.encode()).hexdigest()\n```\n"
    )

    assert DiffTool.extract_refactored_file(markdown) is None


@pytest.mark.unit
def test_is_plausible_full_file_rejects_small_snippet():
    snippet = "return hashlib.sha256(value.encode()).hexdigest()"

    assert DiffTool.is_plausible_full_file(ORIGINAL, snippet) is False


@pytest.mark.unit
def test_is_plausible_full_file_accepts_full_rewrite():
    assert DiffTool.is_plausible_full_file(ORIGINAL, FULL_REWRITE) is True


@pytest.mark.unit
def test_snippet_only_response_yields_no_diff_candidate():
    markdown = (
        "# Recommendations\n\n"
        "1. Replace md5 with sha256:\n\n"
        "```python\nhashlib.sha256(value.encode())\n```\n\n"
        "2. Avoid shell=True:\n\n"
        "```python\nsubprocess.call(cmd)\n```\n"
    )

    candidate = DiffTool.extract_refactored_file(markdown)

    assert candidate is None


@pytest.mark.unit
def test_full_rewrite_produces_meaningful_diff():
    candidate = DiffTool.extract_refactored_file(
        "## COMPLETE REFACTORED FILE\n\n" f"```python\n{FULL_REWRITE}```\n"
    )
    assert candidate is not None
    assert DiffTool.is_plausible_full_file(ORIGINAL, candidate)

    diff = DiffTool.unified(ORIGINAL, candidate, filename="source.py")

    assert "-    return subprocess.call(cmd, shell=True)" in diff
    assert "+    return subprocess.call(cmd)" in diff
    assert "md5" in diff and "sha256" in diff
