"""User satisfaction."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.core.logging import get_logger

logger = get_logger("arcas.evaluation.satisfaction")


def wilson_interval(
    positives: int, total: int, z: float = 1.96
) -> Dict[str, float]:
    """Wilson score confidence interval for a binomial proportion."""
    if total == 0:
        return {"lower": 0.0, "upper": 1.0, "point": 0.0}

    proportion = positives / total
    denominator = 1 + z**2 / total
    centre = proportion + z**2 / (2 * total)
    margin = z * math.sqrt(
        (proportion * (1 - proportion) + z**2 / (4 * total)) / total
    )
    return {
        "point": round(proportion, 3),
        "lower": round(max(0.0, (centre - margin) / denominator), 3),
        "upper": round(min(1.0, (centre + margin) / denominator), 3),
    }


@dataclass
class AgentSatisfaction:
    agent: str
    positive: int = 0
    negative: int = 0

    @property
    def total(self) -> int:
        return self.positive + self.negative

    def as_dict(self) -> dict:
        interval = wilson_interval(self.positive, self.total)
        return {
            "agent": self.agent,
            "thumbs_up": self.positive,
            "thumbs_down": self.negative,
            "responses": self.total,
            "satisfaction_rate": interval["point"],
            "confidence_interval_95": [interval["lower"], interval["upper"]],
        }


@dataclass
class SatisfactionReport:
    overall: AgentSatisfaction
    per_agent: List[AgentSatisfaction] = field(default_factory=list)
    source: str = "audit_log"
    note: str = ""

    def as_dict(self) -> dict:
        payload = {
            "source": self.source,
            **self.overall.as_dict(),
            "per_agent": [a.as_dict() for a in self.per_agent],
        }
        payload.pop("agent", None)
        if self.note:
            payload["note"] = self.note
        # Small samples must not be quoted as headline figures.
        if self.overall.total < 20:
            payload["interpretation"] = (
                f"Sample size is {self.overall.total}; the 95% interval spans "
                f"{payload['confidence_interval_95'][0]:.2f}-"
                f"{payload['confidence_interval_95'][1]:.2f}. Report as "
                "indicative only, not as a converged satisfaction rate."
            )
        return payload


def _parse_vote(detail: Optional[str]) -> Optional[dict]:
    if not detail:
        return None
    try:
        payload = json.loads(detail)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or "rating" not in payload:
        return None
    return payload


def aggregate_feedback(db=None) -> SatisfactionReport:
    """Aggregate every recorded thumbs-up/down vote."""
    rows: List[dict] = []

    if db is not None:
        try:
            from app.database.models import AuditLog

            records = (
                db.query(AuditLog)
                .filter(AuditLog.action == "feedback")
                .all()
            )
            for record in records:
                vote = _parse_vote(getattr(record, "detail", None))
                if vote:
                    rows.append(vote)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read feedback from the database: %s", exc)

    if not rows:
        rows = _read_audit_file()

    overall = AgentSatisfaction(agent="overall")
    buckets: Dict[str, AgentSatisfaction] = defaultdict(
        lambda: AgentSatisfaction(agent="")
    )

    for vote in rows:
        rating = vote.get("rating")
        if rating not in (1, -1):
            continue
        agent = (vote.get("agent") or "overall").strip() or "overall"
        bucket = buckets[agent]
        bucket.agent = agent
        if rating == 1:
            bucket.positive += 1
            overall.positive += 1
        else:
            bucket.negative += 1
            overall.negative += 1

    note = ""
    if overall.total == 0:
        note = (
            "No feedback has been recorded yet. Metric 6 requires real user "
            "votes; collect them via POST /api/v1/review/{session_id}/feedback "
            "before reporting a satisfaction figure."
        )

    return SatisfactionReport(
        overall=overall,
        per_agent=sorted(buckets.values(), key=lambda a: -a.total),
        note=note,
    )


def _read_audit_file() -> List[dict]:
    """Parse feedback rows from the append-only audit file."""
    from pathlib import Path

    from app.core.config import settings

    path = Path(settings.AUDIT_LOG_PATH)
    if not path.exists():
        return []

    rows: List[dict] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) < 5 or parts[2] != "feedback":
                continue
            vote = _parse_vote(parts[4])
            if vote:
                rows.append(vote)
    except OSError as exc:  # noqa: BLE001
        logger.warning("Could not read the audit file: %s", exc)
    return rows
