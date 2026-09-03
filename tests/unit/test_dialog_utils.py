"""弹窗默认居中 + 拖拽标记。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QPushButton

from zentray.ui.dialog_utils import (
    apply_dialog_chrome,
    center_dialog,
    is_interactive_widget,
    mark_dialog_moved,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["zentray-test"])
    return app


def test_center_dialog_places_on_available_screen_center(qapp):
    dlg = QDialog()
    dlg.setFixedSize(400, 200)
    center_dialog(dlg)

    screen = qapp.primaryScreen()
    geo = screen.availableGeometry()
    assert dlg.x() == geo.x() + (geo.width() - 400) // 2
    assert dlg.y() == geo.y() + (geo.height() - 200) // 2
    dlg.deleteLater()


def test_center_dialog_skips_after_user_move(qapp):
    dlg = QDialog()
    dlg.setFixedSize(400, 200)
    center_dialog(dlg)
    dlg.move(12, 34)
    mark_dialog_moved(dlg)
    center_dialog(dlg)
    assert dlg.pos().x() == 12
    assert dlg.pos().y() == 34
    dlg.deleteLater()


def test_apply_dialog_chrome_frameless_dialog_and_drag_filter(qapp):
    dlg = QDialog()
    apply_dialog_chrome(dlg, width=480, height=320)

    flags = dlg.windowFlags()
    assert flags & Qt.FramelessWindowHint
    assert flags & Qt.Dialog
    assert dlg.width() == 480
    assert dlg.height() == 320
    assert getattr(dlg, "_drag_filter", None) is not None
    dlg.deleteLater()


def test_apply_dialog_chrome_stay_on_top_and_tool(qapp):
    dlg = QDialog()
    apply_dialog_chrome(dlg, width=200, height=80, stay_on_top=True, tool=True)
    flags = dlg.windowFlags()
    assert flags & Qt.WindowStaysOnTopHint
    assert flags & Qt.Tool
    dlg.deleteLater()


def test_is_interactive_widget_buttons_not_labels(qapp):
    dlg = QDialog()
    btn = QPushButton("ok", dlg)
    label = QLabel("title", dlg)
    assert is_interactive_widget(btn) is True
    assert is_interactive_widget(label) is False
    dlg.deleteLater()


def test_child_show_does_not_recenter_after_user_move(qapp):
    dlg = QDialog()
    apply_dialog_chrome(dlg, width=400, height=200)
    label = QLabel("x", dlg)
    mark_dialog_moved(dlg)
    dlg.move(20, 40)
    label.show()
    qapp.processEvents()
    assert dlg.x() == 20
    assert dlg.y() == 40
    dlg.deleteLater()


def test_drag_filter_no_reference_cycle(qapp):
    """弹窗关闭后必须可被引用计数立即回收。

    若 _drag_filter 与 dialog 互持强引用成环，只能靠 cyclic GC 在任意线程
    （HTTP 处理线程）析构 Qt 对象，曾导致 WebEngine 线程断言崩溃。
    """
    import gc
    import weakref

    dlg = QDialog()
    apply_dialog_chrome(dlg, width=400, height=200)
    # 先让 schedule_center 的 0/30/100ms 定时器触发完（它们短暂持有 dialog 引用）
    from PySide6.QtCore import QEventLoop, QTimer as _QTimer

    loop = QEventLoop()
    _QTimer.singleShot(150, loop.quit)
    loop.exec()
    ref = weakref.ref(dlg)
    del dlg
    gc.collect()
    assert ref() is None


def test_open_vue_route_schedules_delete_later():
    """WebEngine 弹窗必须走 deleteLater，在主线程确定性析构。"""
    from pathlib import Path
    import zentray.ui.web_host as web_host

    src = Path(web_host.__file__).read_text(encoding="utf-8")
    assert "dlg.deleteLater()" in src
