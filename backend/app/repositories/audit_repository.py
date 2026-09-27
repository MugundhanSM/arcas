"""Audit log repository."""

from datetime import datetime, timezone

from app.core.config import settings
from app.core.logging import get_logger
from app.database.models import AuditLog

logger = get_logger("arcas.audit")


class AuditRepository:

    @staticmethod
    def record(
        db,
        action: str,
        actor: str = None,
        session_id: str = None,
        detail: str = None,
    ) -> None:
        # File trail (best effort, append-only).
        try:
            line = (
                f"{datetime.now(timezone.utc).isoformat()}\t"
                f"{actor or '-'}\t{action}\t{session_id or '-'}\t"
                f"{(detail or '').replace(chr(9), ' ').replace(chr(10), ' ')}\n"
            )
            with open(settings.AUDIT_LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError as exc:  # noqa: BLE001
            logger.debug("Could not write audit file: %s", exc)

        # Database trail (best effort).
        if db is None:
            return
        try:
            entry = AuditLog(
                actor=actor,
                action=action,
                session_id=session_id,
                detail=detail,
            )
            db.add(entry)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.debug("Could not write audit row: %s", exc)
            try:
                db.rollback()
            except Exception:  # noqa: BLE001
                pass
