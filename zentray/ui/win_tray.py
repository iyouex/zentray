# zentray/ui/win_tray.py
"""
Windows 托盘后端（docs/design/windows-interaction-design.md §3，2026-10-07 重设计）。

- 主显示：任务栏中央应用按钮 = QPainter 动态图标 + 完整文字标签（§3.0，
  WindowsTaskbarCenterTray）；左键=速览面板、悬停=tooltip
- 辅助：通知区图标（WindowsTray）——右键菜单 / toast / 合并模式兜底
- 图标运行时绘制（饼图/番茄/茶绿/转圈/徽标/倒计时叠加），替代预烘焙 PNG
"""
from __future__ import annotations

import re
import sys

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget, QSystemTrayIcon

from zentray.ui.tray import QtStandardTray

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
# 任务栏中央按钮（设计 §3.0，2026-10-07 重设计）
# 机制回收自搁置分支 feature/win-tray-title：1×1 离屏无边框窗口
# 造任务栏应用按钮，setWindowTitle=轮播文字、setWindowIcon=动态图标。
# ============================================================

def taskbar_label(text: str, max_chars: int, offset: int = 0) -> str:
    """中央按钮标签（纯函数）：超长截断…；offset>0 为跑马灯滚动位。"""
    t = (text or "").strip() or "ZenTray"
    n = max(8, min(32, int(max_chars or 20)))
    if len(t) <= n:
        return t
    if offset <= 0:
        return t[: n - 1] + "…"
    padded = t + "   ·   "
    off = offset % len(padded)
    return (padded[off:] + padded[:off])[:n]


def taskbar_label_visible() -> bool | None:
    """任务栏是否「从不合并」（文字标签可见）。True/False；探测不到（非
    Windows / 键缺失）返回 None，前端隐藏提示行。"""
    if not sys.platform.startswith("win32"):
        return None
    try:
        import winreg

        key = (
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
        )
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            val, _ = winreg.QueryValueEx(k, "TaskbarGlomLevel")
            return int(val) == 2  # 0=始终合并 1=占满时 2=从不
    except Exception:
        return None


class _TaskbarCenterWindow(QWidget):
    """1×1 离屏窗口：系统为它在任务栏生成应用按钮。

    左键按钮 = 窗口被激活 → 拦截 ActivationChange 弹速览面板（锚定光标，
    即按钮位置），随后 hide/show 复位释放前台焦点（窗口永不现身）。
    """

    glance_requested = Signal(QPoint)

    def __init__(self):
        super().__init__()
        self._resetting = False
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinimizeButtonHint  # 保任务栏分组正确
        )
        self.setWindowTitle("ZenTray")
        self.resize(1, 1)
        self.move(-10000, -10000)
        self.show()

    def changeEvent(self, ev):
        if (
            ev.type() == QEvent.Type.ActivationChange
            and self.isActiveWindow()
            and not self._resetting
        ):
            self._resetting = True
            pos = QCursor.pos()
            QTimer.singleShot(0, lambda: self.glance_requested.emit(QPoint(pos.x(), pos.y())))
            # 延迟 hide/show：不在事件处理中重入；复位后交还前台焦点
            def _reset():
                self.hide()
                self.show()
                self._resetting = False

            QTimer.singleShot(0, _reset)
        super().changeEvent(ev)


class WindowsTaskbarCenterTray(WindowsTray):
    """§3.0 主显示：任务栏中央按钮（动态图标+文字标签）。

    继承 WindowsTray——通知区图标降为辅助（菜单锚点/toast/合并模式兜底），
    图标绘制、tooltip、右键菜单、通知区左键速览全部沿用。
    """

    def __init__(self, app):
        super().__init__(app)
        self.taskbar_window: _TaskbarCenterWindow | None = None
        self._tb_text = "ZenTray"
        self._marquee_offset = 0
        self._marquee_timer = QTimer(self)
        self._marquee_timer.setInterval(400)  # 旧分支已验证节奏
        self._marquee_timer.timeout.connect(self._on_marquee_tick)

    # —— 设置实时读取（保存设置无需重启）——
    @staticmethod
    def _tb_settings() -> tuple[bool, int, bool]:
        try:
            from zentray.services.settings_manager import SettingsManager

            ap = SettingsManager().appearance
            return (
                bool(ap.taskbar_center_enabled),
                int(ap.taskbar_label_length),
                bool(ap.taskbar_label_marquee),
            )
        except Exception:
            return True, 20, False

    def set_state(self, icon: str, text: str):
        super().set_state(icon, text)
        enabled, length, marquee = self._tb_settings()
        if not enabled:
            self._close_taskbar_window()
            return
        if self.taskbar_window is None:
            self.taskbar_window = _TaskbarCenterWindow()
            self.taskbar_window.glance_requested.connect(self.glance_requested)
        win = self.taskbar_window
        if self._last_pixmap is not None:
            win.setWindowIcon(QIcon(self._last_pixmap))
        self._tb_text = (text or "").strip() or "ZenTray"
        self._marquee_offset = 0
        self._sync_taskbar_title(length, marquee)
        if marquee and len(self._tb_text) > length:
            if not self._marquee_timer.isActive():
                self._marquee_timer.start()
        elif self._marquee_timer.isActive():
            self._marquee_timer.stop()

    def _on_marquee_tick(self):
        _, length, _ = self._tb_settings()
        self._marquee_offset += 1
        win.setWindowTitle(taskbar_label(self._tb_text, length, self._marquee_offset))

    def _sync_taskbar_title(self, length: int, marquee: bool) -> None:
        if self.taskbar_window is None:
            return
        self.taskbar_window.setWindowTitle(
            taskbar_label(self._tb_text, length, 0 if not marquee else self._marquee_offset)
        )

    def _close_taskbar_window(self) -> None:
        if self._marquee_timer.isActive():
            self._marquee_timer.stop()
        if self.taskbar_window is not None:
            self.taskbar_window.close()
            self.taskbar_window = None

    def shutdown(self):
        self._close_taskbar_window()
        super().shutdown()
