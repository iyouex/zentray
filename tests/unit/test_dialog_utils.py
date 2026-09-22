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


def test_chrome_dialog_records_fixed_size(qapp):
    """apply_dialog_chrome 必须记录固定尺寸，供 Resize 守卫恢复合成器越权改小。"""
    dlg = QDialog()
    apply_dialog_chrome(dlg, width=500, height=300)
    assert getattr(dlg, "_chrome_size", None) == (500, 300)


def test_resize_guard_restores_fixed_size_after_platform_override(qapp):
    """混合 DPI 多屏最小化恢复时，Wayland configure 会绕过 min/max 把窗口折半（实测 900x540→450x270）。

    模拟方式：放开 min/max 限制后把窗口 resize 到偏小尺寸（等价于合成器越权），
    Resize 守卫应通过 hide→resize→show 在 ~120ms 内恢复固定尺寸。
    """
    from PySide6.QtCore import QEvent, QEventLoop, QSize, QTimer
    from PySide6.QtGui import QResizeEvent

    dlg = QDialog()
    apply_dialog_chrome(dlg, width=400, height=200)
    dlg.show()

    # 等初始多阶段居中定时器跑完
    loop = QEventLoop()
    QTimer.singleShot(150, loop.quit)
    loop.exec()

    # 模拟合成器越权：放开约束 + 直接改小 + 直接调 eventFilter
    # （offscreen 平台不向顶层窗口投递 Resize 事件，故不走 sendEvent；真实 Wayland 已验证会送达）
    dlg.setMinimumSize(QSize(1, 1))
    dlg.setMaximumSize(QSize(4096, 4096))
    dlg.resize(200, 100)
    dlg._drag_filter.eventFilter(dlg, QResizeEvent(QSize(200, 100), QSize(400, 200)))

    loop2 = QEventLoop()
    QTimer.singleShot(300, loop2.quit)
    loop2.exec()

    assert dlg.size() == QSize(400, 200), "Resize 守卫未恢复固定尺寸"
    assert dlg.isVisible(), "恢复后窗口应重新显示"


def test_chrome_dialog_is_resizable_not_fixed(qapp):
    """mutter 只对固定尺寸(min==max)窗口在最小化恢复时下发带尺寸 configure（单位错误，
    实测 900x540→450x270 折半且客户端 resize 被无视）。chrome 必须保持可拉伸分类。"""
    dlg = QDialog()
    apply_dialog_chrome(dlg, width=500, height=300)
    assert dlg.minimumWidth() == 500 and dlg.minimumHeight() == 300
    assert dlg.maximumWidth() > 500, "max==min 会被 mutter 视为固定尺寸窗口（恢复折半根源）"
    assert dlg.maximumHeight() > 300
    assert (dlg.width(), dlg.height()) == (500, 300), "初始仍应为设计尺寸"
    dlg.deleteLater()


def test_resize_guard_ignores_user_enlarge(qapp):
    """现在允许用户拉伸窗口：守卫只恢复“变小”（合成器 bug 特征），拉大必须放行。"""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QResizeEvent

    dlg = QDialog()
    apply_dialog_chrome(dlg, width=400, height=200)
    dlg.show()
    dlg._drag_filter.eventFilter(dlg, QResizeEvent(QSize(600, 400), QSize(400, 200)))
    assert getattr(dlg, "_chrome_resize_total", 0) == 0, "用户拉大触发了恢复"
    dlg.deleteLater()


def test_resize_guard_total_recovery_cap(qapp):
    """两个并存弹窗的尺寸恢复会互相触发合成器 configure（无限减半拉锯）。

    守卫必须有总量硬上限：超过 4 次恢复后停止重建，窗口宁可保持当前尺寸也不得狂闪。
    """
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QResizeEvent

    dlg = QDialog()
    apply_dialog_chrome(dlg, width=400, height=200)
    dlg.setMinimumSize(QSize(1, 1))
    dlg.setMaximumSize(QSize(4096, 4096))
    dlg.resize(200, 100)

    ev = QResizeEvent(QSize(200, 100), QSize(400, 200))
    for _ in range(6):
        dlg._drag_filter.eventFilter(dlg, ev)

    total = getattr(dlg, "_chrome_resize_total", 0)
    assert total == 5, f"恢复总量应停在 5（4 次恢复 + 1 次告警），实际 {total}"
    dlg.deleteLater()


