# zentray/ui/dialog_utils.py
"""对话框通用布局：横版优先、适配屏幕、按钮文字完整显示。"""
from __future__ import annotations

import logging
import weakref

from PySide6.QtCore import Qt, QSize, QObject, QEvent, QPoint, QTimer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QAbstractButton,
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QSlider,
    QScrollBar,
    QAbstractItemView,
    QTabBar,
    QMenu,
    QCalendarWidget,
)

logger = logging.getLogger(__name__)


def is_interactive_widget(widget: QObject | None) -> bool:
    """判断控件是否为按钮、输入框、下拉框、弹出菜单等交互式控件。"""
    if not widget or not isinstance(widget, QWidget):
        return False
    if isinstance(
        widget,
        (
            QAbstractButton,
            QAbstractSpinBox,
            QComboBox,
            QLineEdit,
            QTextEdit,
            QPlainTextEdit,
            QSlider,
            QScrollBar,
            QAbstractItemView,
            QTabBar,
            QMenu,
            QCalendarWidget,
        ),
    ):
        return True

    # 窗口类型判定必须用 windowType()：Qt.Tool 是复合标志（Dialog|Popup 位置叠加），
    # windowFlags() & Qt.Tool 对任何 Dialog 窗口恒非零 —— 那样所有对话框都会被误判为
    # 交互控件，拖拽过滤器装不到对话框自身（Show 居中与 Resize 守卫全部失效）
    wt = widget.windowType()
    if wt == Qt.WindowType.Popup or wt == Qt.WindowType.Tool:
        return True

    classname = widget.metaObject().className()
    interactive_keywords = [
        "Button",
        "Edit",
        "Combo",
        "Spin",
        "Slider",
        "Scroll",
        "View",
        "List",
        "Tree",
        "Table",
        "Calendar",
        "WebEngine",
        "Menu",
        "Popup",
        "Dropdown",
        "Item",
    ]
    return any(k in classname for k in interactive_keywords)


