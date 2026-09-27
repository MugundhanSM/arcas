from langgraph.graph import END, START, StateGraph

from app.core.telemetry import traced_node
from app.orchestration.checkpointer import get_checkpointer, thread_config
from app.orchestration.review_nodes import (
    documentation_node,
    metrics_node,
    refactor_node,
    review_node,
    risk_finalize_node,
    risk_node,
    security_node,
    test_generation_node,
)
from app.orchestration.review_state import ReviewState

workflow = StateGraph(
    ReviewState
)


workflow.add_node(
    "review_agent",
    traced_node("review_agent", review_node, layer=5),
)

workflow.add_node(
    "metrics_agent",
    traced_node("metrics_agent", metrics_node, layer=5),
)

workflow.add_node(
    "security_agent",
    traced_node("security_agent", security_node, layer=5),
)

workflow.add_node(
    "risk_agent",
    traced_node("risk_agent", risk_node, layer=5),
)

workflow.add_node(
    "risk_finalize_agent",
    traced_node("risk_finalize_agent", risk_finalize_node, layer=5),
)

workflow.add_node(
    "refactor_agent",
    traced_node("refactor_agent", refactor_node, layer=5),
)

workflow.add_node(
    "documentation_agent",
    traced_node("documentation_agent", documentation_node, layer=5),
)

workflow.add_node(
    "test_generation_agent",
    traced_node("test_generation_agent", test_generation_node, layer=5),
)


workflow.add_edge(
    START,
    "review_agent"
)

workflow.add_edge(
    "review_agent",
    "metrics_agent"
)

workflow.add_edge(
    "review_agent",
    "security_agent"
)

# risk_agent joins the metrics and security branches: it runs only once both have completed.
workflow.add_edge(
    "metrics_agent",
    "risk_agent"
)

workflow.add_edge(
    "security_agent",
    "risk_agent"
)

# refactor_agent and documentation_agent fan out from risk and run concurrently with each other.
workflow.add_edge(
    "risk_agent",
    "refactor_agent"
)

workflow.add_edge(
    "risk_agent",
    "documentation_agent"
)

workflow.add_edge(
    "refactor_agent",
    "test_generation_agent"
)

workflow.add_edge(
    "refactor_agent",
    "risk_finalize_agent"
)

workflow.add_edge(
    "risk_finalize_agent",
    END
)

workflow.add_edge(
    "documentation_agent",
    END
)

workflow.add_edge(
    "test_generation_agent",
    END
)

_checkpointer = get_checkpointer()

_compiled = (
    workflow.compile(checkpointer=_checkpointer)
    if _checkpointer is not None
    else workflow.compile()
)


class _SessionAwareGraph:
    def __init__(self, compiled):
        self._compiled = compiled

    @staticmethod
    def _ensure_config(config):
        if config and config.get("configurable", {}).get("thread_id"):
            return config
        merged = dict(config or {})
        merged.setdefault("configurable", {})
        merged["configurable"] = {
            **thread_config()["configurable"],
            **merged["configurable"],
        }
        return merged

    async def ainvoke(self, state, config=None, **kwargs):
        return await self._compiled.ainvoke(
            state, config=self._ensure_config(config), **kwargs
        )

    def invoke(self, state, config=None, **kwargs):
        return self._compiled.invoke(
            state, config=self._ensure_config(config), **kwargs
        )

    def astream(self, state, config=None, **kwargs):
        return self._compiled.astream(
            state, config=self._ensure_config(config), **kwargs
        )

    def stream(self, state, config=None, **kwargs):
        return self._compiled.stream(
            state, config=self._ensure_config(config), **kwargs
        )

    def __getattr__(self, item):
        return getattr(self._compiled, item)


review_graph = _SessionAwareGraph(_compiled)
