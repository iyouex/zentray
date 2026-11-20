"""下一步操作提示（纯函数）。"""
from __future__ import annotations

from zentray.core.models import Task
from zentray.services.next_step import build_next_step


def _task(**kw):
    base = {"title": "写文档", "category": "工作", "priority": "high"}
    base.update(kw)
    return Task(**base)


def test_none():
    assert build_next_step(None) is None


def test_active_subtask_points_to_first():
    t = _task(
        subtasks=[
            {"id": "a", "title": "补四角", "status": "done"},
            {"id": "b", "title": "角落过渡", "status": "active"},
        ]
    )
    ns = build_next_step(t)
    assert ns["kind"] == "subtask"
    assert ns["text"] == "完成子任务 2/2「角落过渡」"
    assert ns["subtask_id"] == "b"
    assert "25" in ns["hint"]


def test_abandoned_subtask_ignored():
    t = _task(
        subtasks=[
            {"id": "a", "title": "旧子任务", "status": "abandoned"},
            {"id": "b", "title": "新子任务", "status": "active"},
        ]
    )
    ns = build_next_step(t)
    assert ns["kind"] == "subtask"
    assert "新子任务" in ns["text"]


def test_all_done():
    t = _task(subtasks=[{"id": "a", "title": "a", "status": "done"}])
    ns = build_next_step(t)
    assert ns["kind"] == "done"
    assert "完成" in ns["text"]


def test_no_subs_with_deadline():
    t = _task(deadline="2026-11-22")
    ns = build_next_step(t)
    assert ns["kind"] == "task"
    assert "截止 2026-11-22" in ns["hint"]


def test_no_subs_no_deadline():
    t = _task(deadline=None)
    ns = build_next_step(t)
    assert ns["kind"] == "task"
    assert ns["hint"] == "先推进一小步"


def test_non_dict_subtasks_ignored():
    t = _task(subtasks=["bad", {"id": "b", "title": "ok", "status": "active"}])
    ns = build_next_step(t)
    assert ns["kind"] == "subtask"
    assert ns["text"].endswith("「ok」")