class DialogDragFilter(QObject):
    """通用弹窗拖拽过滤器（支持 Wayland / X11 / Windows 原生系统级拖拽与物理拖拽）。"""

    def __init__(self, dialog: QDialog):
        super().__init__(dialog)
        # weakref：强引用会与 dialog._drag_filter 成环，只能被 cyclic GC 在任意线程
        # （如 HTTP 处理线程）回收，导致 QDialog/WebEngine 在错误线程析构而崩溃
        self._dialog_ref = weakref.ref(dialog)
        self.drag_pos = None

    @property
    def dialog(self) -> QDialog | None:
        return self._dialog_ref()

    def install_recursive(self, target: QObject) -> None:
        if not target:
            return
        try:
            if not is_interactive_widget(target):
                target.installEventFilter(self)
            for child in target.findChildren(QWidget):
                if not is_interactive_widget(child):
                    child.installEventFilter(self)
        except Exception:
            pass

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # PySide6 6.11：经窗口系统投递的部分事件包装上 event.type() 会抛
        # AttributeError（实测 QEnterEvent），必须防御，否则每次鼠标进入弹窗都打异常
        try:
            etype = event.type()
        except AttributeError:
            return False
        if etype == QEvent.Resize:
            # Wayland 合成器的 configure 是权威、无法拒绝：混合 DPI 多屏下最小化恢复时，
            # 窗口可能被重新关联到另一块屏并按新 DPR 折算尺寸（实测 900x540 → 450x270），
            # 且此后客户端 resize() 会被合成器无视（xdg_toplevel 无客户端 resize 协议）。
            # 唯一可靠恢复：在 QWindow 层 unmap→resize→remap 重建 surface，强制重新 configure。
            if obj is self.dialog:
                target = getattr(self.dialog, "_chrome_size", None)
                if target:
                    sz = self.dialog.size()
                    if sz.width() >= target[0] and sz.height() >= target[1]:
                        # 尺寸正常或被用户拉大（现在允许拉伸）：复位计数，不干预。
                        # total 必须随正常状态一并清零：合成器在每次最小化时都会发一次
                        # 减半 configure（实测），若按面板生命周期累计，两轮最小化就耗尽
                        # 恢复额度，之后窗口永久保持减半 —— 曾是「页面还是会缩小」的根因。
                        # 无限拉锯已由单活策略结构性消除，这里只防单轮连续风暴。
                        setattr(self.dialog, "_chrome_resize_fixes", 0)
                        setattr(self.dialog, "_chrome_resize_total", 0)
                    else:
                        # 恢复总量硬上限：两个并存弹窗的恢复会互相触发合成器
                        # configure（实测无限减半拉锯、窗口狂闪），到顶必须停手
                        total = getattr(self.dialog, "_chrome_resize_total", 0)
                        if total >= 4:
                            if total == 4:
                                setattr(self.dialog, "_chrome_resize_total", total + 1)
                                logger.warning(
                                    "合成器持续改尺寸为 %s，已达恢复上限，停止重建",
                                    self.dialog.size(),
                                )
                            return False
                        setattr(self.dialog, "_chrome_resize_total", total + 1)
                        fixes = getattr(self.dialog, "_chrome_resize_fixes", 0)
                        setattr(self.dialog, "_chrome_resize_fixes", fixes + 1)
                        logger.info(
                            "合成器改尺寸为 %s，重建 surface 恢复 %s (第 %d 次)",
                            self.dialog.size(), target, fixes + 1,
                        )
                        dlg = self.dialog

                        def _recover():
                            h = dlg.windowHandle()
                            if h is None:
                                return
                            # 用 QWindow 层开关而非 QWidget.hide()/show()：
                            # QDialog::setVisible(False) 会把结果置为 Rejected。
                            # 配合 run_modal_loop（不因隐藏退出），临时 unmap 不再杀对话框。
                            h.setVisible(False)
                            dlg.resize(*target)
                            h.setVisible(True)

                        QTimer.singleShot(60, _recover)
            return False
        if etype == QEvent.Show:
            # 只在对话框自身 Show 时居中；子控件 Show 会频繁触发，不能把窗口拽回中心
            if obj is self.dialog:
                schedule_center(self.dialog)
            self.install_recursive(self.dialog)
            return False
        elif etype == QEvent.ChildAdded:
            child = event.child()
            if child and isinstance(child, QWidget):
                try:
                    if not is_interactive_widget(child):
                        child.installEventFilter(self)
                except Exception:
                    pass
            return False
        elif etype == QEvent.MouseButtonPress:
            if event.button() == Qt.LeftButton:
                app = QApplication.instance()
                if app and app.activePopupWidget():
                    # 当前有下拉菜单或弹出浮层打开，绝对不触发窗口拖拽
                    return False

                global_pos = (
                    event.globalPosition().toPoint()
                    if hasattr(event, "globalPosition")
                    else event.globalPos()
                )
                hit_widget = app.widgetAt(global_pos) if app else None

                curr = hit_widget
                while curr:
                    if curr == self.dialog:
                        break
                    if is_interactive_widget(curr):
                        # 点击在按钮、下拉框、弹出菜单或交互控件上，直接放行，绝不抢占
                        return False
                    curr = curr.parentWidget()

                handle = self.dialog.windowHandle()
                if handle:
                    try:
                        if handle.startSystemMove():
                            mark_dialog_moved(self.dialog)
                            return True
                    except Exception:
                        pass
                self.drag_pos = (
                    global_pos - self.dialog.frameGeometry().topLeft()
                )
                return False
        elif etype == QEvent.MouseMove:
            if event.buttons() == Qt.LeftButton and self.drag_pos is not None:
                mark_dialog_moved(self.dialog)
                self.dialog.move(event.globalPosition().toPoint() - self.drag_pos)
                return True
        elif etype == QEvent.MouseButtonRelease:
            self.drag_pos = None
        return False


