import os
import shutil
import sys
from pathlib import Path

import pytest

# Make the backend package importable when pytest is invoked from any cwd.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _llm_configured() -> bool:
    return bool(
        os.getenv("LLM_API_URL") and os.getenv("LLM_API_KEY")
    )


def _semgrep_available() -> bool:
    return shutil.which("semgrep") is not None


def pytest_collection_modifyitems(config, items):
    skip_llm = pytest.mark.skip(reason="LLM provider not configured")
    skip_semgrep = pytest.mark.skip(reason="semgrep CLI not installed")

    llm_ok = _llm_configured()
    semgrep_ok = _semgrep_available()

    for item in items:
        if "requires_llm" in item.keywords and not llm_ok:
            item.add_marker(skip_llm)
        if "requires_semgrep" in item.keywords and not semgrep_ok:
            item.add_marker(skip_semgrep)


@pytest.fixture(autouse=True)
def offline_llm(request, monkeypatch):
    if "requires_llm" in request.keywords:
        return

    from app.tools.llm_tool import LLMNotConfiguredError, LLMTool

    def _unavailable(*_args, **_kwargs):
        raise LLMNotConfiguredError("LLM disabled for hermetic tests.")

    monkeypatch.setattr(LLMTool, "is_available", staticmethod(lambda: False))
    monkeypatch.setattr(LLMTool, "generate", staticmethod(_unavailable))


@pytest.fixture(autouse=True)
def clear_result_cache():
    from app.core.session_memory import _memory_store

    with _memory_store._lock:
        _memory_store._data.clear()
        _memory_store._expires.clear()
    yield


@pytest.fixture
def vulnerable_python() -> str:
    return (
        "import subprocess\n"
        "import hashlib\n"
        "\n"
        "API_KEY = \"AKIAIOSFODNN7EXAMPLE\"\n"
        "\n"
        "def run(cmd):\n"
        "    return subprocess.call(cmd, shell=True)\n"
        "\n"
        "def digest(value):\n"
        "    return hashlib.md5(value.encode()).hexdigest()\n"
    )


@pytest.fixture
def clean_python() -> str:
    return (
        "def add(a, b):\n"
        "    \"\"\"Return the sum of two numbers.\"\"\"\n"
        "    return a + b\n"
        "\n"
        "class Calculator:\n"
        "    def total(self, values):\n"
        "        return sum(values)\n"
    )


@pytest.fixture(scope="session", autouse=True)
def _warm_semgrep_probe():
    try:
        from app.tools.semgrep_tool import warm_registry_probe

        warm_registry_probe()
    except Exception:  # noqa: BLE001
        pass
