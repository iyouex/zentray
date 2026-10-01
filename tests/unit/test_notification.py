# tests/unit/test_notification.py
from zentray.services.wxpusher import WxPusherService
from zentray.services.notification import NotificationClient


def test_wxpusher_missing_credentials():
    svc = WxPusherService(app_token="", uid="")
    assert not svc.is_configured()
    result = svc.send_message("hello")
    assert result["code"] == -1


def test_notification_client_unconfigured(monkeypatch):
    from zentray.services.settings_manager import NotificationSettings

    monkeypatch.setattr(NotificationSettings, "app_popup_enabled", lambda self: False)
    client = NotificationClient(app_token="", uid="")
    result = client.send("t", "c")
    assert result["status"] == "error"


def test_send_channel_filter(monkeypatch):
    """渠道白名单：只发所选类型，app_popup 标记跟随筛选。"""
    from zentray.services.settings_manager import NotificationSettings, NotifyChannel

    monkeypatch.setattr(NotificationSettings, "app_popup_enabled", lambda self: True)
    monkeypatch.setattr(
        NotificationSettings,
        "wxpusher_channels",
        lambda self: [
            NotifyChannel(
                type="wxpusher",
                wxpusher_app_token="t",
                wxpusher_uid="u",
                enabled=True,
            )
        ],
    )
    sent = []

    def _fake_send(self, content, summary="ZenTray 通知", content_type=3):
        sent.append(summary)
        return {"code": 1000}

    monkeypatch.setattr(WxPusherService, "is_configured", lambda self: True)
    monkeypatch.setattr(WxPusherService, "send_message", _fake_send)

    client = NotificationClient(app_token="", uid="")
    r = client.send("t1", "c", channels=["wxpusher"])
    assert sent == ["t1"]
    assert r["status"] == "ok" and r["app_popup"] is False

    r2 = client.send("t2", "c", channels=["app_popup"])
    assert sent == ["t1"]  # wxpusher 被筛掉
    assert r2["app_popup"] is True

    r3 = client.send("t3", "c")  # 不筛 = 全部
    assert sent == ["t1", "t3"] and r3["app_popup"] is True


def test_job_notify_channels_roundtrip():
    from zentray.services.settings_manager import AIJobSettings, OpsSettings

    j = AIJobSettings.from_dict(
        {"notify_channels": ["wxpusher", "bogus", "wxpusher", "app_popup"]},
        kind="plan",
    )
    assert j.notify_channels == ["wxpusher", "app_popup"]
    assert AIJobSettings.from_dict({}, kind="plan").notify_channels == []
    assert AIJobSettings().to_dict()["notify_channels"] == []
    assert OpsSettings().notify_channels == []


def test_popup_selected(monkeypatch):
    from zentray.workers.nightly_job import NightlyJobWorker
    import zentray.services.settings_manager as sm_mod

    class FakeJob:
        def __init__(self, ch):
            self.notify_channels = ch

    class FakeAI:
        plan = FakeJob(["wxpusher"])
        review = FakeJob([])

    class FakeSM:
        ai = FakeAI()

    monkeypatch.setattr(sm_mod, "SettingsManager", lambda: FakeSM())
    assert NightlyJobWorker._popup_selected("plan") is False  # 只选了 wxpusher
    assert NightlyJobWorker._popup_selected("review") is True  # 空 = 跟随全局
