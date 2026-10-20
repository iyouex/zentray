"""局部设置保存不得重置省略字段（历次升级后丢设置的回归）。

根因：_apply_dict 曾对已存在的 section 整体替换、缺失字段取硬编码默认值，
任何局部 payload（页面局部保存/向导/旧客户端）都会清掉自己没回传的字段。
"""

from zentray.services.settings_manager import SettingsManager


def _fresh(tmp_data_dir):
    SettingsManager._instance = None
    return SettingsManager()


def test_partial_notification_patch_keeps_channels(tmp_data_dir):
    sm = _fresh(tmp_data_dir)
    wx = next(c for c in sm.notification.channels if c.type == "wxpusher")
    wx.enabled = True
    wx.wxpusher_app_token = "AT_x"
    wx.wxpusher_uid = "UID_x"
    sm._apply_dict({"notification": {"enabled": True}})

    wx2 = next(c for c in sm.notification.channels if c.type == "wxpusher")
    assert wx2.enabled is True
    assert wx2.wxpusher_app_token == "AT_x"
    assert wx2.wxpusher_uid == "UID_x"


def test_notification_empty_channels_keeps_current(tmp_data_dir):
    sm = _fresh(tmp_data_dir)
    before = [(c.type, c.enabled) for c in sm.notification.channels]
    sm._apply_dict({"notification": {"channels": [], "enabled": False}})
    assert [(c.type, c.enabled) for c in sm.notification.channels] == before
    assert sm.notification.enabled is False


def test_partial_ops_patch_keeps_overlays(tmp_data_dir):
    sm = _fresh(tmp_data_dir)
    sm.ops.param_presets["p"] = {"k": "v"}
    sm.ops.installed_at["p"] = "2026-01-01T00:00:00"
    sm.ops.hidden_bundled.append("param-demo")

    sm._apply_dict({"ops": {"enabled": True}})
    assert sm.ops.param_presets == {"p": {"k": "v"}}
    assert sm.ops.installed_at == {"p": "2026-01-01T00:00:00"}
    assert sm.ops.hidden_bundled == ["param-demo"]
    assert sm.ops.enabled is True


def test_partial_feishu_sync_keeps_creds(tmp_data_dir):
    sm = _fresh(tmp_data_dir)
    sm.feishu_sync.app_id = "cli_x"
    sm.feishu_sync.app_secret = "sec"
    sm._apply_dict({"feishu_sync": {"sync_calendar": False}})
    assert sm.feishu_sync.app_id == "cli_x"
    assert sm.feishu_sync.app_secret == "sec"
    assert sm.feishu_sync.sync_calendar is False


def test_partial_pomodoro_keeps_other_fields(tmp_data_dir):
    sm = _fresh(tmp_data_dir)
    sm.pomodoro.daily_goal_pomodoros = 8
    sm.pomodoro.menu_label_format = "自定义"
    sm._apply_dict({"pomodoro": {"duration_minutes": 50}})
    assert sm.pomodoro.duration_minutes == 50
    assert sm.pomodoro.daily_goal_pomodoros == 8
    assert sm.pomodoro.menu_label_format == "自定义"


def test_partial_backup_keeps_dir(tmp_data_dir):
    sm = _fresh(tmp_data_dir)
    sm.backup.dir = "/mnt/bk"
    sm.backup.auto_enabled = True
    sm._apply_dict({"backup": {"keep": 3}})
    assert sm.backup.dir == "/mnt/bk"
    assert sm.backup.auto_enabled is True
    assert sm.backup.keep == 3


def test_partial_save_survives_disk_roundtrip(tmp_data_dir):
    """局部保存落盘重载后，省略字段仍保留。"""
    import json

    from zentray.services import settings_manager as sm_mod

    sm = _fresh(tmp_data_dir)
    sm.backup.auto_enabled = True
    sm.ops.hidden_bundled.append("param-demo")
    sm._apply_dict({"pomodoro": {"duration_minutes": 40}})
    sm.save()

    sm_mod.SETTINGS_FILE.write_text(
        json.dumps(
            {
                "pomodoro": {"duration_minutes": 40},
                "backup": {"auto_enabled": True},
                "ops": {"hidden_bundled": ["param-demo"]},
            }
        ),
        encoding="utf-8",
    )
    SettingsManager._instance = None
    sm2 = SettingsManager()
    assert sm2.pomodoro.duration_minutes == 40
    assert sm2.backup.auto_enabled is True
    assert sm2.ops.hidden_bundled == ["param-demo"]


def test_old_partial_file_still_gets_defaults(tmp_data_dir):
    """老格式文件缺字段仍按默认补齐——迁移行为不变。"""
    import json

    from zentray.services import settings_manager as sm_mod

    sm_mod.SETTINGS_FILE.write_text(
        json.dumps({"pomodoro": {"duration_minutes": 30}}), encoding="utf-8"
    )
    SettingsManager._instance = None
    sm = SettingsManager()
    assert sm.pomodoro.duration_minutes == 30
    assert sm.pomodoro.short_break_minutes == 5
