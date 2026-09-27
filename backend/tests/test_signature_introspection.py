import pytest

from app.agents.signature_introspector import (
    Param,
    build_call_arguments,
    describe_signatures,
    extract_signatures,
    synthesize_value,
)
from app.agents.test_generation_agent import TestGenerationAgent

SAMPLE = '''
def divide(a, b):
    return a / b


def greet(name, greeting="hi"):
    return greeting + name


def process(items: list, limit: int = 10, verbose: bool = False):
    return items[:limit]


def login(username: str, password: str):
    return username == "admin" and password == "secret"


class Calculator:
    def __init__(self):
        self.total = 0

    def add(self, x: int, y: int) -> int:
        return x + y

    @staticmethod
    def square(n):
        return n * n

    def _private(self):
        return 1
'''


# Signature extraction
@pytest.mark.unit
def test_extracts_module_functions_and_public_methods():
    sigs = extract_signatures(SAMPLE)
    names = {s.qualified_name for s in sigs}
    assert "divide" in names
    assert "greet" in names
    assert "Calculator.add" in names
    assert "Calculator.square" in names
    # Private methods are excluded.
    assert "Calculator._private" not in names


@pytest.mark.unit
def test_self_receiver_is_dropped_from_methods():
    sigs = {s.qualified_name: s for s in extract_signatures(SAMPLE)}
    add = sigs["Calculator.add"]
    assert [p.name for p in add.required_params()] == ["x", "y"]


@pytest.mark.unit
def test_defaults_are_not_required():
    sigs = {s.name: s for s in extract_signatures(SAMPLE)}
    required = [p.name for p in sigs["process"].required_params()]
    assert required == ["items"]  # limit and verbose have defaults


@pytest.mark.unit
def test_fragment_that_does_not_parse_returns_empty():
    assert extract_signatures("def broken(:\n    pass") == []


# Dummy-value synthesis
@pytest.mark.unit
@pytest.mark.parametrize(
    "annotation,check",
    [
        ("int", lambda v: v.lstrip("-").isdigit()),
        ("str", lambda v: "'" in v),
        ("bool", lambda v: v == "True"),
        ("list", lambda v: "[" in v),
        ("dict", lambda v: "{" in v),
        ("Optional[int]", lambda v: v.lstrip("-").isdigit()),
    ],
)
def test_annotation_driven_synthesis(annotation, check):
    val = synthesize_value(Param(name="x", annotation=annotation), counter=[1])
    assert check(val), f"{annotation} -> {val!r}"


@pytest.mark.unit
def test_name_heuristics_pick_plausible_values():
    assert "@" in synthesize_value(Param(name="email"))
    assert "http" in synthesize_value(Param(name="url"))
    assert synthesize_value(Param(name="is_active")) == "True"


@pytest.mark.unit
def test_single_letter_params_are_numeric_and_distinct():
    sig = extract_signatures("def divide(a, b):\n    return a / b")[0]
    args, chosen = build_call_arguments(sig)
    # Both numeric, and distinct so the call never divides by zero.
    assert chosen["a"] != chosen["b"]
    assert chosen["a"].lstrip("-").isdigit()
    assert chosen["b"].lstrip("-").isdigit()


# Smoke-test generation + execution
@pytest.mark.unit
def test_generated_smoke_tests_execute_and_pass():
    result = TestGenerationAgent.execute_tests(SAMPLE, "", "python")
    assert result["ran"] is True
    assert result["passed"] is True
    assert result["smoke_count"] >= 4
    assert "passed" in (result["stdout"] or "")


@pytest.mark.unit
def test_divide_smoke_does_not_divide_by_zero():
    code = "def divide(a, b):\n    return a / b\n"
    result = TestGenerationAgent.execute_tests(code, "", "python")
    assert result["passed"] is True


@pytest.mark.unit
def test_self_heals_when_llm_tests_do_not_import():
    broken_md = (
        "## Test Strategy\n\n"
        "```python\n"
        "from module_under_test import a_function_that_does_not_exist\n"
        "def test_bogus():\n"
        "    assert a_function_that_does_not_exist() == 1\n"
        "```\n"
    )
    code = "def real_function(x: int) -> int:\n    return x + 1\n"
    result = TestGenerationAgent.execute_tests(code, broken_md, "python")
    assert result["ran"] is True
    assert result["healed"] is True
    assert result["passed"] is True


@pytest.mark.unit
def test_third_party_imports_are_reported_not_installed():
    md = (
        "```python\n"
        "import requests\n"
        "from module_under_test import f\n"
        "def test_x():\n"
        "    assert f(1) == 2\n"
        "```\n"
    )
    code = "def f(x):\n    return x + 1\n"
    result = TestGenerationAgent.execute_tests(code, md, "python")
    # requests must be flagged as an un-installed third-party import.
    assert "requests" in result.get("third_party_imports", [])


@pytest.mark.unit
def test_non_python_language_is_skipped_gracefully():
    result = TestGenerationAgent.execute_tests("int x = 1;", "", "java")
    assert result["ran"] is False
    assert "not yet supported" in result["reason"]


@pytest.mark.unit
def test_fallback_scaffold_is_runnable_when_llm_unavailable():
    code = "def add(a, b):\n    return a + b\n"
    md = TestGenerationAgent.analyze(
        code, "python", {"functions": ["add"]}, []
    )
    assert "module_under_test" in md
    result = TestGenerationAgent.execute_tests(code, md, "python")
    assert result["passed"] is True


@pytest.mark.unit
def test_describe_signatures_is_readable():
    text = describe_signatures(extract_signatures(SAMPLE))
    assert "divide(a, b)" in text
    assert "Calculator.add(x: int, y: int) -> int" in text
