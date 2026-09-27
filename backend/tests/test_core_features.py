import pytest

from app.core.selfcheck import SelfCheckGPT, split_sentences
from app.core.telemetry import start_span
from app.core.trace_store import SpanRecorder, TraceStore
from app.evaluation.refactor_correctness import measure_refactoring_correctness
from app.evaluation.satisfaction import wilson_interval
from app.tools.retriever_tool import RetrieverTool
from app.tools.treesitter_tool import TreeSitterTool

pytestmark = pytest.mark.unit


# Layer 8 - SelfCheckGPT

_SAMPLES = [
    "The query is built by concatenating strings, which permits SQL "
    "injection. Use parameterized queries via cursor.execute with placeholders.",
    "String concatenation in the SQL query enables injection. Fix by using "
    "parameterized queries and cursor.execute placeholders.",
    "SQL injection is possible because the query concatenates strings. "
    "Parameterized queries with cursor.execute placeholders resolve it.",
]


def test_faithful_paraphrase_scores_low_risk():
    primary = (
        "The function uses string concatenation to build the SQL query. This "
        "allows SQL injection. Use parameterized queries with cursor.execute "
        "and placeholders."
    )
    result = SelfCheckGPT.score_with_samples(primary, _SAMPLES)
    assert result.ran
    assert result.risk_level == "low"


def test_fabricated_api_scores_high_risk():
    primary = (
        "The function uses string concatenation. Call "
        "sqlalchemy.autosanitize_bindparams to fix it automatically."
    )
    result = SelfCheckGPT.score_with_samples(primary, _SAMPLES)
    assert result.risk_level == "high"
    flagged = " ".join(t for s in result.sentences for t in s.unsupported_tokens)
    assert "autosanitize_bindparams" in flagged


def test_unrelated_answer_scores_maximum_risk():
    primary = "The code has a memory leak in the buffer allocator."
    assert SelfCheckGPT.score_with_samples(primary, _SAMPLES).hallucination_score > 0.9


def test_selfcheck_needs_at_least_two_samples():
    result = SelfCheckGPT.score_with_samples("Anything.", ["only one"])
    assert not result.ran
    assert "insufficient samples" in result.skip_reason


def test_selfcheck_runs_with_an_injected_sampler():
    result = SelfCheckGPT.check(
        prompt="review this",
        primary_response=_SAMPLES[0],
        num_samples=3,
        sampler=lambda _p: _SAMPLES[1],
    )
    assert result.ran and result.samples_used == 3


def test_sentence_splitter_handles_markdown_bullets():
    text = "- First finding is here.\n- Second finding is there.\n"
    assert len(split_sentences(text)) == 2


# Layer 9 - in-process tracing


def test_trace_records_spans_per_layer():
    trace_id = TraceStore.start_trace()
    with start_span("gateway", layer=2):
        with start_span("guardrails", layer=3):
            pass
    trace = TraceStore.get(trace_id)
    layers = {row["layer"] for row in trace.layer_breakdown()}
    assert {2, 3} <= layers


def test_bottleneck_uses_self_time_not_inclusive_time():
    import time

    trace_id = TraceStore.start_trace()
    with start_span("gateway", layer=2):
        with start_span("agent", layer=5):
            time.sleep(0.03)
    payload = TraceStore.get(trace_id).as_dict()
    assert payload["bottleneck"]["layer_name"].startswith("L5")


def test_spans_outside_a_trace_are_a_no_op():
    from app.core.trace_store import set_current_trace

    set_current_trace(None)
    with SpanRecorder("orphan", 5):
        pass  # must not raise


def test_span_records_errors_without_swallowing_them():
    trace_id = TraceStore.start_trace()
    with pytest.raises(ValueError):
        with start_span("failing", layer=5):
            raise ValueError("boom")
    spans = TraceStore.get(trace_id).spans
    assert any(s.error and "boom" in s.error for s in spans)


# Layer 7 - unified knowledge corpus


def test_structured_corpus_is_reachable_by_default():
    stats = RetrieverTool.stats()
    assert stats["structured_entries"] >= 300
    assert stats["total_documents"] >= 330
    assert stats["ranking"] == "bm25"


def test_retrieval_prefers_the_matching_language():
    results = RetrieverTool.search("sql query string concatenation", "java", 5)
    languages = [doc.language for doc, _ in results]
    assert "java" in languages


def test_retrieval_finds_the_relevant_cwe_entry():
    results = RetrieverTool.search(
        "pickle deserialization of untrusted data", "python", 5
    )
    titles = " ".join(doc.title.lower() for doc, _ in results)
    assert "deserialization" in titles


def test_empty_query_still_returns_context():
    assert RetrieverTool.search("", "python", 3)


# Layer 6 - multi-language AST parsing


def test_python_is_parsed_with_a_real_grammar():
    result = TreeSitterTool.analyze(
        "import os\nclass A:\n    def m(self): pass\n", "python"
    )
    assert result["parser"] == "tree-sitter"
    assert result["classes"] == ["A"]


