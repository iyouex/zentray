# zentray/ui/win_flyout.py
"""Windows 贴边胶囊的窄边 flyout（P2b）。

- A 端（content）：插件 / 任务列表（原生列表，任务可切换、插件打开面板）。
- B 端（system）：设置 / 插件管理 / 通知与专注 / 快捷键 / 退出。

窗口是 ``Qt.Tool`` + 透明 + 不抢焦点；贴胶囊窄边定位由 ``edge_dock.flyout_rect``
计算（放不下翻到另一侧，最后夹进可用区）。点击外部 / Esc 关闭。
"""
from __future__ import annotations

import ctypes
import logging
import sys
import time

from PySide6.QtCore import QEvent, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from zentray.ui.edge_dock import flyout_rect

logger = logging.getLogger(__name__)

_ROW_STYLE = """
QLabel#flTitle { color: #eaf2fc; font-size: 12.5px; font-weight: 600; }
QPushButton#flClose { border: none; background: transparent; color: #9fb0c8;
  font-size: 12px; padding: 0; min-width: 22px; max-width: 22px; min-height: 22px; }
QPushButton#flClose:hover { color: #ffffff; }
QLabel#flSec { color: #7a8798; font-size: 9px; letter-spacing: 1px; padding: 4px 4px 2px 4px; }
QPushButton[flRole="row"] { text-align: left; border: none; border-left: 2px solid transparent;
  background: transparent; color: #c8d6e8; padding: 6px 8px; border-radius: 6px; font-size: 11px; }
QPushButton[flRole="row"]:hover { background: rgba(255,255,255,.06); color: #eaf3ff; }
QPushButton[flRole="row"][current="true"] { background: rgba(76,194,255,.1); color: #eaf3ff; }
QPushButton[flRole="row"][priority="high"] { border-left-color: #ff6b6b; }
QPushButton[flRole="row"][priority="medium"] { border-left-color: #ffc44d; }
QPushButton[flRole="row"][priority="low"] { border-left-color: #4ade80; }
QPushButton[flRole="row"][danger="true"] { color: #ffb4b4; }
QPushButton#flFooter { border: 1px solid rgba(255,255,255,.12); background: rgba(255,255,255,.04);
  color: #cfe0f2; border-radius: 7px; padding: 6px; font-size: 10px; }
QPushButton#flFooter:hover { background: rgba(255,255,255,.08); }
QFrame#flSep { background: rgba(255,255,255,.08); max-height: 1px; min-height: 1px; border: none; }
"""

_LIGHT_STYLE = """
QLabel#flTitle { color: #17202b; font-size: 12.5px; font-weight: 600; }
QPushButton#flClose { border: none; background: transparent; color: #6b7a90;
  font-size: 12px; padding: 0; min-width: 22px; max-width: 22px; min-height: 22px; }
QPushButton#flClose:hover { color: #17202b; }
QLabel#flSec { color: #7a8798; font-size: 9px; letter-spacing: 1px; padding: 4px 4px 2px 4px; }
QPushButton[flRole="row"] { text-align: left; border: none; border-left: 2px solid transparent;
  background: transparent; color: #334155; padding: 6px 8px; border-radius: 6px; font-size: 11px; }
QPushButton[flRole="row"]:hover { background: rgba(0,0,0,.05); color: #0b2a4a; }
QPushButton[flRole="row"][current="true"] { background: rgba(0,103,192,.1); color: #0b2a4a; }
QPushButton[flRole="row"][priority="high"] { border-left-color: #e5484d; }
QPushButton[flRole="row"][priority="medium"] { border-left-color: #d99a1e; }
QPushButton[flRole="row"][priority="low"] { border-left-color: #2f9e5b; }
QPushButton[flRole="row"][danger="true"] { color: #c2410c; }
QPushButton#flFooter { border: 1px solid rgba(0,0,0,.12); background: rgba(0,0,0,.03);
  color: #334155; border-radius: 7px; padding: 6px; font-size: 10px; }
QPushButton#flFooter:hover { background: rgba(0,0,0,.06); }
QFrame#flSep { background: rgba(0,0,0,.08); max-height: 1px; min-height: 1px; border: none; }
"""


def apply_no_activate(widget: QWidget) -> None:
    """Windows: WS_EX_NOACTIVATE + TOOLWINDOW（不抢焦点、不进 Alt-Tab）。"""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(widget.winId())
        user32 = ctypes.windll.user32
        gwl_exstyle = -20
        ws_ex_noactivate = 0x08000000
        ws_ex_toolwindow = 0x00000080
        style = user32.GetWindowLongW(hwnd, gwl_exstyle)
        user32.SetWindowLongW(hwnd, gwl_exstyle, style | ws_ex_noactivate | ws_ex_toolwindow)
    except Exception:
        logger.debug("WS_EX_NOACTIVATE 设置失败", exc_info=True)


def _short(text: str, n: int = 26) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


