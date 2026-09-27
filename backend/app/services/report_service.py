"""Report service."""

import json

from app.core.logging import get_logger
from app.repositories.review_result_repository import (
    ReviewResultRepository,
)
from app.repositories.review_session_repository import (
    ReviewSessionRepository,
)

logger = get_logger("arcas.services.report")


_EMPTY_RESPONSE = {
    "review_findings": {},
    "security_findings": [],
    "risk_analysis": {},
    "metrics": {},
    "refactor_recommendations": "",
    "refactor_diff": "",
    "refactored_code": "",
    "documentation": "",
    "generated_tests": "",
    "output_guardrail": {},
    "workspace_warnings": [],
    "react_traces": {},
    "warnings": [],
}


class ReportService:

    @staticmethod
    def get_report(db, session_id: str):
        session = ReviewSessionRepository.find_by_session_id(db, session_id)
        if not session:
            return None

        results = ReviewResultRepository.find_by_review_session_id(
            db, session.id
        )

        report = {
            "session_id": session.session_id,
            "language": session.language,
            "created_at": str(session.created_at),
            "results": [],
        }

        for result in results:
            if result.agent_name == "full_response":
                continue  # internal restore payload, not for this view
            parsed_result = result.result
            try:
                parsed_result = json.loads(result.result)
            except Exception:  # noqa: BLE001
                pass
            report["results"].append(
                {"agent_name": result.agent_name, "result": parsed_result}
            )

        return report

    @staticmethod
    def get_all_reviews(db, skip: int = 0, limit: int = 50, actor: str = None):
        """Return the History list with rich preview data."""
        sessions = ReviewSessionRepository.find_all(
            db, skip=skip, limit=limit, actor=actor
        )

        items = []
        for session in sessions:
            source = session.source_code or ""
            preview = source[:120] + "..." if len(source) > 120 else source
            stats = ReportService._session_stats(db, session)
            items.append(
                {
                    "session_id": session.session_id,
                    "language": session.language,
                    "intent": getattr(session, "intent", "full_review"),
                    "created_at": str(session.created_at),
                    "workspace_name": getattr(session, "workspace_name", None),
                    "source_preview": preview,
                    "finding_count": stats["finding_count"],
                    "risk_level": stats["risk_level"],
                    "maintainability_index": stats["maintainability_index"],
                }
            )
        return items

    @staticmethod
    def get_report_for_restore(db, session_id: str, actor: str = None):
        """Return a full ReviewResponse-compatible dict for restore."""
        session = ReviewSessionRepository.find_by_session_id(db, session_id)
        if not session:
            return None

        # Enforce ownership when auth is in play: a user may only restore their own sessions.
        if (
            actor is not None
            and getattr(session, "actor", None) is not None
            and session.actor != actor
        ):
            return None

        results = ReviewResultRepository.find_by_review_session_id(
            db, session.id
        )
        rows = {r.agent_name: r.result for r in results}

        if "full_response" in rows:
            try:
                response = json.loads(rows["full_response"])
                # Always trust the live session fields for these.
                response["session_id"] = session.session_id
                response["language"] = session.language
                response["intent"] = getattr(session, "intent", "full_review")
                response["source_code"] = session.source_code
                response.setdefault("message", "Restored from history.")
                return response
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "full_response row corrupt for %s: %s", session_id, exc
                )

        # Fallback reconstruction from individual agent rows.
        return ReportService._reconstruct(session, rows)

    @staticmethod
    def _reconstruct(session, rows: dict) -> dict:
        def load(name, default):
            raw = rows.get(name)
            if raw is None:
                return default
            try:
                return json.loads(raw)
            except Exception:  # noqa: BLE001
                return raw

        response = dict(_EMPTY_RESPONSE)
        response.update(
            {
                "session_id": session.session_id,
                "language": session.language,
                "intent": getattr(session, "intent", "full_review"),
                "source_code": session.source_code,
                "review_findings": load("review_agent", {}) or {},
                "security_findings": load("security_agent", []) or [],
                "risk_analysis": load("risk_agent", {}) or {},
                "metrics": load("metrics_agent", {}) or {},
                "refactor_recommendations": rows.get("refactor_agent", "")
                or "",
                "documentation": rows.get("documentation_agent", "") or "",
                "generated_tests": rows.get("test_generation_agent", "") or "",
                "message": "Restored from history (legacy record).",
            }
        )
        return response

    @staticmethod
    def _session_stats(db, session) -> dict:
        """Best-effort mini-stats for a History card."""
        stats = {
            "finding_count": 0,
            "risk_level": None,
            "maintainability_index": None,
        }
        try:
            results = ReviewResultRepository.find_by_review_session_id(
                db, session.id
            )
            rows = {r.agent_name: r.result for r in results}

            if "full_response" in rows:
                data = json.loads(rows["full_response"])
                stats["finding_count"] = len(
                    data.get("security_findings", []) or []
                )
                stats["risk_level"] = (data.get("risk_analysis") or {}).get(
                    "risk_level"
                )
                stats["maintainability_index"] = (
                    data.get("metrics") or {}
                ).get("maintainability_index")
                return stats

            if "security_agent" in rows:
                findings = json.loads(rows["security_agent"])
                stats["finding_count"] = len(findings or [])
            if "risk_agent" in rows:
                stats["risk_level"] = json.loads(rows["risk_agent"]).get(
                    "risk_level"
                )
            if "metrics_agent" in rows:
                stats["maintainability_index"] = json.loads(
                    rows["metrics_agent"]
                ).get("maintainability_index")
        except Exception:  # noqa: BLE001
            pass
        return stats
