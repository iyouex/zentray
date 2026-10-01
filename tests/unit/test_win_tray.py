"""Windows 托盘图标规格解析（icon_paint_spec 纯函数，跨平台可跑）。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication

from zentray.ui.win_tray import icon_paint_spec, paint_tray_pixmap


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
