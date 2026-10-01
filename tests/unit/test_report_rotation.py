"""报告托盘轮播：通知未点击查看的报告临时进入顶栏任务轮播。"""
from zentray.services.report_rotation import ReportRotation
from zentray.services.settings_manager import AIJobSettings, OpsSettings


def test_add_and_active():
    r = ReportRotation()
    r.add("run:x", "📄 插件报告待查看: A", 60, now=100.0)
    slots = r.active(now=100.0)
    assert len(slots) == 1
    assert slots[0]["key"] == "run:x"
    assert slots[0]["text"].startswith("📄")


def test_expiry_prunes():
    r = ReportRotation()
    r.add("k", "t", 1, now=100.0)
    assert r.active(now=100.0 + 59)
    assert r.active(now=100.0 + 61) == []


def test_mark_viewed():
    r = ReportRotation()
    r.add("k", "t", 60, now=0)
    assert r.mark_viewed("k") is True
    assert r.active(now=1) == []
    assert r.mark_viewed("k") is False  # 重复查看不报错


def test_same_key_refreshes_not_stacks():
    r = ReportRotation()
    r.add("k", "t1", 5, now=0)
    r.add("k", "t2", 60, now=10)
    slots = r.active(now=20)
    assert len(slots) == 1
    assert slots[0]["text"] == "t2"
    assert slots[0]["expires_at"] == 10 + 60 * 60


def test_settings_defaults_roundtrip():
    job = AIJobSettings.from_dict({}, kind="plan")
    assert job.report_tray_enabled is True
    assert job.report_tray_minutes == 60
    d = AIJobSettings.from_dict(
        {"report_tray_enabled": False, "report_tray_minutes": 30}, kind="review"
    )
    assert d.report_tray_enabled is False
    assert d.report_tray_minutes == 30
    assert job.to_dict()["report_tray_minutes"] == 60

    ops = OpsSettings()
    assert ops.report_tray_enabled is True
    assert ops.report_tray_minutes == 60
