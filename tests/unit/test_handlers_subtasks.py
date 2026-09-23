# tests/unit/test_handlers_subtasks.py
"""子任务 API 路由测试——路由顺序是易碎点，必须专测。"""
import pytest

from zentray.api.handlers import ApiContext, handle_request, set_api_context


@pytest.fixture
def api(task_service):
    set_api_context(ApiContext(task_service=task_service))
    return task_service


def _make_task(task_service, **extra):
    return task_service.create_task({"title": "任务", "category": "工作", **extra})


def test_add_subtask_route(api):
    t = _make_task(api)
    code, body = handle_request("POST", f"/api/tasks/{t.id}/subtasks", {"title": "步骤"})
    assert code == 200
    assert [s["title"] for s in body["item"]["subtasks"]] == ["步骤"]


def test_add_subtask_requires_title(api):
    t = _make_task(api)
    code, _ = handle_request("POST", f"/api/tasks/{t.id}/subtasks", {"title": "  "})
    assert code == 400


def test_subtask_done_returns_auto_completed(api):
    t = _make_task(api, subtasks=[{"title": "甲"}])
    sid = t.subtasks[0]["id"]
    code, body = handle_request("POST", f"/api/tasks/{t.id}/subtasks/{sid}/done", {})
    assert code == 200
    assert body["auto_completed"] is True  # 唯一子任务完成即自动完成
    assert body["item"]["subtasks"][0]["status"] == "done"


def test_subtask_abandon_no_auto_while_others_active(api):
    t = _make_task(api, subtasks=[{"title": "甲"}, {"title": "乙"}])
    sid = t.subtasks[0]["id"]
    code, body = handle_request("POST", f"/api/tasks/{t.id}/subtasks/{sid}/abandon", {})
    assert code == 200
    assert body["auto_completed"] is False


def test_old_suffix_routes_not_hijacked(api):
    """/done /abandon /select 后缀分支必须在新复合分支之前生效。"""
    t = _make_task(api)
    assert handle_request("POST", f"/api/tasks/{t.id}/done", {})[0] == 200
    assert handle_request("POST", f"/api/tasks/{t.id}/progress", {"percent": 50})[0] == 404  # 已删


def test_subtask_bad_sid_404(api):
    t = _make_task(api, subtasks=[{"title": "甲"}])
    code, _ = handle_request("POST", f"/api/tasks/{t.id}/subtasks/no-such/done", {})
    assert code == 404


def test_reminder_action_routes(api):
    t = _make_task(api)
    # snooze：写 snooze_until
    code, body = handle_request(
        "POST", f"/api/tasks/{t.id}/reminder-action",
        {"action": "snooze", "fire_key": "2026-09-23|11:00", "snooze_minutes": 10},
    )
    assert code == 200
    assert body["item"]["reminder"]["snooze_until"]
    # dismiss：写 last_fired_key、清 snooze
    code, body = handle_request(
        "POST", f"/api/tasks/{t.id}/reminder-action",
        {"action": "dismiss", "fire_key": "2026-09-23|11:00"},
    )
    assert code == 200
    rem = body["item"]["reminder"]
    assert rem["last_fired_key"] == "2026-09-23|11:00" and not rem["snooze_until"]
    # done：归档删除，item 为快照
    code, body = handle_request(
        "POST", f"/api/tasks/{t.id}/reminder-action",
        {"action": "done", "fire_key": "2026-09-23|11:00"},
    )
    assert code == 200
    assert not any(x.id == t.id for x in api.get_all_tasks())
    # 非法 action
    assert handle_request(
        "POST", f"/api/tasks/{_make_task(api).id}/reminder-action", {"action": "update"}
    )[0] == 400
