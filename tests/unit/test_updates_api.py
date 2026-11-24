"""应用内自更新接口：后台启动、取消、稍后与状态快照（服务层换假实现，不触网）。"""
import pytest

from zentray.api.handlers import ApiContext, handle_request, set_api_context
from zentray.services import updater


class _FakeUpdater:
    def __init__(self):
        self.calls = []
        self.snapshot = {"state": "available", "result": {"version": "9.9.9"}}
        self.fail_with = None

    def _record(self, name, *args):
        if self.fail_with is not None:
            raise RuntimeError(self.fail_with)
        self.calls.append((name, *args))

    def start_check(self, proxy="", manual=True):
        self._record("check", proxy, manual)
        return {"started": True, "state": "checking"}

    def start_download(self, version="", proxy=""):
        self._record("download", version, proxy)
        return {"started": True, "state": "downloading"}

    def cancel_download(self):
        self._record("cancel")
        return {"cancelled": True, "state": "available"}

    def status(self):
        return dict(self.snapshot)

    def start_install(self):
        self._record("install")
        return {"started": True, "state": "installing"}

    def restart(self):
        self._record("restart")
        return {"restarting": True}

    def defer_restart(self):
        self._record("defer")
        return {"deferred": True, "state": "installed"}


@pytest.fixture
def api(monkeypatch, tmp_data_dir):
    fake = _FakeUpdater()
    monkeypatch.setattr(updater.UpdaterService, "_instance", fake)
    set_api_context(ApiContext())
    return fake


def test_check_starts_in_background_and_returns_at_once(api):
    code, body = handle_request("POST", "/api/updates/check", {})
    assert code == 200 and body == {"started": True, "state": "checking"}
    assert api.calls == [("check", "", True)]  # 接口发起的检查是用户可见的手动检查


def test_check_is_no_longer_a_get_route(api):
    code, _body = handle_request("GET", "/api/updates/check")
    assert code == 404  # 发起网络动作只走 POST（享有 Origin 防跨站）
    assert api.calls == []


def test_status_returns_the_state_machine_snapshot(api):
    api.snapshot = {"state": "downloading", "downloaded": 10, "total": 100,
                    "result": {"version": "9.9.9", "has_update": True}}
    code, body = handle_request("GET", "/api/updates/status")
    assert code == 200 and body["state"] == "downloading"
    assert body["result"]["has_update"] is True


def test_download_only_needs_the_version_and_carries_the_configured_proxy(api):
    code, body = handle_request("PUT", "/api/settings", {"settings": {
        "update": {"proxy": "http://127.0.0.1:7897"}}})
    assert code == 200
    code, body = handle_request("POST", "/api/updates/download", {"version": "v9.9.9"})
    assert code == 200 and body == {"started": True, "state": "downloading"}
    assert api.calls == [("download", "9.9.9", "http://127.0.0.1:7897")]


def test_update_settings_round_trip_keeps_auto_check_default_on(api):
    code, body = handle_request("GET", "/api/settings")
    assert body["settings"]["update"] == {"proxy": "", "auto_check": True}
    handle_request("PUT", "/api/settings", {"settings": {"update": {"auto_check": False}}})
    code, body = handle_request("GET", "/api/settings")
    assert body["settings"]["update"]["auto_check"] is False
    assert body["settings"]["update"]["proxy"] == ""


def test_download_refusal_is_reported_as_400(api):
    api.fail_with = "请先检查更新"
    code, body = handle_request("POST", "/api/updates/download", {})
    assert code == 400 and body == {"error": "请先检查更新"}


@pytest.mark.parametrize("method, path, name, expected", [
    ("POST", "/api/updates/cancel", "cancel", {"cancelled": True, "state": "available"}),
    ("POST", "/api/updates/install", "install", {"started": True, "state": "installing"}),
    ("POST", "/api/updates/restart", "restart", {"restarting": True}),
    ("POST", "/api/updates/defer", "defer", {"deferred": True, "state": "installed"}),
])
def test_cancel_install_restart_and_defer_reach_the_service(api, method, path, name, expected):
    code, body = handle_request(method, path, {})
    assert code == 200 and body == expected
    assert api.calls == [(name,)]


@pytest.mark.parametrize("path, name, status", [
    ("/api/updates/cancel", "cancel", 500),
    ("/api/updates/install", "install", 400),
    ("/api/updates/restart", "restart", 500),
    ("/api/updates/defer", "defer", 400),
    ("/api/updates/check", "check", 500),
])
def test_service_errors_carry_the_reason(api, path, name, status):
    api.fail_with = "尚未安装更新"
    code, body = handle_request("POST", path, {})
    assert code == status and body == {"error": "尚未安装更新"}
    assert api.calls == []
