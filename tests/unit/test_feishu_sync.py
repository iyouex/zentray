"""飞书同步单测：token 不包 data 层、事件/任务体映射、入队不抛错、禁用静默。"""
from unittest.mock import MagicMock, patch

from zentray.services.feishu_sync import (
    ACTION_UPSERT,
    FeishuSyncError,
    FeishuSyncService,
    _api,
    _event_spec,
    _task_body,
)
from zentray.services.settings_manager import FeishuSyncSettings


def _resp(data):
    m = MagicMock()
    m.json.return_value = data
    return m


def _svc():
    svc = FeishuSyncService()
    svc._ensure_worker = lambda: None  # 测试不起后台线程
    return svc


def _settings(**kw):
    return FeishuSyncSettings(app_id="cli_x", app_secret="sec", **kw)


# —— _api ——


def test_api_returns_data_section():
    with patch("zentray.services.feishu_sync.requests.request",
               return_value=_resp({"code": 0, "data": {"event": {"event_id": "e1"}}})) as p:
        d = _api("POST", "/open-apis/x", "tok", json={})
    assert d == {"event": {"event_id": "e1"}}
    assert p.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"


def test_api_token_endpoint_not_wrapped_in_data():
    """token 端点 tenant_access_token 在顶层，_api 必须原样带回。"""
    with patch("zentray.services.feishu_sync.requests.request",
               return_value=_resp({"code": 0, "tenant_access_token": "t-1", "expire": 7200})):
        d = _api("POST", "/open-apis/auth/v3/tenant_access_token/internal", json={})
    assert d["tenant_access_token"] == "t-1"


def test_api_logical_error_raises():
    with patch("zentray.services.feishu_sync.requests.request",
               return_value=_resp({"code": 99991672, "msg": "app access token invalid"})):
        try:
            _api("GET", "/open-apis/x", "bad")
            assert False
        except FeishuSyncError as e:
            assert "99991672" in str(e)


def test_api_network_error_wrapped():
    with patch("zentray.services.feishu_sync.requests.request",
               side_effect=RuntimeError("boom")):
        try:
            _api("GET", "/open-apis/x")
            assert False
        except FeishuSyncError as e:
            assert "网络错误" in str(e)


# —— 映射：_event_spec / _task_body ——


def test_event_spec_full_day():
    spec = _event_spec({"title": "写周报", "priority": "high",
                        "deadline": "2026-10-20", "category": "工作"})
    assert spec["summary"] == "🔴 写周报"
    assert spec["start_time"]["date"] == "2026-10-20"
    # 全天事件 end_date 为次日（飞书按前闭后开解释）
    assert spec["end_time"]["date"] == "2026-10-21"


def test_event_spec_timed_30_minutes():
    import datetime as dt

    spec = _event_spec({"title": "评审", "deadline": "2026-10-20",
                        "reminder": {"enabled": True, "time_of_day": "09:30"}})
    start = int(spec["start_time"]["timestamp"])
    end = int(spec["end_time"]["timestamp"])
    expect = dt.datetime(2026, 10, 20, 9, 30).timestamp()
    assert start == int(expect) and end - start == 30 * 60


def test_event_spec_none_without_deadline_or_reminder():
    assert _event_spec({"title": "x", "deadline": "", "reminder": None}) is None
    assert _event_spec({"title": "x", "deadline": "not-a-date",
                        "reminder": {"enabled": False}}) is None


def test_task_body_members_and_due():
    s = _settings(task_list_guid="g1", feishu_user_id="ou_1")
    body = _task_body(s, {"title": "修灯", "details": "客厅", "deadline": "2026-10-20"})
    assert body["summary"] == "修灯" and body["description"] == "客厅"
    assert body["tasklists"] == [{"tasklist_guid": "g1"}]
    assert body["members"][0]["id"] == "ou_1"
    assert body["due"]["is_all_day"] is True


def test_task_body_bad_deadline_no_due():
    body = _task_body(_settings(), {"title": "x", "deadline": "bad"})
    assert "due" not in body


# —— 服务行为 ——


def test_enqueue_never_raises_and_latest_wins():
    svc = _svc()
    svc.enqueue(object(), "upsert")  # 非法对象：吞掉不抛
    svc.enqueue({"id": "t1", "title": "a"}, "upsert")
    svc.enqueue({"id": "t1", "title": "b"}, "deleted")
    assert svc._pending["t1"][0]["title"] == "b"
    assert svc._pending["t1"][1] == "deleted"


def test_push_disabled_silent_no_http():
    with patch("zentray.services.settings_manager.SettingsManager") as sm, patch(
        "zentray.services.feishu_sync.requests.request"
    ) as p:
        sm.return_value.feishu_sync = _settings(enabled=False)
        _svc()._push({"id": "t1"}, ACTION_UPSERT)
    assert not p.called


def test_fetch_token_parsed_and_cached():
    with patch("zentray.services.settings_manager.SettingsManager") as sm, patch(
        "zentray.services.feishu_sync.requests.request",
        return_value=_resp({"code": 0, "tenant_access_token": "t-2", "expire": 7200}),
    ) as p:
        sm.return_value.feishu_sync = _settings()
        svc = _svc()
        assert svc._fetch_token() == "t-2"
        assert svc._fetch_token() == "t-2"  # 命中缓存
    assert p.call_count == 1


def test_connection_requires_credentials(tmp_data_dir):
    ok, msg = _svc().test_connection()
    assert not ok and "App ID" in msg
