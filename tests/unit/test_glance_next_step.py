"""/api/glance 返回 next_step（隔离真实活动日志）。"""
from __future__ import annotations

from types import SimpleNamespace

from zentray.api import handlers
from zentray.core.models import Task


class _FakeTaskService:
    def __init__(self, task: Task):
        self.task = task

    def get_current_task(self):
        return self.task

    def get_all_tasks(self):
        return [self.task]

    def get_task_display_title(self, task):
        return task.title


def test_glance_includes_next_step(monkeypatch):
    task = Task(
        title="写文档",
        category="工作",
        priority="high",
        subtasks=[{"id": "a", "title": "补四角", "status": "active"}],
    )
    fake = SimpleNamespace(
        task_service=_FakeTaskService(task),
        pomodoro_service=None,
        report_rotation=None,
        plugin_runtime=None,
    )
    monkeypatch.setattr(handlers, "_ctx", fake)
    monkeypatch.setattr(
        "zentray.services.activity_log.pomodoro_today_stats", lambda: (0, 0)
    )
    code, data = handlers._glance_state()
    assert code == 200
    assert data["item"]["next_step"]["kind"] == "subtask"
    assert "补四角" in data["item"]["next_step"]["text"]
