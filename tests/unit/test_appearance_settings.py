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
    assert sm.appearance.skin == "neo"


def test_appearance_invalid_values_fall_back(tmp_data_dir):
    sf = sm_mod.SETTINGS_FILE
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(
        json.dumps({"appearance": {"theme": "dark", "motion": "banana", "shape": 3, "skin": "glass"}}),
        encoding="utf-8",
    )
    sm = SettingsManager.reload()
    assert sm.appearance.motion == "full"
    assert sm.appearance.shape == "round"
    assert sm.appearance.skin == "neo"
    assert sm.appearance.theme == "dark"


def test_appearance_roundtrip(tmp_data_dir):
    sm = SettingsManager.reload()
    sm.appearance.motion = "off"
    sm.appearance.shape = "crisp"
    sm.appearance.skin = "aurora"
    sm.save()
    sm2 = SettingsManager.reload()
    assert sm2.appearance.motion == "off"
    assert sm2.appearance.shape == "crisp"
    assert sm2.appearance.skin == "aurora"

def test_appearance_new_skins_roundtrip(tmp_data_dir):
    """synth/clay 新皮肤：合法入名单，持久化往返不丢。"""
    for skin in ("synth", "clay"):
        sm = SettingsManager.reload()
        sm.appearance.skin = skin
        sm.save()
        sm2 = SettingsManager.reload()
        assert sm2.appearance.skin == skin


def test_appearance_theme_int_dirty_value(tmp_data_dir):
    sf = sm_mod.SETTINGS_FILE
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(json.dumps({"appearance": {"theme": 42, "motion": "off"}}), encoding="utf-8")
    sm = SettingsManager.reload()
    assert sm.appearance.theme == "system"
    assert sm.appearance.motion == "off"


def test_win_tray_defaults(tmp_data_dir):
    sm = SettingsManager.reload()
    a = sm.appearance
    assert a.win_tray_enabled is True
    assert a.win_tray_edge == "bottom"
    assert a.win_tray_ratio == 0.75
    assert a.win_tray_form == "capsule"
    assert a.win_tray_hover_ms == 180
    assert a.win_tray_idle_sec == 8
    assert a.win_tray_longpress_ms == 400
    assert a.win_tray_hide_fullscreen is True
    assert a.win_tray_monitor == "primary"


def test_win_tray_roundtrip_and_clamp(tmp_data_dir):
    sm = SettingsManager.reload()
    sm.appearance.win_tray_edge = "left"
    sm.appearance.win_tray_ratio = 0.4
    sm.appearance.win_tray_monitor = "all"
    sm.appearance.win_tray_idle_sec = 12
    sm.save()
    sm2 = SettingsManager.reload()
    assert sm2.appearance.win_tray_edge == "left"
    assert sm2.appearance.win_tray_ratio == 0.4
    assert sm2.appearance.win_tray_monitor == "all"
    assert sm2.appearance.win_tray_idle_sec == 12

    sf = sm_mod.SETTINGS_FILE
    sf.write_text(
        json.dumps(
            {
                "appearance": {
                    "win_tray_edge": "middle",
                    "win_tray_ratio": 2,
                    "win_tray_monitor": "x",
                    "win_tray_longpress_ms": 99999,
                }
            }
        ),
        encoding="utf-8",
    )
    sm3 = SettingsManager.reload()
    assert sm3.appearance.win_tray_edge == "bottom"
    assert sm3.appearance.win_tray_ratio == 1.0
    assert sm3.appearance.win_tray_monitor == "primary"
    assert sm3.appearance.win_tray_longpress_ms == 1500
