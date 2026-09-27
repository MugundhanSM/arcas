from typing import List

from sqlalchemy.orm import Session

from app.database.models import ReviewResult


class ReviewResultRepository:

    @staticmethod
    def create(
        db: Session,
        review_session_id: int,
        agent_name: str,
        result: str
    ):

        review_result = ReviewResult(
            review_session_id=review_session_id,
            agent_name=agent_name,
            result=result
        )

        db.add(review_result)
        db.commit()
        db.refresh(review_result)

        return review_result

    @staticmethod
    def bulk_create(
        db: Session,
        review_session_id: int,
        agent_results: List[tuple],
    ) -> List[ReviewResult]:
        """Persist multiple agent results in a single transaction."""
        rows = []
        for agent_name, result in agent_results:
            row = ReviewResult(
                review_session_id=review_session_id,
                agent_name=agent_name,
                result=result,
            )
            db.add(row)
            db.flush()  # assign id without committing
            rows.append(row)

        db.commit()
        for row in rows:
            db.refresh(row)

        return rows

    @staticmethod
    def find_by_review_session_id(
        db,
        review_session_id: int
    ):

        return (
            db.query(ReviewResult)
            .filter(
                ReviewResult.review_session_id ==
                review_session_id
            )
            .all()
        )
