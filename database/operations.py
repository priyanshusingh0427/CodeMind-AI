"""CRUD operations for debugging history.

All functions take the database URL explicitly so they are easy to test with a
temporary database. History storage can be disabled in Settings; callers must
check ``settings.history_enabled`` before saving.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import delete, func, or_, select

from database.connection import session_scope
from database.models import DebugSessionRecord
from utils.logger import get_logger

logger = get_logger("database")


def _title_for(code: str) -> str:
    for line in code.splitlines():
        stripped = line.strip()
        if stripped.startswith(("def ", "class ", "async def ")):
            return stripped.split("(")[0].split(":")[0][:120]
    first = next((line.strip() for line in code.splitlines() if line.strip()), "Untitled")
    return first[:120]


def save_session(database_url: str, result: dict[str, Any]) -> str:
    """Persist a :meth:`core.ai_debugger.DebugResult.to_dict` payload. Returns the session id."""
    issues = result.get("static_issues", [])
    ai_issues = result.get("ai_issues", [])
    record = DebugSessionRecord(
        session_id=result["session_id"], title=_title_for(result.get("original_code", "")),
        mode=result.get("mode", "hybrid"), original_code=result.get("original_code", ""),
        corrected_code=result.get("corrected_code", ""), expected_behavior=result.get("expected_behavior", ""),
        issues=issues, ai_issues=ai_issues, metrics_before=result.get("metrics_before") or {},
        metrics_after=result.get("metrics_after"), quality_before=float(result.get("quality_before") or 0.0),
        quality_after=result.get("quality_after"), test_results=result.get("test_report"),
        explanation=result.get("explanation", ""), changes=result.get("changes", []),
        model_name=result.get("model_name", ""), repair_status=result.get("repair_status", "not_attempted"),
        attempts=int(result.get("attempts") or 0), total_issues=len(issues) + len(ai_issues),
        critical_issues=sum(1 for i in issues + ai_issues if i.get("severity") in ("critical", "error")),
        duration=float(result.get("duration") or 0.0),
    )
    with session_scope(database_url) as session:
        existing = session.scalar(select(DebugSessionRecord).where(
            DebugSessionRecord.session_id == record.session_id))
        if existing is not None:
            for column in DebugSessionRecord.__table__.columns:
                if column.name not in ("id", "created_at"):
                    setattr(existing, column.name, getattr(record, column.name))
        else:
            session.add(record)
    logger.info("session saved", extra={"session": record.session_id})
    return record.session_id


def list_sessions(database_url: str, search: str = "", status: Optional[str] = None,
                  date_from: Optional[datetime] = None, date_to: Optional[datetime] = None,
                  limit: int = 200) -> list[dict[str, Any]]:
    """Return sessions (newest first) filtered by text search, status and date range."""
    query = select(DebugSessionRecord).order_by(DebugSessionRecord.created_at.desc()).limit(max(1, limit))
    if search.strip():
        pattern = f"%{search.strip()}%"
        query = query.where(or_(DebugSessionRecord.title.ilike(pattern),
                                DebugSessionRecord.original_code.ilike(pattern),
                                DebugSessionRecord.explanation.ilike(pattern),
                                DebugSessionRecord.session_id.ilike(pattern)))
    if status:
        query = query.where(DebugSessionRecord.repair_status == status)
    if date_from:
        query = query.where(DebugSessionRecord.created_at >= date_from)
    if date_to:
        query = query.where(DebugSessionRecord.created_at <= date_to)
    with session_scope(database_url) as session:
        return [record.to_dict() for record in session.scalars(query)]


def get_session(database_url: str, session_id: str) -> Optional[dict[str, Any]]:
    with session_scope(database_url) as session:
        record = session.scalar(select(DebugSessionRecord).where(DebugSessionRecord.session_id == session_id))
        return record.to_dict() if record else None


def delete_session(database_url: str, session_id: str) -> bool:
    with session_scope(database_url) as session:
        outcome = session.execute(delete(DebugSessionRecord).where(DebugSessionRecord.session_id == session_id))
        return bool(outcome.rowcount)


def delete_all_sessions(database_url: str) -> int:
    with session_scope(database_url) as session:
        return int(session.execute(delete(DebugSessionRecord)).rowcount or 0)


def get_statistics(database_url: str) -> dict[str, Any]:
    """Aggregate statistics for the dashboards."""
    with session_scope(database_url) as session:
        total = session.scalar(select(func.count(DebugSessionRecord.id))) or 0
        avg_quality_before = session.scalar(select(func.avg(DebugSessionRecord.quality_before))) or 0.0
        avg_quality_after = session.scalar(select(func.avg(DebugSessionRecord.quality_after))
                                           .where(DebugSessionRecord.quality_after.is_not(None))) or 0.0
        avg_duration = session.scalar(select(func.avg(DebugSessionRecord.duration))) or 0.0
        total_issues = session.scalar(select(func.sum(DebugSessionRecord.total_issues))) or 0
        statuses = dict(session.execute(select(DebugSessionRecord.repair_status,
                                               func.count(DebugSessionRecord.id))
                                        .group_by(DebugSessionRecord.repair_status)).all())
    return {"total_sessions": int(total), "avg_quality_before": round(float(avg_quality_before), 1),
            "avg_quality_after": round(float(avg_quality_after), 1), "avg_duration": round(float(avg_duration), 2),
            "total_issues": int(total_issues), "status_counts": {k: int(v) for k, v in statuses.items()}}
