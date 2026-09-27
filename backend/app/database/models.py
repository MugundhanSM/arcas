from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class ReviewSession(Base):

    __tablename__ = "review_sessions"

    id = Column(Integer, primary_key=True)

    session_id = Column(String, unique=True, nullable=False)

    language = Column(String, nullable=False)

    intent = Column(String, nullable=False, server_default="full_review")

    # The authenticated user who created the session.
    actor = Column(String, nullable=True, index=True)

    source_code = Column(Text, nullable=False)

    # Optional user-defined label for the workspace (editable after creation).
    workspace_name = Column(String, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship


class ReviewResult(Base):

    __tablename__ = "review_results"

    id = Column(Integer, primary_key=True)

    review_session_id = Column(
        Integer,
        ForeignKey("review_sessions.id")
    )

    agent_name = Column(String, nullable=False)

    result = Column(Text, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    review_session = relationship(
        "ReviewSession",
        backref="results"
    )


class User(Base):
    """Application user for JWT/OAuth2 authentication."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)

    username = Column(String, unique=True, nullable=False, index=True)

    hashed_password = Column(String, nullable=False)

    is_active = Column(Integer, nullable=False, default=1)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


class AuditLog(Base):
    """Append-only audit trail of security-relevant events."""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)

    actor = Column(String, nullable=True)

    action = Column(String, nullable=False)

    session_id = Column(String, nullable=True)

    detail = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
