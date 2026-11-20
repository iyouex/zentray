"""贴边胶囊窗口离屏冒烟（跨平台；不依赖 Windows Shell）。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from zentray.ui.edge_dock import EdgeDock
from zentray.ui.win_edge_tray import _CapsuleWindow, _CapsuleModel, fullscreen_should_hide


def _ensure_qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["zentray-test"])
    if not isinstance(app, QApplication):
        pytest.skip("进程已有 QGuiApplication，无法创建 QWidget")
    return app


def test_model_from_pie_state():
    m = _CapsuleModel()
    m.update("pie_high_62", "编写 Windows 交互设计文档")
    assert m.title == "编写 Windows 交互设计文档"
    assert m.priority == "high" and m.progress == 62
    assert m.timer == ""


def test_model_from_tomato_state():
    m = _CapsuleModel()
    m.update("tomato_40", "14:32 · 写文档")
    assert m.timer == "14:32"
    assert m.title == "专注中"
    assert m.base == "tomato"


def test_model_from_spinner_and_badge():
    m = _CapsuleModel()
    m.update("pie_medium_30", "⚡ 文本工具箱 运行中")
    assert "运行中" in m.meta
    m.update("pie_medium_30", "📄 内存分析报告")
    assert m.meta == "报告待查看"


def test_capsule_paints_and_hit_zones():
    _ensure_qapp()
    d = EdgeDock(1200, 800, "bottom", 0.5)
    w = _CapsuleWindow(d)
    try:
        w.set_content("pie_high_62", "编写 Windows 交互设计文档")
        cap = w._cap_rect
        assert (cap.width(), cap.height()) == (392, 54)
        assert w._zone_at(QPoint(cap.left() + 5, cap.center().y())) == "content"
        assert w._zone_at(QPoint(cap.right() - 5, cap.center().y())) == "system"
        assert w._zone_at(QPoint(cap.center().x(), cap.bottom() - 2)) == "spine"
        assert w._zone_at(QPoint(cap.center().x(), cap.center().y())) == "body"
        # 内侧 margin 也算宽边热区
        assert w._zone_at(QPoint(cap.center().x(), 4)) == "spine"
        pm = w.grab()
        assert not pm.isNull()
    finally:
        w.shutdown()


def test_vertical_hit_zones():
    _ensure_qapp()
    d = EdgeDock(1200, 800, "left", 0.5)
    w = _CapsuleWindow(d)
    try:
        cap = w._cap_rect
        assert (cap.width(), cap.height()) == (54, 348)
        assert w._zone_at(QPoint(cap.center().x(), cap.top() + 5)) == "content"
        assert w._zone_at(QPoint(cap.center().x(), cap.bottom() - 5)) == "system"
        assert w._zone_at(QPoint(cap.left() + 2, cap.center().y())) == "spine"
    finally:
        w.shutdown()


def test_model_detail_task_fields():
    m = _CapsuleModel()
    m.update_detail(
        {
            "title": "写文档",
            "category": "工作",
            "priority": "high",
            "subs_done": 3,
            "subs_total": 5,
            "deadline": "2026-11-22",
            "progress": 60,
            "phase": "idle",
        }
    )
    assert m.title == "写文档"
    assert m.meta == "工作 · 子任务 3/5 · 截止 2026-11-22"
    assert (m.priority, m.progress, m.timer, m.base) == ("high", 60, "", "app")


def test_model_detail_focus_and_break():
    m = _CapsuleModel()
    m.update_detail(
        {"title": "写文档", "phase": "focus", "timer": "24:32", "progress": 30, "meta": "专注中", "priority": "high"}
    )
    assert (m.base, m.timer, m.meta) == ("tomato", "24:32", "专注中")
    m.update_detail({"title": "休息一下", "phase": "short_break", "timer": "05:00", "progress": 80, "meta": "休息中", "priority": "low"})
    assert (m.base, m.timer, m.priority) == ("break", "05:00", "low")


def test_model_detail_progress_clamped():
    m = _CapsuleModel()
    m.update_detail({"title": "x", "progress": 150})
    assert m.progress == 100
    m.update_detail({"title": "x", "progress": -5})
    assert m.progress == 0


def test_click_zones_emit_signals():
    _ensure_qapp()
    d = EdgeDock(1200, 800, "bottom", 0.5)
    w = _CapsuleWindow(d)
    try:
        w.set_content("pie_high_62", "写文档")
        cap = w._cap_rect
        events = []
        w.content_clicked.connect(lambda p: events.append("content"))
        w.system_clicked.connect(lambda p: events.append("system"))
        w.spine_clicked.connect(lambda p: events.append("spine"))
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(cap.left() + 5, cap.center().y()))
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(cap.right() - 5, cap.center().y()))
        QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(cap.center().x(), cap.bottom() - 2))
        assert events == ["content", "system", "spine"]
    finally:
        w.shutdown()


def test_long_press_starts_drag_and_snap():
    _ensure_qapp()
    d = EdgeDock(1200, 800, "bottom", 0.5)
    w = _CapsuleWindow(d)
    try:
        w.set_content("pie_high_62", "写文档")
        cap = w._cap_rect
        QTest.mousePress(w, Qt.MouseButton.LeftButton, pos=QPoint(cap.center().x(), cap.bottom() - 2))
        QTest.qWait(480)
        assert w._dragging is True
        ov = w._overlay
        assert ov is not None
        # 覆盖层是整屏（offscreen 800×800）；移到顶部中间再松手
        QTest.mouseMove(ov, QPoint(400, 80))
        QTest.mouseRelease(ov, Qt.MouseButton.LeftButton, pos=QPoint(400, 80))
        QTest.qWait(120)
        assert w._dragging is False
        assert w._dock.edge == "top"
    finally:
        w.shutdown()


def test_fullscreen_state_mapping():
    # QUNS_RUNNING_D3D_FULL_SCREEN=3 / PRESENTATION_MODE=4
    assert fullscreen_should_hide(3) is True
    assert fullscreen_should_hide(4) is True
    assert fullscreen_should_hide(1) is False
    assert fullscreen_should_hide(5) is False
    assert fullscreen_should_hide(None) is False


def test_capsule_reports_screen_and_repositions():
    _ensure_qapp()
    d = EdgeDock(1200, 800, "bottom", 0.5)
    w = _CapsuleWindow(d)
    try:
        assert w.screen() is not None
        assert isinstance(w.screen_name(), str)
        w.reposition()
        assert w._dock.area_w > 0 and w._dock.area_h > 0
    finally:
        w.shutdown()


def test_edge_tray_capsule_and_flyout_wiring():
    """实际后端装配：tray → capsule → 窄边 flyout（离屏）。"""
    app = _ensure_qapp()
    from zentray.ui.win_edge_tray import WindowsEdgeTray

    class _Provider:
        def flyout_snapshot(self):
            return {
                "tasks": [
                    {"id": "t1", "title": "写文档", "priority": "high", "deadline": None, "current": True}
                ],
                "plugins": [{"id": "p1", "name": "文本工具箱", "busy": False}],
            }

        def flyout_select_task(self, task_id):
            pass

        def flyout_open_tasks(self):
            pass

        def flyout_open_plugins(self):
            pass

        def flyout_action(self, action_id):
            pass

    tray = WindowsEdgeTray(app)
    tray._enabled = lambda: True
    try:
        tray.set_flyout_provider(_Provider())
        tray.set_state("pie_high_62", "写文档")
        tray.set_detail({"title": "写文档", "category": "工作", "priority": "high", "progress": 60})
        assert tray.capsule is not None
        assert tray._fs_timer.isActive()
        tray._on_content(QPoint(0, 0))
        assert tray._flyout is not None
        assert type(tray._flyout).__name__ == "TaskPluginFlyout"
        assert tray.capsule._idle_enabled is False
        tray._on_system(QPoint(0, 0))
        assert type(tray._flyout).__name__ == "SystemFlyout"
        tray._close_flyout()
        assert tray.capsule._idle_enabled is True
        hits = []
        tray.show_event("测试事件", on_click=lambda: hits.append(1))
        assert tray._event is not None
        tray._event.clicked.emit()
        assert hits == [1]
    finally:
        tray.shutdown()


def test_compact_ear_geometry_and_paint():
    _ensure_qapp()
    d = EdgeDock(1200, 800, "bottom", 0.75)
    w = _CapsuleWindow(d)
    try:
        w.set_content("pie_high_62", "写文档")
        w.set_compact(True)
        cap = w._cap_rect
        assert (cap.width(), cap.height()) == (168, 44)
        assert not w.grab().isNull()
        w.set_compact(False)
        assert w._cap_rect.width() == 392
    finally:
        w.shutdown()


def test_maybe_compact_respects_pomodoro():
    _ensure_qapp()
    d = EdgeDock(1200, 800, "bottom", 0.5)
    w = _CapsuleWindow(d)
    try:
        w.set_content("pie_high_62", "写文档")
        w._hover = False
        w._idle_enabled = True
        w._model.timer = ""
        w._maybe_compact()
        assert w._dock.compact is True
        w.set_compact(False)
        w._model.timer = "24:32"
        w._maybe_compact()
        assert w._dock.compact is False
    finally:
        w.shutdown()


def test_event_pill_paint_and_click():
    _ensure_qapp()
    from zentray.ui.win_edge_tray import _EventPill

    p = _EventPill()
    hits = []
    p.clicked.connect(lambda: hits.append(1))
    try:
        p.show_event("📄 内存分析报告已生成", (10, 10, 300, 38))
        assert not p.grab().isNull()
        QTest.mouseClick(p, Qt.MouseButton.LeftButton, pos=QPoint(10, 10))
        assert hits == [1]
        assert not p.isVisible()
    finally:
        p._timer.stop()
        p.close()


def test_capsule_light_theme_renders():
    _ensure_qapp()
    d = EdgeDock(1200, 800, "bottom", 0.5)
    w = _CapsuleWindow(d)
    try:
        w.set_content("pie_high_62", "写文档")
        w.set_light(False)
        dark = w.grab().toImage().pixelColor(w._cap_rect.left() + 5, w._cap_rect.center().y()).lightness()
        w.set_light(True)
        light = w.grab().toImage().pixelColor(w._cap_rect.left() + 5, w._cap_rect.center().y()).lightness()
        assert light > dark
        assert light > 160
    finally:
        w.shutdown()


def test_event_pill_light_renders():
    _ensure_qapp()
    from zentray.ui.win_edge_tray import _EventPill

    p = _EventPill()
    try:
        p.show_event("📄 报告已生成", (10, 10, 300, 38), light=True)
        img = p.grab().toImage()
        assert not img.isNull()
        assert img.pixelColor(150, 30).lightness() > 120
    finally:
        p._timer.stop()
        p.close()


def test_system_is_light_returns_bool():
    _ensure_qapp()
    from zentray.ui.win_edge_tray import WindowsEdgeTray

    assert isinstance(WindowsEdgeTray._system_is_light(), bool)


def test_edge_tray_apply_settings_hot():
    """设置页保存 → 后端热应用边/位置/收纳/长按/多屏。"""
    app = _ensure_qapp()
    from types import SimpleNamespace
    from zentray.ui.win_edge_tray import WindowsEdgeTray

    tray = WindowsEdgeTray(app)
    orig = WindowsEdgeTray._appearance
    try:
        tray.set_state("pie_high_62", "写文档")
        fake = SimpleNamespace(
            win_tray_enabled=True,
            win_tray_edge="top",
            win_tray_ratio=0.5,
            win_tray_idle_sec=12,
            win_tray_longpress_ms=300,
            win_tray_hide_fullscreen=False,
            win_tray_monitor="all",
        )
        WindowsEdgeTray._appearance = staticmethod(lambda: fake)
        tray.apply_settings()
        cap = tray.capsule
        assert cap is not None
        assert cap._dock.edge == "top"
        assert abs(cap._dock.ratio - 0.5) < 1e-6
        assert cap._idle_timer.interval() == 12000
        assert cap._long_timer.interval() == 300
        assert cap._multi_monitor is True
    finally:
        WindowsEdgeTray._appearance = orig
        tray.shutdown()