def available_screen_size() -> QSize:
    app = QApplication.instance()
    if app:
        from PySide6.QtGui import QCursor

        screen = app.screenAt(QCursor.pos()) or app.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            return QSize(g.width(), g.height())
    return QSize(1280, 720)


def mark_dialog_moved(dialog: QDialog) -> None:
    """用户已拖动窗口后，后续居中定时器不得再把窗口拽回屏幕中心。"""
    setattr(dialog, "_user_moved", True)


def center_dialog(dialog: QDialog) -> None:
    """将对话框精准居中到当前光标所在屏幕可用区域中心。用户拖动后不再强制居中。"""
    if getattr(dialog, "_user_moved", False):
        return
    app = QApplication.instance()
    if not app:
        return
    from PySide6.QtGui import QCursor

    screen = app.screenAt(QCursor.pos()) or app.primaryScreen()
    if not screen:
        return
    geo = screen.availableGeometry()
    w = dialog.width()
    h = dialog.height()
    x = geo.x() + (geo.width() - w) // 2
    y = geo.y() + (geo.height() - h) // 2
    # 混合 DPI 多屏下，surface 若按另一块屏的度量创建、再映射到目标屏，尺寸会被
    # 重新折算（Qt↔Chromium 关联错乱，点击整体偏移）。映射前把 QWindow 绑定到
    # 目标屏，确保 WebEngine 以正确 DPR 初始化。
    handle = dialog.windowHandle()
    if handle is not None and not handle.isVisible():
        try:
            handle.setScreen(screen)
        except Exception:
            pass
    dialog.setGeometry(x, y, w, h)
    handle = dialog.windowHandle()
    if handle is not None:
        try:
            handle.setPosition(QPoint(x, y))
        except Exception:
            pass


def schedule_center(dialog: QDialog) -> None:
    # 多阶段重定位：Wayland 首帧窗口几何不稳定，单次定时会错位（见 46d7087 / f7cd0de）。
    # center_dialog 内含 _user_moved 守卫，拖动过的窗口不会被拽回中心。
    for delay in (0, 30, 100):
        QTimer.singleShot(delay, lambda d=dialog: center_dialog(d))


def run_modal_loop(dialog: QDialog) -> bool:
    """替代 QDialog.exec() 的模态运行：只在 finished 信号时退出。

    exec() 内部的事件循环会被任何窗口隐藏以 Rejected 打断 —— 而 Resize 守卫
    恢复混合 DPI 缩小时必须 unmap/remap 窗口（实测 900x540→450x270 后客户端
    resize 被合成器无视），这个 120ms 的临时隐藏会直接杀死 exec() 中的对话框。
    自管循环只认 finished（accept/reject/done 触发），临时隐藏不再致命。
    """
    from PySide6.QtCore import QEventLoop

    dialog.show()
    loop = QEventLoop()
    dialog.finished.connect(loop.quit)
    loop.exec()
    return dialog.result() == QDialog.DialogCode.Accepted


def enable_dialog_drag(dialog: QDialog) -> None:
    """为无边框弹窗启用递归鼠标拖拽支持。"""
    dialog.create()
    drag_filter = DialogDragFilter(dialog)
    drag_filter.install_recursive(dialog)
    setattr(dialog, "_drag_filter", drag_filter)


