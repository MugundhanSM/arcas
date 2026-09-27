import asyncio
import time

import httpx
import pytest
from httpx import ASGITransport

from app.agents.security_agent import SecurityAgent
from app.main import app
from app.orchestration.review_graph import review_graph

pytestmark = pytest.mark.integration


def test_health_stays_responsive_during_long_review(
    monkeypatch, vulnerable_python
):
    # Simulate a slow, blocking static-analysis stage (e.g. a large Semgrep scan).
    def _slow_analyze(code, language="python", deep_scan=False):
        time.sleep(1.5)
        return []

    monkeypatch.setattr(
        SecurityAgent, "analyze", staticmethod(_slow_analyze)
    )

    async def scenario():
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            # Kick off the (slow) review in the background.
            review_task = asyncio.create_task(
                review_graph.ainvoke(
                    {
                        "source_code": vulnerable_python,
                        "language": "python",
                        "intent": "full_review",
                    }
                )
            )

            # Give the review a moment to reach the slow security stage.
            await asyncio.sleep(0.2)

            # Health must answer immediately, not after the review finishes.
            start = time.perf_counter()
            response = await client.get("/health")
            elapsed = time.perf_counter() - start

            assert response.status_code == 200
            assert elapsed < 0.2, (
                f"/health took {elapsed:.3f}s while a review was running - "
                "the event loop is being blocked."
            )

            # Let the background review finish so the loop shuts down cleanly.
            await review_task

    asyncio.run(scenario())
