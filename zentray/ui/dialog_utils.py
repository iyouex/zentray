# zentray/ui/dialog_utils.py
"""对话框通用布局：横版优先、适配屏幕、按钮文字完整显示。"""
from __future__ import annotations

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

    flags = widget.windowFlags()
    if flags & (Qt.Popup | Qt.Tool):
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
        if event.type() == QEvent.Show:
            # 只在对话框自身 Show 时居中；子控件 Show 会频繁触发，不能把窗口拽回中心
            if obj is self.dialog:
                schedule_center(self.dialog)
            self.install_recursive(self.dialog)
            return False
        elif event.type() == QEvent.ChildAdded:
            child = event.child()
            if child and isinstance(child, QWidget):
                try:
                    if not is_interactive_widget(child):
                        child.installEventFilter(self)
                except Exception:
                    pass
            return False
        elif event.type() == QEvent.MouseButtonPress:
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
        elif event.type() == QEvent.MouseMove:
            if event.buttons() == Qt.LeftButton and self.drag_pos is not None:
                mark_dialog_moved(self.dialog)
                self.dialog.move(event.globalPosition().toPoint() - self.drag_pos)
                return True
        elif event.type() == QEvent.MouseButtonRelease:
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

    dialog.setFixedSize(fixed_w, fixed_h)
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
