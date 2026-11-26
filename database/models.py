"""ORM models for debugging history."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base class."""


class DebugSessionRecord(Base):
    """One stored debugging session."""

    __tablename__ = "debug_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True)
    title: Mapped[str] = mapped_column(String(200), default="Untitled")
    mode: Mapped[str] = mapped_column(String(20), default="hybrid")
    original_code: Mapped[str] = mapped_column(Text)
    corrected_code: Mapped[str] = mapped_column(Text, default="")
    expected_behavior: Mapped[str] = mapped_column(Text, default="")
    issues: Mapped[list] = mapped_column(JSON, default=list)
    ai_issues: Mapped[list] = mapped_column(JSON, default=list)
    metrics_before: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics_after: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    quality_before: Mapped[float] = mapped_column(Float, default=0.0)
    quality_after: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    test_results: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, default="")
    changes: Mapped[list] = mapped_column(JSON, default=list)
    model_name: Mapped[str] = mapped_column(String(100), default="")
    repair_status: Mapped[str] = mapped_column(String(40), default="not_attempted", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    total_issues: Mapped[int] = mapped_column(Integer, default=0)
    critical_issues: Mapped[int] = mapped_column(Integer, default=0)
    duration: Mapped[float] = mapped_column(Float, default=0.0)

    def to_dict(self) -> dict:
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}
