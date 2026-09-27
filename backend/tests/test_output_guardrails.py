import pytest

from app.core.output_guardrails import OutputGuardrails

pytestmark = pytest.mark.unit


def _check(text, source="def f():\n    return 1\n", findings=None):
    return OutputGuardrails.check(
        generated_text=text,
        source_code=source,
        review_findings=findings or {"functions": ["f"], "classes": []},
    )


def test_empty_generation_fails_with_zero_confidence():
    result = _check("")
    assert result.passed is False
    assert result.confidence == 0.0


def test_clean_suggestion_passes_with_high_confidence():
    text = (
        "Consider extracting a helper.\n\n"
        "```python\n"
        "def f():\n"
        "    return 1\n"
        "```\n"
    )
    result = _check(text)
    assert result.passed is True
    assert result.confidence >= 0.8
    assert result.security_regressions == []


def test_security_regression_is_flagged_and_lowers_confidence():
    text = (
        "Here is the fix:\n\n"
        "```python\n"
        "import subprocess\n"
        "subprocess.call(cmd, shell=True)\n"
        "```\n"
    )
    result = _check(text)
    assert result.security_regressions
    assert result.confidence < 1.0


def test_eval_suggestion_is_flagged():
    text = "```python\nresult = eval(user_input)\n```\n"
    result = _check(text)
    assert any("eval" in r.lower() for r in result.security_regressions)


def test_invalid_python_block_raises_syntax_warning():
    text = "```python\ndef broken(:\n    return 1\n```\n"
    result = _check(text)
    assert result.syntax_warnings
    assert result.confidence < 1.0


def test_confidence_is_bounded_between_zero_and_one():
    text = (
        "```python\n"
        "subprocess.call(c, shell=True)\n"
        "eval(x)\n"
        "exec(y)\n"
        "pickle.loads(z)\n"
        "requests.get(u, verify=False)\n"
        "```\n"
    )
    result = _check(text)
    assert 0.0 <= result.confidence <= 1.0
