"""appearance 新键 motion/shape：默认值、非法值回退、往返持久化（spec §5）。"""
import json

from zentray.services import settings_manager as sm_mod
from zentray.services.settings_manager import SettingsManager

# 注意：SETTINGS_FILE 是模块级变量且被 tmp_data_dir fixture monkeypatch，
# 必须经 sm_mod.SETTINGS_FILE 运行时取属性（reload() 自身会重置 _instance）。


def test_appearance_defaults(tmp_data_dir):
    sm = SettingsManager.reload()
    assert sm.appearance.motion == "full"
    assert sm.appearance.shape == "round"


def test_appearance_invalid_values_fall_back(tmp_data_dir):
    sf = sm_mod.SETTINGS_FILE
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(
        json.dumps({"appearance": {"theme": "dark", "motion": "banana", "shape": 3}}),
        encoding="utf-8",
    )
    sm = SettingsManager.reload()
    assert sm.appearance.motion == "full"
    assert sm.appearance.shape == "round"
    assert sm.appearance.theme == "dark"


def test_appearance_roundtrip(tmp_data_dir):
    sm = SettingsManager.reload()
    sm.appearance.motion = "off"
    sm.appearance.shape = "crisp"
    sm.save()
    sm2 = SettingsManager.reload()
    assert sm2.appearance.motion == "off"
    assert sm2.appearance.shape == "crisp"


def test_appearance_theme_int_dirty_value(tmp_data_dir):
    sf = sm_mod.SETTINGS_FILE
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps({"appearance": {"theme": 42, "motion": "off"}}), encoding="utf-8")
    sm = SettingsManager.reload()
    assert sm.appearance.theme == "system"
    assert sm.appearance.motion == "off"
