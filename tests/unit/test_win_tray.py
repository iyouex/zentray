"""Windows 托盘图标规格解析（icon_paint_spec 纯函数，跨平台可跑）。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QGuiApplication

from zentray.ui.win_tray import (
    icon_paint_spec,
    paint_tray_pixmap,
    taskbar_label,
    taskbar_label_visible,
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


# —— 任务栏中央按钮（§3.0）——

def test_taskbar_label_short_passthrough():
    assert taskbar_label("写文档", 20) == "写文档"
    assert taskbar_label("", 20) == "ZenTray"


def test_taskbar_label_truncate_with_ellipsis():
    t = "[工作-需求B] 编写交互设计文档与原型图评审"
    out = taskbar_label(t, 20)
    assert len(out) == 20 and out.endswith("…") and out.startswith(t[:19])


def test_taskbar_label_length_clamped():
    # 钳制到 8-32：超范围参数不炸、结果长度合法
    out = taskbar_label("x" * 100, 999)
    assert len(out) == 32
    assert len(taskbar_label("x" * 100, 2)) == 8


def test_taskbar_label_marquee_scroll():
    t = "这是一个非常长的任务标题需要跑马灯滚动展示"
    first = taskbar_label(t, 12)
    assert first.endswith("…")  # offset=0 截断
    second = taskbar_label(t, 12, 1)
    assert len(second) == 12 and second != first


def test_taskbar_label_visible_none_offscreen_linux():
    # 非 Windows 探测不到 → None（前端隐藏提示行）
    import sys

    if not sys.platform.startswith("win32"):
        assert taskbar_label_visible() is None


def test_taskbar_center_settings_parse_and_clamp(tmp_path, monkeypatch):
    from zentray.services import settings_manager as sm

    monkeypatch.setattr(sm, "SETTINGS_FILE", tmp_path / "settings.json")
    sm.SettingsManager.reload()
    mgr = sm.SettingsManager()
    assert mgr.appearance.taskbar_center_enabled is True
    assert mgr.appearance.taskbar_label_length == 20
    assert mgr.appearance.taskbar_label_marquee is False
    mgr._apply_dict(
        {
            "appearance": {
                "taskbar_center_enabled": False,
                "taskbar_label_length": 99,
                "taskbar_label_marquee": True,
            }
        }
    )
    assert mgr.appearance.taskbar_center_enabled is False
    assert mgr.appearance.taskbar_label_length == 32  # 钳到上限
    assert mgr.appearance.taskbar_label_marquee is True
