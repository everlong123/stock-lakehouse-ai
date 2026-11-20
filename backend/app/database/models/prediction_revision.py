"""Append-only copies of forecasts before a revision replaces the latest view."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class PredictionRevision(Base):
    __tablename__ = "prediction_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    prediction_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    model_name: Mapped[str] = mapped_column(String(64), nullable=False)
    target_session: Mapped[date] = mapped_column(Date, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    archived_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