def test_resize_guard_total_resets_after_normal_size(qapp):
    """total 是“每轮连续异常”的计数，不能按面板生命周期累计：
    合成器每次最小化都会发一次减半 configure（实测），生命周期累计配额
    会让两轮最小化后就永久保持减半——“页面还是会缩小”的根因之一。"""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QResizeEvent

    dlg = QDialog()
    apply_dialog_chrome(dlg, width=400, height=200)
    dlg.setMinimumSize(QSize(1, 1))
    dlg.setMaximumSize(QSize(4096, 4096))
    dlg.resize(200, 100)

    ev_shrink = QResizeEvent(QSize(200, 100), QSize(400, 200))
    dlg._drag_filter.eventFilter(dlg, ev_shrink)  # 第 1 轮减半恢复
    assert getattr(dlg, "_chrome_resize_total", 0) == 1

    # 守卫恢复后尺寸回归正常 → 计数必须复位
    dlg.resize(400, 200)
    dlg._drag_filter.eventFilter(dlg, QResizeEvent(QSize(400, 200), QSize(200, 100)))
    assert getattr(dlg, "_chrome_resize_total", 0) == 0, "恢复正常后 total 未复位"

    # 下一轮最小化再减半，仍应正常恢复，不被历史累计卡死
    dlg.resize(200, 100)
    dlg._drag_filter.eventFilter(dlg, ev_shrink)
    assert getattr(dlg, "_chrome_resize_total", 0) == 1, "新一轮减半被历史配额误杀"
    dlg.deleteLater()


def test_run_modal_loop_survives_transient_window_hide(qapp):
    """Resize 守卫恢复混合 DPI 缩小时必须临时 unmap QWindow；exec() 会被该隐藏
    以 Rejected 打断（最小化后对话框凭空消失的根因）。

    run_modal_loop 只在 finished 信号时退出：临时隐藏后对话框必须仍存活，
    直到真正的 reject() 才返回。
    """
    from PySide6.QtCore import QElapsedTimer, QTimer
    from zentray.ui.dialog_utils import run_modal_loop

    dlg = QDialog()
    apply_dialog_chrome(dlg, width=400, height=200)
    dlg.show()
    qapp.processEvents()

    def transient_hide():
        h = dlg.windowHandle()
        h.setVisible(False)
        dlg.resize(400, 200)
        h.setVisible(True)

    QTimer.singleShot(120, transient_hide)
    QTimer.singleShot(400, dlg.reject)

    t = QElapsedTimer()
    t.start()
    ok = run_modal_loop(dlg)
    assert ok is False
    assert dlg.result() == QDialog.DialogCode.Rejected
    assert t.elapsed() >= 350, "模态循环被临时隐藏提前打断（exec() 的致命行为）"
    dlg.deleteLater()


def test_run_modal_loop_accept_returns_true(qapp):
    from PySide6.QtCore import QTimer
    from zentray.ui.dialog_utils import run_modal_loop

    dlg = QDialog()
    apply_dialog_chrome(dlg, width=400, height=200)
    QTimer.singleShot(150, dlg.accept)
    assert run_modal_loop(dlg) is True
    dlg.deleteLater()


def test_is_interactive_widget_window_type_check(qapp):
    """Qt.Tool 是复合标志（含 Dialog 位），windowFlags() & Tool 对任何对话框恒真。

    历史缺陷：该误判使 DialogDragFilter 从未装到 chrome 对话框自身，
    Show 居中与 Resize 守卫全部失效。必须用 windowType() 精确判定。
    """
    from zentray.ui.dialog_utils import is_interactive_widget

    dlg = QDialog()
    apply_dialog_chrome(dlg, width=400, height=200)
    assert is_interactive_widget(dlg) is False, "chrome 对话框被误判为交互控件"
    assert dlg._drag_filter is not None

    # 真正的 Tool 窗口（如闪电添加浮层）仍应视为交互式
    tool_dlg = QDialog()
    tool_dlg.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
    assert is_interactive_widget(tool_dlg) is True

