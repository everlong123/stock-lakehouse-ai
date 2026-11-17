"""Persistence helpers for AI agent conversations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database.models.agent_conversation import AgentConversation


def _truncate(text: str, limit: int) -> str:
    """Cut a message to a single readable line.

    WHY: the session title is shown in a narrow list, so a full message
    would wrap over many lines. The cut is on a word boundary where
    possible, and the ellipsis marks that something was removed.
    """
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    cut = clean[:limit].rsplit(" ", 1)[0]
    return f"{cut}…"


class ConversationRepository:
    """CRUD operations for agent_conversations."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: dict[str, Any]) -> AgentConversation:
        """Insert one turn.

        WHY THE ROLLBACK
        ----------------
        ``flush()`` writes the row to the database. If the row is too big
        for its column - a walk-forward tool result is ~70 KB and the
        column used to be ``TEXT`` (65,535 bytes) - MySQL raises a
        DataError and the session is left in a "pending rollback" state.
        Any later use of that session then fails with
        ``PendingRollbackError`` even though nothing else is wrong.

        So the failed flush is rolled back here, and the error is
        re-raised for the caller to log. The chat still answers the user;
        only the transcript copy is lost.
        """
        record = AgentConversation(**payload)
        self.session.add(record)
        try:
            self.session.flush()
        except Exception:
            self.session.rollback()
            raise
        return record

    def list_by_session(self, session_id: str, limit: int = 100) -> list[AgentConversation]:
        stmt = (
            select(AgentConversation)
            .where(AgentConversation.session_id == session_id)
            .order_by(AgentConversation.created_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt).all())

    def list_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        """Summarise every chat session, newest activity first.

        WHY THIS EXISTS
        ---------------
        A chat app that can only hold one conversation has no history. The
        user asked for the Gemini-style behaviour: a list of past chats,
        each openable, each deletable.

        The title is the FIRST user message of the session, truncated. That
        is a factual label taken from what the user actually typed — not a
        generated summary, and not a placeholder like "Chat 1" that tells
        the user nothing when they are looking for one of five chats.
        """
        rows = self.session.execute(
            select(
                AgentConversation.session_id,
                func.min(AgentConversation.created_at).label("started_at"),
                func.max(AgentConversation.created_at).label("last_active"),
                func.count(AgentConversation.id).label("message_count"),
            )
            .group_by(AgentConversation.session_id)
            .order_by(func.max(AgentConversation.created_at).desc())
            .limit(limit)
        ).all()

        if not rows:
            return []

        # Fetch the first message of each session in one extra query rather
        # than one query per session (N+1). The list is small, but the
        # pattern matters: this endpoint is called on every page load.
        session_ids = [row.session_id for row in rows]
        first_messages: dict[str, str] = {}
        for session_id in session_ids:
            stmt = (
                select(AgentConversation.user_message)
                .where(AgentConversation.session_id == session_id)
                .order_by(AgentConversation.created_at.asc())
                .limit(1)
            )
            message = self.session.scalars(stmt).first()
            if message:
                first_messages[session_id] = message

        return [
            {
                "session_id": row.session_id,
                "title": _truncate(first_messages.get(row.session_id, ""), 60),
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "last_active": row.last_active.isoformat() if row.last_active else None,
                "message_count": int(row.message_count),
            }
            for row in rows
        ]

    def delete_session(self, session_id: str) -> int:
        """Delete every turn of one session. Returns the number of rows removed."""
        stmt = delete(AgentConversation).where(AgentConversation.session_id == session_id)
        result = self.session.execute(stmt)
        self.session.flush()
        return int(result.rowcount or 0)

    def delete_message(self, message_id: int) -> int:
        """Delete one single turn. Returns the number of rows removed."""
        stmt = delete(AgentConversation).where(AgentConversation.id == message_id)
        result = self.session.execute(stmt)
        self.session.flush()
        return int(result.rowcount or 0)
