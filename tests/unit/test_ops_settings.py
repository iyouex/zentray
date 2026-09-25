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
