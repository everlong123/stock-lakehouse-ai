"""AI agent conversation history stored in MySQL."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class AgentConversation(Base):
    """One user/assistant turn, including optional tool invocation."""

    __tablename__ = "agent_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # WHY MEDIUMTEXT AND NOT TEXT
    # --------------------------
    # `tool_result` stores the whole JSON payload of every tool call. A
    # walk-forward over one symbol produces ~70 KB of windows, and MySQL's
    # TEXT tops out at 65,535 BYTES - the INSERT failed with
    # "Data too long for column 'tool_result'" and the request returned
    # HTTP 500. MEDIUMTEXT holds 16 MB, which is far above any payload the
    # agent can produce.
    user_message: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    assistant_message: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_arguments: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    tool_result: Mapped[str | None] = mapped_column(MEDIUMTEXT, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
