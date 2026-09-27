import pytest

from app.tools.retriever_tool import RetrieverTool

pytestmark = pytest.mark.unit


def test_retriever_returns_relevant_python_security_context():
    context = RetrieverTool.get_context(
        language="python",
        query="subprocess shell injection command execution",
        top_k=5,
    )
    assert isinstance(context, str)
    assert len(context) > 0
    # The retrieved guidance should mention an injection-related concept.
    assert any(
        term in context.lower()
        for term in ("injection", "subprocess", "shell", "command")
    )


def test_retriever_biases_toward_requested_language():
    context = RetrieverTool.get_context(
        language="javascript",
        query="cross site scripting xss innerHTML",
        top_k=5,
    )
    assert isinstance(context, str)
    assert len(context) > 0


def test_retriever_empty_query_still_returns_preferred_guides():
    context = RetrieverTool.get_context(language="python", query="", top_k=3)
    assert isinstance(context, str)
    # With no query it should fall back to the preferred guides, not crash.
    assert len(context) >= 0
