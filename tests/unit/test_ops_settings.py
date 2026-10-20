from zentray.services.settings_manager import SettingsManager


def test_ops_defaults(tmp_data_dir):
    sm = SettingsManager()
    assert sm.ops.enabled is False
    assert sm.get_ops_user_plugins_dir().name == "plugins"


def test_ops_roundtrip(tmp_data_dir):
    sm = SettingsManager()
    sm.ops.enabled = True
    sm.save()
    SettingsManager._instance = None
    sm2 = SettingsManager()
    assert sm2.ops.enabled is True


def test_ops_v21_overlay_fields_roundtrip(tmp_data_dir):
    """param_presets / installed_at 往返 + 脏值清洗；旧 trigger_overrides 残键忽略。"""
    import json

    from zentray.services import settings_manager as sm_mod

    sf = sm_mod.SETTINGS_FILE
    sf.write_text(
        json.dumps(
            {
                "ops": {
                    "enabled": True,
                    # 旧调度覆盖层残键：读取时整体忽略（调度已随任务，2026-10-20）
                    "trigger_overrides": {"p1": [{"type": "daily", "time": "08:00"}]},
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
    assert not hasattr(sm.ops, "trigger_overrides")
    assert sm.ops.param_presets == {"p1": {"target": "web", "n": "3"}}
    assert sm.ops.installed_at == {"p1": "2026-09-28T10:00:00"}
    sm.save()
    SettingsManager._instance = None
    sm2 = SettingsManager()
    assert sm2.ops.param_presets == sm.ops.param_presets
    assert sm2.ops.installed_at == sm.ops.installed_at
