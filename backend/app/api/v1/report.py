import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_user
from app.database.dependencies import get_db
from app.repositories.audit_repository import AuditRepository
from app.services.report_service import ReportService

router = APIRouter()


class FeedbackRequest(BaseModel):
    rating: int  # 1 (thumbs up) or -1 (thumbs down)
    comment: Optional[str] = None
    agent: Optional[str] = None  # which agent's output is being rated


@router.get("/report/{session_id}")
def get_report(
    session_id: str,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
):

    report = ReportService.get_report(
        db=db,
        session_id=session_id
    )

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No review found for session '{session_id}'.",
        )

    return report


@router.get("/review/{session_id}/restore")
def restore_review(
    session_id: str,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
):
    restored = ReportService.get_report_for_restore(
        db=db,
        session_id=session_id,
        actor=user,
    )

    if restored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No restorable review found for session '{session_id}'.",
        )

    return restored


@router.post("/review/{session_id}/feedback")
def submit_feedback(
    session_id: str,
    feedback: FeedbackRequest,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
):
    """Record thumbs-up / thumbs-down feedback for an agent output."""
    if feedback.rating not in (1, -1):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="rating must be 1 (helpful) or -1 (not helpful).",
        )

    AuditRepository.record(
        db=db,
        action="feedback",
        actor=user,
        session_id=session_id,
        detail=json.dumps(feedback.dict()),
    )
    return {"status": "recorded", "session_id": session_id}


@router.get("/reviews")
def get_reviews(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: str = Depends(get_current_user),
):
    # User-scoped history: pass the authenticated user so each user only sees their own sessions.
    return ReportService.get_all_reviews(
        db=db,
        skip=skip,
        limit=limit,
        actor=user,
    )
