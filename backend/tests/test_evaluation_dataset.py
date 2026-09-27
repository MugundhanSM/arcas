import pytest

from app.evaluation.datasets import BENCHMARK, CATEGORY_KEYWORDS


@pytest.mark.unit
def test_every_sample_has_code_and_language():
    for sample in BENCHMARK:
        assert sample.code.strip(), f"{sample.name} has empty code"
        assert sample.language, f"{sample.name} has no language"


@pytest.mark.unit
def test_safe_and_vulnerable_labels_are_consistent():
    for sample in BENCHMARK:
        if sample.is_safe:
            assert not sample.expected_categories, (
                f"safe sample {sample.name} should expect no categories"
            )
        else:
            assert sample.expected_categories, (
                f"vulnerable sample {sample.name} must expect a category"
            )


@pytest.mark.unit
def test_expected_categories_have_keyword_mappings():
    known = set(CATEGORY_KEYWORDS)
    for sample in BENCHMARK:
        for category in sample.expected_categories:
            assert category in known, (
                f"{sample.name} expects unmapped category '{category}'"
            )


@pytest.mark.unit
def test_dataset_covers_both_safe_and_vulnerable():
    safe = [s for s in BENCHMARK if s.is_safe]
    vulnerable = [s for s in BENCHMARK if not s.is_safe]
    assert len(safe) >= 3
    assert len(vulnerable) >= 10
    assert {s.name for s in BENCHMARK}.__len__() == len(BENCHMARK)
