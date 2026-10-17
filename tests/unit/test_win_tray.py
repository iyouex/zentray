"""Windows 托盘图标规格解析（icon_paint_spec 纯函数，跨平台可跑）。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication

from zentray.ui.win_tray import (
    _StatusStripWindow,
    icon_paint_spec,
    paint_tray_pixmap,
)


def setup_module():
    # QPixmap 绘制需要 QGuiApplication 先行（离屏）
    if QGuiApplication.instance() is None:
        QGuiApplication(["zentray-test"])


def test_pie_parse():
    s = icon_paint_spec("pie_high_60", "任务标题")
    assert s["base"] == "pie" and s["priority"] == "high" and s["progress"] == 60
    assert not s["spinner"] and not s["badge"]


def test_pie_progress_clamped():
    assert icon_paint_spec("pie_high_120", "")["progress"] == 100
    assert icon_paint_spec("pie_low_00", "")["progress"] == 0


def test_tomato_countdown_minutes_ceil():
    s = icon_paint_spec("tomato_40", "14:32 · 写文档", countdown_on=True)
    assert s["base"] == "tomato" and s["progress"] == 40
    assert s["minutes"] == 15  # 向上取整


def test_break_countdown_exact_minute():
    assert icon_paint_spec("break_30", "05:00", countdown_on=True)["minutes"] == 5


def test_countdown_off_or_no_prefix():
    assert icon_paint_spec("tomato_40", "14:32")["minutes"] is None
    assert icon_paint_spec("tomato_40", "专注中", countdown_on=True)["minutes"] is None


def test_text_prefixes_apply_to_any_base():
    # 轮播期 icon 仍是 pie_*，⚡/📄 由文案前缀表达
    assert icon_paint_spec("pie_none_0", "⚡ 插件运行中")["spinner"]
    assert icon_paint_spec("pie_none_0", "📄 报告待查看")["badge"]
    assert icon_paint_spec("app_icon", "⚡ 运行中")["spinner"]


def test_app_icon_fallback():
    s = icon_paint_spec("", "")
    assert s["base"] == "app" and s["progress"] == 0


def test_paint_tray_pixmap_returns_pixmap():
    for spec in (
        icon_paint_spec("pie_high_60", ""),
        icon_paint_spec("tomato_40", "14:32", countdown_on=True),
        icon_paint_spec("app_icon", "📄 待看"),
    ):
        pm = paint_tray_pixmap(spec, "")
        assert pm is not None and not pm.isNull()


# —— 状态条（§3.0，2026-10-17 重设计）——

def _qt_app_or_skip():
    # QWidget 需 QApplication；本模块 setup_module 先建 QGuiApplication 时无法升级
    import pytest
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return QApplication(["zentray-test"])
    if not isinstance(app, QApplication):
        pytest.skip("进程已有 QGuiApplication（本模块 setup_module 先建），无法升级")
    return app


def test_status_strip_window_never_self_activates():
    # v0.7.13 Windows 狂闪教训：顶层窗口 show() 自我激活 → ActivationChange
    # 死循环。状态条必须带 WA_ShowWithoutActivating（仅映射 SW_SHOWNOACTIVATE，
    # 不设 WS_EX_NOACTIVATE）。
    from PySide6.QtCore import Qt

    _qt_app_or_skip()
    w = _StatusStripWindow()
    assert w.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    w.close()


def test_status_strip_content_and_marquee_timer():
    # 超宽 + 跑马灯 → 定时器启动；短文本/关闭跑马灯 → 定时器停止
    _qt_app_or_skip()
    w = _StatusStripWindow()
    w.set_content(None, "短标题", True)
    assert not w._timer.isActive()  # 不超宽不滚
    w.resize(120, 30)
    w.set_content(None, "[工作-需求B] 编写交互设计文档与原型图评审", True)
    assert w._timer.isActive()
    w.set_content(None, "[工作-需求B] 编写交互设计文档与原型图评审", False)
    assert not w._timer.isActive()
    assert w._text == "[工作-需求B] 编写交互设计文档与原型图评审"
    w.close()


def test_statusbar_settings_parse_and_migrate(tmp_path, monkeypatch):
    from zentray.services import settings_manager as sm

    f = tmp_path / "settings.json"
    monkeypatch.setattr(sm, "SETTINGS_FILE", f)
    sm.SettingsManager.reload()
    mgr = sm.SettingsManager()
    assert mgr.appearance.statusbar_enabled is True
    assert mgr.appearance.statusbar_marquee is False
    # 旧键（中央按钮方案）盘上迁移：合并前改名，否则被基线新键遮蔽
    f.write_text(
        '{"appearance": {"taskbar_center_enabled": false, "taskbar_label_marquee": true}}',
        encoding="utf-8",
    )
    sm.SettingsManager.reload()
    migrated = sm.SettingsManager()
    assert migrated.appearance.statusbar_enabled is False
    assert migrated.appearance.statusbar_marquee is True
    # 新键直读
    f.write_text(
        '{"appearance": {"statusbar_enabled": true, "statusbar_marquee": false}}',
        encoding="utf-8",
    )
    sm.SettingsManager.reload()
    fresh = sm.SettingsManager()
    assert fresh.appearance.statusbar_enabled is True
    assert fresh.appearance.statusbar_marquee is False
