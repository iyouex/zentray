# zentray/ui/win_tray.py
"""
Windows 托盘后端（docs/design/windows-interaction-design.md §3，2026-10-17 重设计）。

- 主显示：任务栏正上方状态条（§3.0，WindowsStatusStripTray）——AppBar 系统级
  保留条带，动态图标 + 完整标题不截断；左键=速览面板、右键=菜单
- 辅助：通知区图标（WindowsTray）——toast / 设置兜底入口
- 图标运行时绘制（饼图/番茄/茶绿/转圈/徽标/倒计时叠加），替代预烘焙 PNG
"""
from __future__ import annotations

import logging
import re
import sys

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget, QSystemTrayIcon

from zentray.ui.tray import QtStandardTray

logger = logging.getLogger(__name__)

# 优先级 → 环色（与 Linux 预烘焙 PNG 语义一致：high 红 / medium 黄 / low 绿）
_PRIORITY_COLOR = {
    "high": "#e5484d",
    "medium": "#f5a524",
    "low": "#30a46c",
    "none": "#8b8f98",
}
_TOMATO = "#e5484d"
_TEA = "#3aa981"
_ACCENT = "#0078d4"

_ICON_SIZE = 64  # 绘制源尺寸：16/20/24px 通知区图标 3~4x 超采样，避免高 DPI 发糊


def icon_paint_spec(icon: str, text: str, countdown_on: bool = False) -> dict:
    """icon 名 + 当前托盘文案 → 图标绘制规格（纯函数，便于单测）。"""
    name = (icon or "app_icon").strip() or "app_icon"
    spec = {
        "base": "app",          # app | pie | tomato | break
        "priority": "",
        "progress": 0,          # 0-100，10 步进
        "spinner": False,       # 脚本运行中（文案 ⚡ 前缀）
        "badge": False,         # 报告待查看（文案 📄 前缀）
        "minutes": None,        # 番茄/休息图标内叠加的剩余分钟（设置开启时）
    }
    m = re.match(r"^pie_(high|medium|low|none)_(\d+)$", name)
    if m:
        spec["base"] = "pie"
        spec["priority"] = m.group(1)
        spec["progress"] = max(0, min(100, int(m.group(2))))
    else:
        m = re.match(r"^(tomato|break)_(\d+)$", name)
        if m:
            spec["base"] = m.group(1)
            spec["progress"] = max(0, min(100, int(m.group(2))))
    # ⚡/📄 前缀对任意底图都要生效（轮播期 icon 仍是 pie_*，文案前缀表达运行/待看）
    t = text or ""
    spec["spinner"] = t.startswith("⚡")
    spec["badge"] = t.startswith("📄")
    if countdown_on and spec["base"] in ("tomato", "break"):
        mm = re.match(r"^(\d{1,2}):(\d{2})", t)
        if mm:
            # 剩余分钟向上取整：14:32 → 15
            spec["minutes"] = int(mm.group(1)) + (1 if int(mm.group(2)) else 0)
    return spec


def paint_tray_pixmap(spec: dict, app_icon_path: str = "") -> QPixmap | None:
    """按规格绘制托盘图标。失败返回 None（调用方回退 PNG）。"""
    pm = QPixmap(_ICON_SIZE, _ICON_SIZE)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    try:
        base = spec.get("base", "app")
        rect = QRect(4, 4, _ICON_SIZE - 8, _ICON_SIZE - 8)
        if base == "pie":
            color = QColor(_PRIORITY_COLOR.get(spec.get("priority"), "none"))
            _paint_ring(p, rect, color, int(spec.get("progress") or 0))
        elif base in ("tomato", "break"):
            color = QColor(_TOMATO if base == "tomato" else _TEA)
            _paint_disc(p, rect, color, int(spec.get("progress") or 0))
        else:
            app = QPixmap(app_icon_path) if app_icon_path else QPixmap()
            if app.isNull():
                # 无源图：绘制单色 app 剪影（圆角方块 + 圆点）
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(_ACCENT))
                p.drawRoundedRect(rect, 14, 14)
                p.setBrush(QColor("#ffffff"))
                p.drawEllipse(rect.center(), 10, 10)
            else:
                p.drawPixmap(rect, app)
            if spec.get("spinner"):
                pen = QPen(QColor("#ffffff"), 6)
                pen.setCapStyle(Qt.RoundCap)
                p.setPen(pen)
                # 270° 活动弧：起 45° 顺时针，表示「进行中」
                p.drawArc(rect.adjusted(6, 6, -6, -6), 45 * 16, 270 * 16)
            if spec.get("badge"):
                _paint_badge(p, str(spec.get("minutes") or ""))
        return pm
    finally:
        p.end()


