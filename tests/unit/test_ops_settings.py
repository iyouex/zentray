from zentray.services.settings_manager import SettingsManager


def test_ops_defaults(tmp_data_dir):
    sm = SettingsManager()
    assert sm.ops.enabled is False
    assert sm.ops.confirm_before_run is True
    assert sm.get_ops_user_plugins_dir().name == "plugins"


def test_ops_roundtrip(tmp_data_dir):
    sm = SettingsManager()
    sm.ops.enabled = True
    sm.save()
    SettingsManager._instance = None
    sm2 = SettingsManager()
    assert sm2.ops.enabled is True


def test_ops_v21_overlay_fields_roundtrip(tmp_data_dir):
    """trigger_overrides / param_presets / installed_at 往返 + 脏值清洗。"""
    import json

    from zentray.services import settings_manager as sm_mod

    sf = sm_mod.SETTINGS_FILE
    sf.write_text(
        json.dumps(
            {
                "ops": {
                    "enabled": True,
                    "trigger_overrides": {
                        "p1": [{"type": "daily", "time": "08:00"}, "junk"],
                        "bad": "not-a-list",
                    },
                    "param_presets": {
                        "p1": {"target": "web", "n": 3},
                        "bad": "not-a-dict",
                    },
                    "installed_at": {"p1": "2026-09-28T10:00:00"},
                }
            }
        ),
        encoding="utf-8",
    )
    SettingsManager._instance = None
    sm = SettingsManager()
    assert sm.ops.trigger_overrides == {
        "p1": [{"type": "daily", "time": "08:00"}]
    }  # 非法条目/非列表键整体剔除
    assert sm.ops.param_presets == {"p1": {"target": "web", "n": "3"}}
    assert sm.ops.installed_at == {"p1": "2026-09-28T10:00:00"}
    sm.save()
    SettingsManager._instance = None
    sm2 = SettingsManager()
    assert sm2.ops.trigger_overrides == sm.ops.trigger_overrides
    assert sm2.ops.param_presets == sm.ops.param_presets
    assert sm2.ops.installed_at == sm.ops.installed_at
