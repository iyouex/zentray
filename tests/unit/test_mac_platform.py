# tests/unit/test_mac_platform.py
"""macOS 平台层纯函数单测（Linux 上可跑，darwin 代码全部导入守卫）。

对应 docs/design/mac-interaction-design.md §12 技术落点。
"""
import importlib
import sys
from pathlib import Path

from zentray.services.system_utils import mac_hotkey_parse


def test_mac_tray_module_import_safe_off_darwin():
    # 非 darwin 平台 import 零副作用（PyObjC 全部延迟导入到实例化路径）
    import zentray.ui.mac_tray  # noqa: F401

    assert zentray.ui.mac_tray.MacStatusItemTray is not None


def test_mac_hotkey_parse():
    # ⌥Space（mac 默认）：option 0x0800 + space 49
    assert mac_hotkey_parse("<alt>+<space>") == (0x0800, 49)
    # Linux 默认串在 mac 上也可注册：ctrl|option + t(17)
    assert mac_hotkey_parse("<ctrl>+<alt>+t") == (0x1000 | 0x0800, 17)
    assert mac_hotkey_parse("<cmd>+<shift>+a") == (0x0100 | 0x0200, 0)
    # 裸键拒绝（会吞正常打字）；未映射键/空串/纯修饰键拒绝
    assert mac_hotkey_parse("space") is None
    assert mac_hotkey_parse("<alt>+f13") is None
    assert mac_hotkey_parse("") is None
    assert mac_hotkey_parse("<alt>") is None
    assert mac_hotkey_parse("<ctrl>+<alt>+t+e") is None  # 双键拒绝


def test_launchagent_plist_content():
    from zentray.services.autostart import _launchagent_plist

    xml = _launchagent_plist(
        "/usr/bin/python3 -m zentray.main", "/Users/u/dev/my_todo"
    )
    assert "<string>com.zentray.ZenTray</string>" in xml
    # 命令行按空白拆分为独立 <string>（plist ProgramArguments 语义）
    assert "<string>/usr/bin/python3</string>" in xml
    assert "<string>-m</string>" in xml
    assert "<string>zentray.main</string>" in xml
    assert "<key>RunAtLoad</key>\n    <true/>" in xml
    assert "<string>/Users/u/dev/my_todo</string>" in xml


def test_hotkey_default_per_platform(monkeypatch, tmp_path):
    """HOTKEY_QUICK_ADD 按平台取默认：darwin ⌥Space，其余 Ctrl+Alt+T。

    通过 reload 验证；Path.home 重定向到 tmp，避免模块级 makedirs 污染真实
    home 目录，结束后还原环境再 reload 回真实状态。
    """
    import zentray.config as cfg

    try:
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        monkeypatch.setattr(sys, "platform", "darwin")
        cfg = importlib.reload(cfg)
        assert cfg.HOTKEY_QUICK_ADD == "<alt>+<space>"
        monkeypatch.setattr(sys, "platform", "linux")
        cfg = importlib.reload(cfg)
        assert cfg.HOTKEY_QUICK_ADD == "<ctrl>+<alt>+t"
    finally:
        monkeypatch.undo()
        importlib.reload(cfg)
