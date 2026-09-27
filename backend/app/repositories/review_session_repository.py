from sqlalchemy.orm import Session

from app.database.models import ReviewSession


class ReviewSessionRepository:

    @staticmethod
    def create(
        db: Session,
        session_id: str,
        language: str,
        source_code: str,
        intent: str = "full_review",
        actor: str = None,
    ):

        review = ReviewSession(
            session_id=session_id,
            language=language,
            source_code=source_code,
            intent=intent,
            actor=actor,
        )

        db.add(review)
        db.commit()
        db.refresh(review)

        return review
    

    @staticmethod
    def find_by_session_id(
        db,
        session_id: str
    ):

        return (
            db.query(ReviewSession)
            .filter(
                ReviewSession.session_id == session_id
            )
            .first()
        )

    @staticmethod
    def update_workspace_name(
        db,
        session_id: str,
        workspace_name: str,
        actor: str = None,
    ):
        """Update the workspace name for a session (actor-scoped)."""
        query = db.query(ReviewSession).filter(
            ReviewSession.session_id == session_id
        )
        if actor is not None:
            query = query.filter(ReviewSession.actor == actor)
        session = query.first()
        if session is None:
            return None
        session.workspace_name = workspace_name
        db.commit()
        db.refresh(session)
        return session


    @staticmethod
    def find_all(
        db,
        skip: int = 0,
        limit: int = 50,
        actor: str = None,
    ):

        query = db.query(ReviewSession)

        # User-scoped history: when an actor is supplied, only return that user's sessions.
        if actor is not None:
            query = query.filter(ReviewSession.actor == actor)

        return (
            query
            .order_by(
                ReviewSession.created_at.desc()
            )
            .offset(skip)
            .limit(limit)
            .all()
        )