def _paint_ring(p: QPainter, rect: QRect, color: QColor, progress: int) -> None:
    """优先级饼图：底环半透明 + 进度实色弧（12 点起顺时针）。"""
    pen = QPen(color)
    pen.setWidth(9)
    pen.setCapStyle(Qt.RoundCap)
    pen.setColor(QColor(color.red(), color.green(), color.blue(), 70))
    p.setPen(pen)
    p.drawEllipse(rect)
    if progress > 0:
        pen.setColor(color)
        p.setPen(pen)
        p.drawArc(rect, 90 * 16, -int(progress * 3.6) * 16)


def _paint_disc(p: QPainter, rect: QRect, color: QColor, progress: int) -> None:
    """番茄/休息圆饼：满色盘 + 浅色扇形表示已消耗进度。"""
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    p.drawEllipse(rect)
    if progress > 0:
        p.setBrush(QColor(255, 255, 255, 110))
        span = int(progress * 3.6 * 16)
        p.drawPie(rect, 90 * 16, -span)


def _paint_badge(p: QPainter, text: str) -> None:
    """右下角徽标：红点；有数字（剩余分钟）则画数字。"""
    cx, cy, r = _ICON_SIZE - 14, _ICON_SIZE - 14, 10
    p.setPen(QPen(QColor("#ffffff"), 3))
    p.setBrush(QColor("#e5484d"))
    p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
    if text:
        p.setPen(QColor("#ffffff"))
        font = p.font()
        font.setPixelSize(11)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRect(cx - r, cy - r, r * 2, r * 2), Qt.AlignCenter, text)


class WindowsTray(QtStandardTray):
    """Windows 通知区：左键速览、右键菜单、QPainter 动态图标 + tooltip。"""

    # 左键速览请求（携带托盘图标位置，锚定面板）
    glance_requested = Signal(QPoint)

    def _on_activated(self, reason):
        # Windows 惯例分流：右键=菜单，左键/双击=速览面板（OneDrive 同型）
        if reason == QSystemTrayIcon.Context:
            self.menu.popup(QCursor.pos())
            return
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            geo = self.tray.geometry()
            pos = geo.center() if (geo and geo.isValid()) else QCursor.pos()
            self.glance_requested.emit(QPoint(pos.x(), pos.y()))

    def set_state(self, icon: str, text: str):
        self._paint_and_set(icon, text)
        tip = (text or "").strip() or "ZenTray"
        # Windows 无文字槽位：全量状态走 tooltip（≤128 字符）
        self.tray.setToolTip(f"ZenTray\n{tip[:128]}")
        self._last_label = tip
        self.label_changed.emit(text or "")

    def set_label(self, text: str):
        # 文案变化同样影响叠加态（⚡/📄/倒计时前缀），走完整重绘
        self.set_state(self._last_icon or "app_icon", text)

    def set_icon(self, name: str):
        self._paint_and_set(name, self._last_label)

    def _paint_and_set(self, icon: str, text: str):
        name = (icon or "app_icon").strip() or "app_icon"
        countdown = False
        try:
            from zentray.services.settings_manager import SettingsManager

            countdown = bool(SettingsManager().pomodoro.tray_icon_countdown)
        except Exception:
            pass
        spec = icon_paint_spec(name, text, countdown_on=countdown)
        pm = paint_tray_pixmap(spec, self._app_icon_path)
        self._last_pixmap = None  # 中央按钮复用同一 pixmap
        if pm is None or pm.isNull():
            # 绘制失败回退预烘焙 PNG（父类逻辑）
            path = self._icon_dir / f"{name}.png"
            if not path.exists() and self._app_icon_path:
                from pathlib import Path

                path = Path(self._app_icon_path)
            if path.exists():
                self.tray.setIcon(QIcon(str(path)))
        else:
            self.tray.setIcon(QIcon(pm))
            self._last_pixmap = pm
        self._last_icon = name


# ============================================================
# 状态条（设计 §3.0，2026-10-17 重设计）
# 旧「1×1 窗口造任务栏中央按钮」方案废弃：文字标签依赖任务栏「从不合并」
# 系统设置（连累所有应用）、按钮宽度按窗口数分配长标题必截断、合并模式下
# 一枚小图标淹没在应用堆里。AppBar（SHAppBarMessage）是任务栏自身的同款
# 机制：系统保留条带、最大化窗口自动避让、不依赖任何用户设置。
# ============================================================