class _FlyoutBase(QWidget):
    """透明玻璃 flyout 基类：定位、外部点击关闭、Esc。"""

    WIDTH = 360
    HEIGHT = 430

    closed = Signal()

    def __init__(self, light: bool = False, parent=None):
        super().__init__(parent)
        self._light = bool(light)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._open_ts = 0.0
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.setStyleSheet(_LIGHT_STYLE if self._light else _ROW_STYLE)

    def set_light(self, light: bool) -> None:
        self._light = bool(light)
        self._apply_theme()
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)
        if self._light:
            p.setBrush(QColor(252, 253, 255, 250))
            p.setPen(QPen(QColor(0, 0, 0, 42), 1))
        else:
            p.setBrush(QColor(28, 32, 40, 250))
            p.setPen(QPen(QColor(255, 255, 255, 36), 1))
        p.drawRoundedRect(rect, 14, 14)
        # 内侧高光
        p.setPen(QPen(QColor(255, 255, 255, 200) if self._light else QColor(255, 255, 255, 18), 1))
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 13, 13)

    def open_at(self, rect: tuple[int, int, int, int]) -> None:
        self.setGeometry(*rect)
        self.show()
        self.raise_()
        apply_no_activate(self)
        self._open_ts = time.monotonic()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def closeEvent(self, event) -> None:
        app = QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass
        self.closed.emit()
        super().closeEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.MouseButtonPress and time.monotonic() - self._open_ts > 0.12:
            if not self.geometry().contains(QCursor.pos()):
                self.close()
        elif event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            self.close()
        return super().eventFilter(obj, event)


class TaskPluginFlyout(_FlyoutBase):
    """窄边 A：任务列表 + 插件列表。"""

    WIDTH = 360
    HEIGHT = 430

    def __init__(self, provider, light: bool = False, parent=None):
        self.provider = provider
        super().__init__(light=light, parent=parent)
        self._build()
        self.refresh()

    def _build(self) -> None:
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(12, 12, 12, 12)
        self._root.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("任务与插件")
        title.setObjectName("flTitle")
        head.addWidget(title)
        head.addStretch(1)
        close = QPushButton("×")
        close.setObjectName("flClose")
        close.clicked.connect(self.close)
        head.addWidget(close)
        self._root.addLayout(head)

        self._body = QVBoxLayout()
        self._body.setSpacing(2)
        self._root.addLayout(self._body)
        self._root.addStretch(1)

        self._footer = QPushButton("打开完整列表")
        self._footer.setObjectName("flFooter")
        self._footer.clicked.connect(self._open_tasks)
        self._root.addWidget(self._footer)

    def refresh(self) -> None:
        while self._body.count():
            item = self._body.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        snap = self.provider.flyout_snapshot() if self.provider is not None else {}
        snap = snap or {}
        tasks = (snap.get("tasks") or [])[:4]
        plugins = (snap.get("plugins") or [])[:3]

        if tasks:
            sec = QLabel("任务")
            sec.setObjectName("flSec")
            self._body.addWidget(sec)
        for t in tasks:
            label = ("● " if t.get("current") else "○ ") + _short(t.get("title") or "未命名", 24)
            if t.get("deadline"):
                label += "  · " + _short(str(t["deadline"]), 12)
            btn = QPushButton(label)
            btn.setToolTip(t.get("title") or "")
            btn.setProperty("flRole", "row")
            btn.setProperty("priority", t.get("priority") or "none")
            btn.setProperty("current", "true" if t.get("current") else "false")
            btn.clicked.connect(lambda _=False, tid=t.get("id"): self._select_task(tid))
            self._body.addWidget(btn)

        if plugins:
            sec2 = QLabel("插件")
            sec2.setObjectName("flSec")
            self._body.addWidget(sec2)
        for p in plugins:
            btn = QPushButton("▷ " + _short(p.get("name") or p.get("id") or "插件", 22))
            btn.setToolTip("打开插件面板运行")
            btn.setProperty("flRole", "row")
            btn.clicked.connect(lambda _=False: self._open_plugins())
            self._body.addWidget(btn)
        if not tasks and not plugins:
            empty = QLabel("暂无可显示的任务或插件")
            empty.setObjectName("flSec")
            self._body.addWidget(empty)

    def _select_task(self, task_id) -> None:
        if self.provider is not None and task_id:
            self.provider.flyout_select_task(task_id)
        self.close()

    def _open_tasks(self) -> None:
        if self.provider is not None:
            self.provider.flyout_open_tasks()
        self.close()

    def _open_plugins(self) -> None:
        if self.provider is not None:
            self.provider.flyout_open_plugins()
        self.close()


class SystemFlyout(_FlyoutBase):
    """窄边 B：设置 / 插件管理 / 通知与专注 / 快捷键 / 退出。"""

    WIDTH = 236
    HEIGHT = 236

    def __init__(self, provider, light: bool = False, parent=None):
        self.provider = provider
        super().__init__(light=light, parent=parent)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(2)

        head = QHBoxLayout()
        title = QLabel("ZenTray")
        title.setObjectName("flTitle")
        head.addWidget(title)
        head.addStretch(1)
        close = QPushButton("×")
        close.setObjectName("flClose")
        close.clicked.connect(self.close)
        head.addWidget(close)
        root.addLayout(head)

        rows = [
            ("⚙  设置", "settings", False),
            ("🧩  插件管理", "ops.panel", False),
            ("🔔  通知与专注", "settings", False),
            ("⌨  快捷键", "settings", False),
            (None, None, False),
            ("⏻  退出 ZenTray", "quit", True),
        ]
        for label, action, danger in rows:
            if label is None:
                sep = QFrame()
                sep.setObjectName("flSep")
                root.addWidget(sep)
                continue
            btn = QPushButton(label)
            btn.setProperty("flRole", "row")
            if danger:
                btn.setProperty("danger", "true")
            btn.clicked.connect(lambda _=False, a=action: self._act(a))
            root.addWidget(btn)
        root.addStretch(1)

    def _act(self, action: str) -> None:
        if self.provider is not None and action:
            self.provider.flyout_action(action)
        self.close()
