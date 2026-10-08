# tests/unit/test_calendar_export.py
"""设置-系统「导出任务到系统日历」：_build_tasks_ics 纯函数。"""
from zentray.api.handlers import _build_tasks_ics
from zentray.core.models import Task
from zentray.core.reminder import TaskReminder


def _task(**kw):
    base = dict(title="写周报", category="工作", priority="medium", deadline="2026-10-10")
    base.update(kw)
    return Task(**base)


def test_ics_all_day_event_for_deadline():
    ics = _build_tasks_ics([_task(id="t1")])
    assert ics.startswith("BEGIN:VCALENDAR\r\n")
    assert "UID:zentray-t1@zentray.local" in ics
    assert "DTSTART;VALUE=DATE:20261010" in ics
    assert "SUMMARY:写周报" in ics
    assert ics.count("BEGIN:VEVENT") == 1


def test_ics_skips_tasks_without_date_or_reminder():
    tasks = [
        _task(id="a", deadline=None),  # 无截止无提醒 → 跳过
        _task(id="b"),                 # 有截止 → 导出
        _task(id="c", deadline="bad-date"),  # 非法日期 → 跳过
    ]
    assert _build_tasks_ics(tasks).count("BEGIN:VEVENT") == 1


def test_ics_reminder_makes_timed_event():
    t = _task(id="r1", reminder=TaskReminder(enabled=True, time_of_day="09:30"))
    ics = _build_tasks_ics([t])
    assert "DTSTART:20261010T093000" in ics
    assert "DTEND:20261010T100000" in ics  # 30 分钟


def test_ics_escapes_text():
    ics = _build_tasks_ics([_task(id="e1", title="买米,油", details="备注;一行\n二行")])
    assert "SUMMARY:买米\\,油" in ics
    assert "一行\\n二行" in ics
    assert "分类\\: " not in ics  # 冒号无需转义，只确认未被破坏
