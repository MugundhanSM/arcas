"""Incremental schema migrations."""

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger("arcas.migrations")


def run_migrations(engine: Engine) -> None:
    """Apply all pending schema migrations."""
    with engine.connect() as conn:
        _add_intent_column(conn)
        _add_actor_column(conn)
        _add_workspace_name_column(conn)
        conn.commit()
    logger.info("Schema migrations applied successfully.")


def _add_intent_column(conn) -> None:
    conn.execute(
        text(
            """
            ALTER TABLE review_sessions
                ADD COLUMN IF NOT EXISTS intent VARCHAR
                    NOT NULL DEFAULT 'full_review'
            """
        )
    )
    logger.debug("review_sessions.intent column ensured.")


def _add_actor_column(conn) -> None:
    conn.execute(
        text(
            """
            ALTER TABLE review_sessions
                ADD COLUMN IF NOT EXISTS actor VARCHAR
            """
        )
    )
    logger.debug("review_sessions.actor column ensured.")


def _add_workspace_name_column(conn) -> None:
    conn.execute(
        text(
            """
            ALTER TABLE review_sessions
                ADD COLUMN IF NOT EXISTS workspace_name VARCHAR
            """
        )
    )
    logger.debug("review_sessions.workspace_name column ensured.")
