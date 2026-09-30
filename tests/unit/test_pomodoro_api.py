# tests/unit/test_pomodoro_api.py
"""POST /api/pomodoro/start：任务绑定启动番茄钟的门控与转发。"""
import pytest

from zentray.api.handlers import ApiContext, handle_request, set_api_context


class _Svc:
    def __init__(self):
        self.is_active = False


class _Runtime:
    is_busy = False


class _TaskService:
    def find_task(self, tid):
        return None if tid == "missing" else type("T", (), {"id": tid, "title": "任务"})()


@pytest.fixture
def api(tmp_data_dir):
    started = []
    svc = _Svc()
    set_api_context(
        ApiContext(
            task_service=_TaskService(),
            pomodoro_service=svc,
            plugin_runtime=_Runtime(),
            start_pomodoro=lambda tid: started.append(tid),
        )
    )
    return svc, started


def test_start_unbound_ok(api):
    _svc, started = api
    code, body = handle_request("POST", "/api/pomodoro/start", {})
    assert code == 200 and body["ok"] is True
    assert started == [""]


def test_start_bound_task_ok(api):
    _svc, started = api
    code, body = handle_request("POST", "/api/pomodoro/start", {"task_id": "t1"})
    assert code == 200
    assert started == ["t1"]


def test_start_task_not_found(api):
    _svc, started = api
    code, body = handle_request("POST", "/api/pomodoro/start", {"task_id": "missing"})
    assert code == 404
    assert started == []


def test_start_busy_conflicts(api):
    svc, started = api
    svc.is_active = True
    code, _body = handle_request("POST", "/api/pomodoro/start", {})
    assert code == 409
    assert started == []
    svc.is_active = False
    _Runtime.is_busy = True
    code, _body = handle_request("POST", "/api/pomodoro/start", {})
    assert code == 409
    assert started == []
    _Runtime.is_busy = False
