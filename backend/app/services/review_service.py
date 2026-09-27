import asyncio
import json
import logging
import uuid

from sqlalchemy.orm import Session

from app.core.session_memory import SessionMemory
from app.core.telemetry import start_span
from app.orchestration.checkpointer import thread_config
from app.orchestration.intent_classifier import IntentClassifier
from app.orchestration.review_graph import review_graph
from app.orchestration.review_state import INTENT_AGENTS
from app.orchestration.substep_emitter import (
    install_queue_emitter,
    uninstall_emitter,
)
from app.repositories.audit_repository import AuditRepository
from app.repositories.review_result_repository import ReviewResultRepository
from app.repositories.review_session_repository import ReviewSessionRepository

logger = logging.getLogger("arcas.services.review")


# Live-progress topology.
_STAGE_PREDECESSORS = {
    "review_agent": set(),
    "metrics_agent": {"review_agent"},
    "security_agent": {"review_agent"},
    "risk_agent": {"metrics_agent", "security_agent"},
    "refactor_agent": {"risk_agent"},
    "documentation_agent": {"risk_agent"},
    "test_generation_agent": {"refactor_agent"},
    "risk_finalize_agent": {"refactor_agent"},
}

_STAGE_SUCCESSORS = {
    "review_agent": ("metrics_agent", "security_agent"),
    "metrics_agent": ("risk_agent",),
    "security_agent": ("risk_agent",),
    "risk_agent": (
        "refactor_agent",
        "documentation_agent",
    ),
    "refactor_agent": ("risk_finalize_agent", "test_generation_agent"),
}

_RUNNING_LABELS = {
    "review_agent": "Analysing code structure",
    "metrics_agent": "Computing quality metrics",
    "security_agent": "Scanning for vulnerabilities",
    "risk_agent": "Assessing overall risk",
    "refactor_agent": "Consulting secure-coding knowledge and drafting guidance",
    "documentation_agent": "Drafting documentation",
    "test_generation_agent": "Generating tests",
    "output_guardrails": "Validating generated output",
    "risk_finalize_agent": "Re-assessing risk with AI-identified findings",
}

_DONE_LABELS = {
    "review_agent": "Structure analysed",
    "metrics_agent": "Quality metrics computed",
    "security_agent": "Vulnerability scan complete",
    "risk_agent": "Risk assessed",
    "refactor_agent": "Refactoring guidance ready",
    "documentation_agent": "Documentation ready",
    "test_generation_agent": "Tests generated",
    "output_guardrails": "Output validated",
    "risk_finalize_agent": "Risk score finalised",
}