_STRIP_HEIGHT = 30  # 逻辑像素

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _APPBARDATA(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("hWnd", wintypes.HWND),
            ("uCallbackMessage", wintypes.UINT),
            ("uEdge", wintypes.UINT),
            ("rc", wintypes.RECT),
            ("lParam", wintypes.LPARAM),
        ]

    class _MSG(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
        ]

    _ABM_NEW, _ABM_REMOVE, _ABM_SETPOS, _ABM_GETTASKBARPOS = 0, 1, 3, 5
    _ABE_TOP, _ABE_BOTTOM = 1, 3
    _ABN_POSCHANGED, _ABN_FULLSCREENAPP = 1, 2

    def _shAppBarMessage(msg: int, abd: _APPBARDATA) -> int:
        return ctypes.windll.shell32.SHAppBarMessage(msg, ctypes.byref(abd))


class _StatusStripWindow(QWidget):
    """任务栏正上方的状态条：动态图标 + 完整标题（超宽跑马灯/省略号）。

    左键=速览面板、右键=菜单；AppBar 注册后系统为其保留条带（最大化窗口
    不覆盖）。注册失败（如 CI 会话无 Shell）退化为普通置顶条，仍可用。
    """

    glance_requested = Signal(QPoint)
    menu_requested = Signal(QPoint)

    def __init__(self):
        super().__init__()
        # 绝不自我激活（v0.7.13 狂闪教训：show() 的 OS 级激活异步落地可成环）；
        # 本窗口不进任务栏/Alt-Tab（Qt.Tool），点击交互全在 mousePressEvent 内
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self._pm: QPixmap | None = None
        self._text = "ZenTray"
        self._marquee = False
        self._offset = 0  # 跑马灯像素偏移
        self._registered = False
        self._callback_msg = 0
        self._taskbar_created_msg = 0
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._on_tick)
        self.show()
        if sys.platform == "win32":
            self._register_appbar()

    # —— AppBar 注册 / 定位（物理像素，落地前换算 Qt 逻辑像素）——

    def _register_appbar(self) -> None:
        try:
            self._callback_msg = 0x8000  # WM_APP
            abd = _APPBARDATA(
                cbSize=ctypes.sizeof(_APPBARDATA),
                hWnd=int(self.winId()),
                uCallbackMessage=self._callback_msg,
            )
            if not _shAppBarMessage(_ABM_NEW, abd):
                return  # 注册失败：置顶条降级，不报错（CI 会话等场景）
            self._registered = True
            # Explorer 重启后广播 TaskbarCreated，需重新注册
            self._taskbar_created_msg = ctypes.windll.user32.RegisterWindowMessageW(
                "TaskbarCreated"
            )
            self._apply_pos()
        except Exception:
            logger.exception("AppBar 注册失败，状态条退化为普通置顶条")

    def _unregister_appbar(self) -> None:
        if not self._registered:
            return
        abd = _APPBARDATA(
            cbSize=ctypes.sizeof(_APPBARDATA), hWnd=int(self.winId())
        )
        _shAppBarMessage(_ABM_REMOVE, abd)
        self._registered = False

    def _apply_pos(self) -> None:
        """按任务栏实际位置提议条带矩形，SETPOS 仲裁后落位。

        矩形一律从屏幕/任务栏物理尺寸推算，不用 availableGeometry——
        注册成功后它已扣除本条带，反复重提会步步上移。
        """
        try:
            cx = ctypes.windll.user32.GetSystemMetrics(0)
            cy = ctypes.windll.user32.GetSystemMetrics(1)
            h = round(_STRIP_HEIGHT * self._dpr())
            x, y, w = 0, cy - h - 48, cx  # 探测失败兜底：按 48px 任务栏留位
            abd = _APPBARDATA(
                cbSize=ctypes.sizeof(_APPBARDATA), hWnd=int(self.winId())
            )
            if _shAppBarMessage(_ABM_GETTASKBARPOS, abd):
                tb = abd.rc
                if abd.uEdge == _ABE_BOTTOM:
                    y = tb.top - h
                elif abd.uEdge == _ABE_TOP:
                    y = tb.bottom
                elif tb.left <= 0:  # LEFT：条带贴任务栏右缘
                    x, y, w = tb.right, cy - h, cx - (tb.right - tb.left)
                else:  # RIGHT
                    x, y, w = 0, cy - h, cx - (tb.right - tb.left)
            abd = _APPBARDATA(
                cbSize=ctypes.sizeof(_APPBARDATA),
                hWnd=int(self.winId()),
                uEdge=_ABE_BOTTOM,
                rc=wintypes.RECT(x, y, x + w, y + h),
            )
            _shAppBarMessage(_ABM_SETPOS, abd)
            rc = abd.rc
            d = self._dpr()
            self.setGeometry(
                round(rc.left / d), round(rc.top / d),
                round((rc.right - rc.left) / d), round((rc.bottom - rc.top) / d),
            )
        except Exception:
            logger.exception("AppBar 定位失败，状态条停在默认位置")
            self.setGeometry(0, 0, 400, _STRIP_HEIGHT)

    @staticmethod
    def _dpr() -> float:
        screen = QGuiApplication.primaryScreen()
        return float(screen.devicePixelRatio()) if screen else 1.0

    def nativeEvent(self, eventType, message):
        # Appbar 回调与 TaskbarCreated 都直达本窗口，无需全局事件过滤器
        if sys.platform == "win32" and self.isVisible():
            try:
                msg = _MSG.from_address(int(message))
                if msg.message == self._callback_msg and self._callback_msg:
                    if msg.wParam == _ABN_FULLSCREENAPP:
                        self._on_fullscreen(bool(msg.lParam))
                    elif msg.wParam == _ABN_POSCHANGED:
                        self._apply_pos()
                elif (
                    self._taskbar_created_msg
                    and msg.message == self._taskbar_created_msg
                ):
                    # Explorer 重启：先撤旧注册再重新登记（Win32 要求）
                    self._unregister_appbar()
                    self._register_appbar()
            except Exception:
                pass
        return super().nativeEvent(eventType, message)

    def _on_fullscreen(self, entering: bool) -> None:
        # 全屏应用让路：撤销注册+隐藏（不留 30px 空带）；退出全屏原样恢复
        if entering:
            self._unregister_appbar()
            self.hide()
        else:
            self.show()
            self._register_appbar()

    # —— 内容与绘制 ——

    def set_content(self, pm: QPixmap | None, text: str, marquee: bool) -> None:
        self._pm = pm
        self._text = text or "ZenTray"
        self._marquee = marquee
        self._offset = 0
        # 与 paintEvent 同一超宽判据：跑马灯开且放不下才滚
        overflow = (
            self.fontMetrics().horizontalAdvance(self._text)
            > self.width() - self.height() - 14
        )
        if marquee and overflow:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _on_tick(self) -> None:
        fm = self.fontMetrics()
        self._offset += 4
        if self._offset > fm.horizontalAdvance(self._text) + 24:
            self._offset = 0
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#1f1f1f"))
        m = 3
        side = self.height() - 2 * m
        if self._pm is not None and not self._pm.isNull():
            p.drawPixmap(m, m, side, side, self._pm)
        x0 = self.height() + 6
        avail = self.width() - x0 - 8
        fm = p.fontMetrics()
        p.setPen(QColor("#ffffff"))
        if fm.horizontalAdvance(self._text) <= avail or not self._marquee:
            p.drawText(
                self.rect().adjusted(x0, 0, -8, 0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                fm.elidedText(self._text, Qt.TextElideMode.ElideRight, avail),
            )
        else:
            p.setClipRect(x0, 0, avail, self.height())
            p.drawText(
                x0 - self._offset,
                (self.height() + fm.height()) // 2 - fm.descent(),
                self._text,
            )

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            pos = QCursor.pos()
            QTimer.singleShot(
                0, lambda: self.glance_requested.emit(QPoint(pos.x(), pos.y()))
            )
        elif ev.button() == Qt.MouseButton.RightButton:
            pos = QCursor.pos()
            QTimer.singleShot(
                0, lambda: self.menu_requested.emit(QPoint(pos.x(), pos.y()))
            )

    def closeEvent(self, ev):
        self._unregister_appbar()
        super().closeEvent(ev)


class WindowsStatusStripTray(WindowsTray):
    """§3.0 主显示（2026-10-17 重设计）：任务栏正上方状态条。

    继承 WindowsTray——通知区图标降为辅助（toast / 兜底），图标绘制、
    tooltip、通知区右键菜单、左键速览全部沿用。
    """

    def __init__(self, app):
        super().__init__(app)
        self.strip: _StatusStripWindow | None = None

    # —— 设置实时读取（保存设置无需重启）——
    @staticmethod
    def _strip_settings() -> tuple[bool, bool]:
        try:
            from zentray.services.settings_manager import SettingsManager

            ap = SettingsManager().appearance
            return bool(ap.statusbar_enabled), bool(ap.statusbar_marquee)
        except Exception:
            return True, False

    def set_state(self, icon: str, text: str):
        super().set_state(icon, text)
        enabled, marquee = self._strip_settings()
        if not enabled:
            self._close_strip()
            return
        if self.strip is None:
            self.strip = _StatusStripWindow()
            self.strip.glance_requested.connect(self.glance_requested)
            self.strip.menu_requested.connect(self.menu.popup)
        self.strip.set_content(
            self._last_pixmap, (text or "").strip() or "ZenTray", marquee
        )

    def _close_strip(self) -> None:
        if self.strip is not None:
            self.strip.close()
            self.strip = None

    def shutdown(self):
        self._close_strip()
        super().shutdown()
