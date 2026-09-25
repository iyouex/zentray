"""backup 设置节：默认值、钳制/枚举回退、往返持久化。"""
import json

from zentray.services import settings_manager as sm_mod
from zentray.services.settings_manager import SettingsManager


def test_backup_defaults(tmp_data_dir):
    sm = SettingsManager.reload()
    assert sm.backup.dir == ""
    assert sm.backup.auto_enabled is False
    assert sm.backup.interval_days == 1
    assert sm.backup.keep == 7
    assert sm.backup.trigger_hour == 9


def test_backup_invalid_values_clamped(tmp_data_dir):
    sf = sm_mod.SETTINGS_FILE
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(
        json.dumps(
            {
                "backup": {
                    "dir": "  /tmp/bk  ",
                    "auto_enabled": True,
                    "interval_days": 5,  # 非法枚举 → 1
                    "keep": 999,  # → 50
                    "trigger_hour": 24,  # → 23
                }
            }
        ),
        encoding="utf-8",
    )
    sm = SettingsManager.reload()
    assert sm.backup.dir == "/tmp/bk"
    assert sm.backup.auto_enabled is True
    assert sm.backup.interval_days == 1
    assert sm.backup.keep == 50
    assert sm.backup.trigger_hour == 23


def test_backup_trigger_hour_zero_is_valid(tmp_data_dir):
    """0 点是合法钟点，不能被 `or` 兜底吞成默认 9。"""
    sf = sm_mod.SETTINGS_FILE
    sf.parent.mkdir(parents=True, exist_ok=True)
    sf.write_text(
        json.dumps({"backup": {"trigger_hour": 0, "keep": 0}}), encoding="utf-8"
    )
    sm = SettingsManager.reload()
    assert sm.backup.trigger_hour == 0
    assert sm.backup.keep == 1  # clamp 下限


def test_backup_roundtrip(tmp_data_dir):
    sm = SettingsManager.reload()
    sm.backup.dir = "~/backups"
    sm.backup.auto_enabled = True
    sm.backup.interval_days = 7
    sm.backup.keep = 3
    sm.backup.trigger_hour = 0
    sm.save()
    sm2 = SettingsManager.reload()
    assert sm2.backup.dir == "~/backups"
    assert sm2.backup.auto_enabled is True
    assert sm2.backup.interval_days == 7
    assert sm2.backup.keep == 3
    assert sm2.backup.trigger_hour == 0