class ReviewService:

    @staticmethod
    def _resolve_intent(
        intent: str,
        source_code: str,
        language: str,
        request_text: str = "",
    ):
        if (intent or "").lower() != "auto":
            return intent, None

        classification = IntentClassifier.classify(
            source_code=source_code,
            language=language,
            request_text=request_text or "",
        )
        logger.info(
            "Auto-resolved intent -> %s (confidence=%.2f)",
            classification.intent, classification.confidence,
        )
        return classification.intent, classification

    @staticmethod
    async def process_review(
        db: Session,
        language: str,
        source_code: str,
        intent: str = "full_review",
        actor: str = None,
        client_session_id: str = None,
        request_text: str = "",
    ):
        # Resolve the intent (auto-classify when requested) before routing.
        intent, classification = ReviewService._resolve_intent(
            intent, source_code, language, request_text
        )

        active_agents = INTENT_AGENTS.get(intent, INTENT_AGENTS["full_review"])

        # Run the graph first - before committing the session row.
        try:
            with start_span("orchestration.graph", layer=4, intent=intent):
                graph_result = await review_graph.ainvoke(
                    {
                        "source_code": source_code,
                        "language": language,
                        "intent": intent,
                    },
                    config=thread_config(client_session_id),
                )
        except Exception as exc:
            logger.exception(
                "review_graph.ainvoke() failed "
                "(intent=%s language=%s): %s",
                intent, language, exc,
            )
            raise RuntimeError(
                "Code review pipeline failed. Please try again."
            ) from exc

        return ReviewService._finalize(
            db,
            language=language,
            source_code=source_code,
            intent=intent,
            actor=actor,
            client_session_id=client_session_id,
            graph_result=graph_result,
            active_agents=active_agents,
            classification=classification,
        )

    @staticmethod
    async def process_review_streaming(
        db: Session,
        language: str,
        source_code: str,
        intent: str = "full_review",
        actor: str = None,
        client_session_id: str = None,
        request_text: str = "",
    ):
        """Run the pipeline and yield real progress events as they happen."""
        # Resolve the intent (auto-classify when requested) before routing.
        intent, classification = ReviewService._resolve_intent(
            intent, source_code, language, request_text
        )
        if classification is not None:
            yield {
                "stage": "intent_classifier",
                "status": "done",
                "message": (
                    f"Detected intent: {classification.intent} "
                    f"({int(classification.confidence * 100)}% confidence)"
                ),
                "intent": classification.intent,
                "confidence": classification.confidence,
                "signals": classification.signals,
            }

        active_agents = INTENT_AGENTS.get(intent, INTENT_AGENTS["full_review"])

        completed: set[str] = set()
        announced: set[str] = set()
        accumulated: dict = {}

        # Live producer/consumer streaming.
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        _SENTINEL = object()
        driver_state: dict = {}

        emitter_token = install_queue_emitter(loop, queue)

        async def _driver() -> None:
            """Run the graph, putting real progress events on the queue."""
            try:
                for event in ReviewService._announce_running(
                    "review_agent", completed, announced, active_agents
                ):
                    await queue.put(event)

                async for update in review_graph.astream(
                    {
                        "source_code": source_code,
                        "language": language,
                        "intent": intent,
                    },
                    config=thread_config(client_session_id),
                    stream_mode="updates",
                ):
                    for node_name, partial in update.items():
                        if isinstance(partial, dict):
                            if "react_traces" in partial:
                                merged_traces = {
                                    **accumulated.get("react_traces", {}),
                                    **partial["react_traces"],
                                }
                                accumulated.update(
                                    {k: v for k, v in partial.items()
                                     if k != "react_traces"}
                                )
                                accumulated["react_traces"] = merged_traces
                            else:
                                accumulated.update(partial)
                        completed.add(node_name)

                        # Report completion of the node that just finished.
                        if node_name in active_agents:
                            await queue.put({
                                "stage": node_name,
                                "status": "done",
                                "message": _DONE_LABELS.get(node_name, node_name),
                            })

                            if node_name == "refactor_agent":
                                await queue.put({
                                    "stage": "output_guardrails",
                                    "status": "running",
                                    "message": _RUNNING_LABELS["output_guardrails"],
                                })
                                await queue.put({
                                    "stage": "output_guardrails",
                                    "status": "done",
                                    "message": _DONE_LABELS["output_guardrails"],
                                })

                        for successor in _STAGE_SUCCESSORS.get(node_name, ()):
                            if _STAGE_PREDECESSORS[successor] <= completed:
                                for event in ReviewService._announce_running(
                                    successor,
                                    completed,
                                    announced,
                                    active_agents,
                                ):
                                    await queue.put(event)
            except Exception as exc:  # noqa: BLE001
                driver_state["exc"] = exc
            finally:
                await asyncio.sleep(0)
                await queue.put(_SENTINEL)

        driver_task = asyncio.create_task(_driver())

        try:
            while True:
                item = await queue.get()
                if item is _SENTINEL:
                    break
                yield item
        except GeneratorExit:
            # Client disconnected mid-stream - abandon the graph run cleanly.
            driver_task.cancel()
            raise
        finally:
            uninstall_emitter(emitter_token)

        # Surface any failure the driver captured, preserving the previous user-facing error contract.
        await driver_task
        if driver_state.get("exc") is not None:
            exc = driver_state["exc"]
            logger.exception(
                "review_graph.astream() failed (intent=%s language=%s): %s",
                intent, language, exc,
            )
            raise RuntimeError(
                "Code review pipeline failed. Please try again."
            ) from exc

        response = ReviewService._finalize(
            db,
            language=language,
            source_code=source_code,
            intent=intent,
            actor=actor,
            client_session_id=client_session_id,
            graph_result=accumulated,
            active_agents=active_agents,
            classification=classification,
        )

        yield {"stage": "complete", "data": response}

    @staticmethod
    def _announce_running(node, completed, announced, active_agents):
        if node in announced or node in completed:
            return
        announced.add(node)
        if node in active_agents:
            yield {
                "stage": node,
                "status": "running",
                "message": _RUNNING_LABELS.get(node, node),
            }

    @staticmethod
    def _finalize(
        db: Session,
        *,
        language: str,
        source_code: str,
        intent: str,
        actor: str,
        client_session_id: str,
        graph_result: dict,
        active_agents: set,
        classification=None,
    ):
        review_findings        = graph_result.get("review_findings", {})
        security_findings      = graph_result.get("security_findings", [])
        risk_analysis          = graph_result.get("risk_analysis", {})
        metrics                = graph_result.get("metrics", {})
        refactor_recommendations = graph_result.get(
            "refactor_recommendations", ""
        )
        refactor_diff          = graph_result.get("refactor_diff", "")
        refactored_code        = graph_result.get("refactored_code", "")
        documentation          = graph_result.get("documentation", "")
        generated_tests        = graph_result.get("generated_tests", "")
        output_guardrail       = graph_result.get("output_guardrail", {})
        workspace_warnings     = graph_result.get("workspace_warnings", [])
        react_traces           = graph_result.get("react_traces", {})

        # Persist the session record - non-fatal.
        fallback_session_id = str(uuid.uuid4())
        session = None
        try:
            session = ReviewSessionRepository.create(
                db=db,
                session_id=fallback_session_id,
                language=language,
                source_code=source_code,
                intent=intent,
                actor=actor,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Could not persist review session (DB unavailable?): %s", exc
            )
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass

        effective_session_id = (
            session.session_id if session else fallback_session_id
        )

        response = {
            "session_id": effective_session_id,
            "language": language,
            "intent": intent,
            "intent_confidence": (
                classification.confidence if classification else None
            ),
            "intent_signals": (
                classification.signals if classification else []
            ),
            "source_code": source_code,
            "review_findings": review_findings,
            "security_findings": security_findings,
            "risk_analysis": risk_analysis,
            "metrics": metrics,
            "refactor_recommendations": refactor_recommendations,
            "refactor_diff": refactor_diff,
            "refactored_code": refactored_code,
            "documentation": documentation,
            "generated_tests": generated_tests,
            "output_guardrail": output_guardrail,
            "workspace_warnings": workspace_warnings,
            "react_traces": react_traces,
        }

        # Persist agent results in a single transaction (bulk_create).
        if session is not None:
            serializers = {
                "review_agent":          lambda: json.dumps(review_findings, indent=2),
                "metrics_agent":         lambda: json.dumps(metrics, indent=2),
                "security_agent":        lambda: json.dumps(security_findings, indent=2),
                "risk_agent":            lambda: json.dumps(risk_analysis, indent=2),
                "refactor_agent":        lambda: refactor_recommendations,
                "documentation_agent":   lambda: documentation,
                "test_generation_agent": lambda: generated_tests,
            }

            pairs = []
            for agent_name, serialize in serializers.items():
                if agent_name not in active_agents:
                    continue
                try:
                    pairs.append((agent_name, serialize()))
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "Could not serialize result for %s: %s",
                        agent_name, exc,
                    )
                    pairs.append((agent_name, "null"))

            # Persist the complete response as a single row for fast restore.
            try:
                pairs.append(("full_response", json.dumps(response)))
            except (TypeError, ValueError) as exc:
                logger.warning("Could not serialize full_response: %s", exc)

            try:
                ReviewResultRepository.bulk_create(
                    db=db,
                    review_session_id=session.id,
                    agent_results=pairs,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Could not persist review results (DB unavailable?): %s",
                    exc,
                )
                try:
                    db.rollback()
                except Exception:  # noqa: BLE001
                    pass

        # Append-only audit entry (already has its own error handling).
        AuditRepository.record(
            db=db,
            action="review.completed",
            actor=actor,
            session_id=effective_session_id,
            detail=(
                f"intent={intent} language={language} "
                f"security_findings={len(security_findings)}"
            ),
        )

        # Session memory for multi-turn context.
        if client_session_id:
            try:
                SessionMemory.record_turn(
                    client_session_id,
                    {
                        "review_session_id": effective_session_id,
                        "intent": intent,
                        "language": language,
                        "security_findings": len(security_findings),
                        "maintainability": metrics.get(
                            "maintainability_index"
                        ),
                    },
                )
            except Exception:  # noqa: BLE001
                pass

        return response
