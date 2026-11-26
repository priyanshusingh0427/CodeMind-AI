"""Tests for the SQLite history layer."""

from datetime import datetime, timedelta

from core.ai_debugger import AIDebugger
from database.operations import (delete_all_sessions, delete_session, get_session, get_statistics, list_sessions,
                                 save_session)


def _result(settings, code="def area(r):\n    return 3.14 * r * r\n"):
    return AIDebugger(settings, llm=None, use_pylint=False).debug(code).to_dict()


def test_save_get_and_list(settings):
    payload = _result(settings)
    session_id = save_session(settings.database_url, payload)
    record = get_session(settings.database_url, session_id)
    assert record is not None
    assert record["title"] == "def area"
    assert record["original_code"] == payload["original_code"]
    assert record["repair_status"] == "not_attempted"
    assert len(list_sessions(settings.database_url)) == 1


def test_save_is_idempotent_per_session(settings):
    payload = _result(settings)
    save_session(settings.database_url, payload)
    payload["explanation"] = "updated"
    save_session(settings.database_url, payload)
    rows = list_sessions(settings.database_url)
    assert len(rows) == 1 and rows[0]["explanation"] == "updated"


def test_search_and_filters(settings):
    save_session(settings.database_url, _result(settings, "def alpha():\n    return 1\n"))
    save_session(settings.database_url, _result(settings, "def beta():\n    return undefined_name\n"))
    assert [r["title"] for r in list_sessions(settings.database_url, search="beta")] == ["def beta"]
    assert len(list_sessions(settings.database_url, status="not_attempted")) == 2
    assert list_sessions(settings.database_url, status="verified") == []
    tomorrow = datetime.now() + timedelta(days=1)
    assert list_sessions(settings.database_url, date_from=tomorrow) == []


def test_delete_and_statistics(settings):
    first = save_session(settings.database_url, _result(settings))
    save_session(settings.database_url, _result(settings, "def g():\n    return x\n"))
    stats = get_statistics(settings.database_url)
    assert stats["total_sessions"] == 2
    assert stats["total_issues"] >= 1
    assert delete_session(settings.database_url, first)
    assert not delete_session(settings.database_url, first)
    assert delete_all_sessions(settings.database_url) == 1
    assert get_statistics(settings.database_url)["total_sessions"] == 0