def apply_dialog_chrome(
    dialog: QDialog,
    *,
    width: int,
    height: int,
    stay_on_top: bool = False,
    tool: bool = False,
) -> None:
    """
    统一弹窗 Chrome 形态: 使用 FramelessWindowHint 彻底移除系统标题栏与系统按钮 (最大化/最小化/关闭)。
    控制页面关闭和大小改由页面内部按钮控制。默认屏幕居中，空白区域可拖拽移动。
    """
    stays_on_top = stay_on_top or bool(dialog.windowFlags() & Qt.WindowStaysOnTopHint)
    window_type = Qt.Tool if tool else Qt.Dialog
    flags = Qt.FramelessWindowHint | window_type | Qt.CustomizeWindowHint
    if stays_on_top:
        flags |= Qt.WindowStaysOnTopHint
    dialog.setWindowFlags(flags)

    scr = available_screen_size()
    max_w = max(320, int(scr.width() * 0.92))
    max_h = max(240, int(scr.height() * 0.92))
    fixed_w = min(width, max_w)
    fixed_h = min(height, max_h)

    # 不能 setFixedSize(min==max)：mutter 对“固定尺寸”窗口在最小化恢复时会下发
    # 带尺寸的 configure，且单位错误（实测 900x540→450x270 折半，客户端 resize 被无视）。
    # 可拉伸窗口恢复时 configure 不带尺寸、由客户端自定 → 折半从协议层不再发生。
    # 页面为响应式布局，拉伸到屏幕 92% 上限不会破版。
    dialog.setMinimumSize(fixed_w, fixed_h)
    dialog.setMaximumSize(max(fixed_w + 1, max_w), max(fixed_h + 1, max_h))
    dialog.resize(fixed_w, fixed_h)
    # 期望尺寸：Resize 守卫仅在窗口被改“小”（合成器 bug 特征）时恢复，用户拉大则放行
    setattr(dialog, "_chrome_size", (fixed_w, fixed_h))
    enable_dialog_drag(dialog)
    schedule_center(dialog)


def fit_dialog(
    dialog: QDialog,
    *,
    preferred_w: int,
    preferred_h: int,
    min_w: int = 480,
    min_h: int = 280,
    max_ratio: float = 0.92,
) -> None:
    """
    横版优先的尺寸策略：
    - 默认宽 >= 高（横版）
    - 不超过可用屏幕 max_ratio
    - 设置 minimumSize，避免内容被压扁导致按钮文字截断
    """
    scr = available_screen_size()
    max_w = max(320, int(scr.width() * max_ratio))
    max_h = max(240, int(scr.height() * max_ratio))

    # 若偏好偏高，改为更宽的横版比例
    if preferred_h > preferred_w:
        preferred_w, preferred_h = max(preferred_w, int(preferred_h * 1.15)), min(
            preferred_h, int(preferred_w * 0.85)
        )

    w = max(min_w, min(preferred_w, max_w))
    h = max(min_h, min(preferred_h, max_h))
    # 保证横版倾向
    if h > w and max_w >= min_w + 80:
        w = min(max_w, max(w, int(h * 1.2)))

    dialog.setMinimumSize(min(min_w, w), min(min_h, h))
    dialog.resize(w, h)
    dialog.setMaximumHeight(max_h)
    dialog.setMaximumWidth(max_w)


def style_action_button(btn: QPushButton, *, min_w: int = 96, min_h: int = 34) -> QPushButton:
    """保证按钮能完整显示文字。"""
    btn.setMinimumWidth(min_w)
    btn.setMinimumHeight(min_h)
    btn.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
    # 避免样式把文字裁切
    btn.setStyleSheet(
        (btn.styleSheet() or "")
        + """
        QPushButton {
            padding: 6px 14px;
            min-height: 28px;
        }
        """
    )
    return btn


def make_scroll_body(content: QWidget) -> QScrollArea:
    """可滚动内容区（内容过高时不撑破屏幕）。"""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
    scroll.setWidget(content)
    return scroll


def dialog_root_with_scroll(
    dialog: QDialog,
    *,
    margins: tuple[int, int, int, int] = (16, 16, 16, 12),
    spacing: int = 10,
) -> tuple[QVBoxLayout, QWidget, QHBoxLayout]:
    """
    标准结构：
      外层 VBox
        - ScrollArea(content_widget)  ← 主体横/纵排
        - footer_layout               ← 按钮行（始终可见）
    返回 (root_layout, content_widget, footer_layout)
    """
    root = QVBoxLayout(dialog)
    root.setContentsMargins(*margins)
    root.setSpacing(spacing)

    content = QWidget()
    scroll = make_scroll_body(content)
    root.addWidget(scroll, 1)

    footer = QHBoxLayout()
    footer.setSpacing(10)
    root.addLayout(footer)
    return root, content, footer
