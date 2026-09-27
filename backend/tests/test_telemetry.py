import pytest

from app.core import telemetry


@pytest.mark.unit
def test_start_span_is_a_noop_when_disabled():
    with telemetry.start_span("unit.test", attribute="value"):
        result = 1 + 1
    assert result == 2


@pytest.mark.unit
def test_traced_node_preserves_behaviour():
    def node(state):
        state["touched"] = True
        return state

    wrapped = telemetry.traced_node("demo_agent", node)
    out = wrapped({"value": 1})

    assert out == {"value": 1, "touched": True}
    assert wrapped.__name__ == "demo_agent_traced"


@pytest.mark.unit
def test_setup_telemetry_disabled_returns_false(monkeypatch):
    monkeypatch.setattr(telemetry, "_configured", False)
    monkeypatch.setattr(telemetry.settings, "ENABLE_TELEMETRY", False)

    assert telemetry.setup_telemetry(app=None) is False