@pytest.mark.parametrize(
    "language,code,expected_function",
    [
        ("java", "public class F { public void bar(){} }", "bar"),
        ("go", 'package main\nimport "fmt"\nfunc Hello() {}', "Hello"),
        ("rust", "use std::fs;\nfn main(){}", "main"),
        ("ruby", 'require "json"\nclass D\n def bark; end\nend', "bark"),
    ],
)
def test_additional_grammars_when_installed(language, code, expected_function):
    result = TreeSitterTool.analyze(code, language)
    if result["parser"] != "tree-sitter":
        pytest.skip(f"tree-sitter grammar for {language} not installed")
    assert expected_function in result["functions"]


def test_unknown_language_falls_back_without_raising():
    result = TreeSitterTool.analyze("fn main() {}", "brainfuck")
    assert result["parser"] == "regex"


def test_parser_provenance_is_always_reported():
    for language in ("python", "cobol"):
        assert TreeSitterTool.analyze("x = 1", language)["parser"] in (
            "tree-sitter",
            "regex",
        )


def test_grouped_go_imports_are_not_reported_as_a_bare_paren():
    result = TreeSitterTool.analyze(
        'package main\nimport (\n  "fmt"\n  "os"\n)\nfunc M(){}', "go"
    )
    if result["parser"] != "tree-sitter":
        pytest.skip("tree-sitter grammar for go not installed")
    assert "import (" not in result["imports"]


def test_syntax_errors_are_counted():
    result = TreeSitterTool.analyze("def broken(:\n    pass\n", "python")
    if result["parser"] != "tree-sitter":
        pytest.skip("tree-sitter grammar for python not installed")
    assert result["syntax_errors"] > 0


# Metric 5 - refactoring correctness

_ORIGINAL = "def divide(a, b):\n    return a / b\n"
_TESTS = (
    "from subject import divide\n"
    "def test_divide():\n    assert divide(6, 3) == 2\n"
)


@pytest.mark.integration
def test_behaviour_preserving_refactor_scores_one():
    refactored = (
        "def divide(a, b):\n"
        "    if b == 0:\n"
        "        raise ValueError('zero')\n"
        "    return a / b\n"
    )
    result = measure_refactoring_correctness(_ORIGINAL, refactored, _TESTS)
    if not result.ran:
        pytest.skip(result.skip_reason)
    assert result.correctness == 1.0
    assert result.counts["regression"] == 0


@pytest.mark.integration
def test_behaviour_breaking_refactor_is_caught():
    result = measure_refactoring_correctness(
        _ORIGINAL, "def divide(a, b):\n    return b / a\n", _TESTS
    )
    if not result.ran:
        pytest.skip(result.skip_reason)
    assert result.correctness == 0.0
    assert result.counts["regression"] == 1


def test_missing_refactor_is_skipped_not_scored_zero():
    result = measure_refactoring_correctness(_ORIGINAL, "", _TESTS)
    assert not result.ran and "No refactored code" in result.skip_reason


def test_non_python_is_skipped_explicitly():
    result = measure_refactoring_correctness("a", "b", _TESTS, language="java")
    assert not result.ran and "Python only" in result.skip_reason


# Metric 6 - user satisfaction


def test_wilson_interval_widens_for_small_samples():
    small = wilson_interval(2, 2)
    large = wilson_interval(200, 200)
    assert small["point"] == large["point"] == 1.0
    assert small["lower"] < large["lower"]


def test_wilson_interval_handles_no_data():
    assert wilson_interval(0, 0)["point"] == 0.0


# Layer 4 - graph checkpointing


def test_thread_config_always_supplies_a_thread_id():
    from app.orchestration.checkpointer import thread_config

    assert thread_config("s1")["configurable"]["thread_id"] == "s1"
    assert thread_config(None)["configurable"]["thread_id"]


def test_anonymous_calls_get_isolated_threads():
    from app.orchestration.checkpointer import thread_config

    first = thread_config(None)["configurable"]["thread_id"]
    second = thread_config(None)["configurable"]["thread_id"]
    assert first != second


def test_checkpointer_reports_its_real_backend():
    from app.orchestration.checkpointer import checkpointer_status

    status = checkpointer_status()
    assert status["backend"] in ("redis", "memory", "disabled", "none")
    if status["backend"] == "memory":
        assert status["shared_across_processes"] is False


# Benchmark dataset provenance


@pytest.mark.parametrize("name", ["sate_iv", "codereviewer"])
def test_dataset_provenance_is_never_overstated(name):
    from app.evaluation.benchmark_datasets import Provenance, load_dataset

    loaded = load_dataset(name)
    assert loaded.samples
    if loaded.provenance is Provenance.LOCAL_SUBSET:
        assert "NOT as" in loaded.note
        assert all(
            s.provenance is Provenance.LOCAL_SUBSET for s in loaded.samples
        )


def test_cwe_category_mapping_is_defined_for_bundled_labels():
    from app.evaluation.benchmark_datasets import (
        CWE_TO_CATEGORY,
        load_dataset,
    )

    for sample in load_dataset("sate_iv").samples:
        for cwe in sample.expected_cwes:
            assert cwe in CWE_TO_CATEGORY, f"{cwe} has no category mapping"
