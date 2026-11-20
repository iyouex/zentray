# zentray/ui/win_edge_tray.py
"""Windows 贴边悬浮托盘（2026-11-20 重设计，P1）。

形态：原生 QWidget 胶囊，贴屏幕四边；不占任务栏、不抢焦点。
交互（已确认）：
- 宽边（贴屏侧，整条热区）：悬停显示聚拢曲边箭头；单击 → 任务详情；
  长按 400ms → 拿起拖动。
- 窄边 A（上/下边=左，左/右边=上）→ 插件 / 任务列表；
  窄边 B（上/下边=右，左/右边=下）→ 设置 / 退出。
- 拖动：始终贴四边；4 角 + 4 边中点共 8 个磁吸停顿点（34px 吸住 / 68px
  松手吸附）；半透明宽箭头指向拖动方向；过角旋转 90°。

P1 只接托盘文案/图标（``icon_paint_spec``），详情复用现有 ``/glance``；
侧边菜单先复用托盘菜单项，P2 再接完整 flyout。
"""
from __future__ import annotations

import ctypes
import logging
import os
import re
import sys
import time
from dataclasses import dataclass

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QMenu, QWidget

from zentray.ui.edge_dock import EdgeDock, event_rect, flyout_rect
from zentray.ui.win_flyout import SystemFlyout, TaskPluginFlyout, apply_no_activate
from zentray.ui.win_tray import WindowsTray, icon_paint_spec

logger = logging.getLogger(__name__)

_PRI_COLOR = {
    "high": "#ff6b6b",
    "medium": "#ffc44d",
    "low": "#4ade80",
    "none": "#8b8f98",
}
_ACCENT = "#4cc2ff"
_MARGIN = 44          # 内侧留给悬停箭头/光晕的透明边
_SPINE_BAND = 18      # 胶囊贴屏侧的宽边热区
_END_BAND = 26        # 窄边热区
_LONG_MS = 400
_MAGNET_PX = 34
_RELEASE_PX = 68
_IDLE_MS = 8000


def fullscreen_should_hide(state: int | None) -> bool:
    """QUNS_RUNNING_D3D_FULL_SCREEN=3 / QUNS_PRESENTATION_MODE=4。"""
    return state in (3, 4)


# ---------------------------------------------------------------- 数据


@dataclass
class _CapsuleModel:
    title: str = "ZenTray"
    meta: str = "单击查看详情 · 长按拖动"
    priority: str = "none"
    progress: int = 0
    timer: str = ""
    base: str = "app"

    def update(self, icon: str, text: str) -> None:
        """从托盘 icon 名 + 文案推导胶囊内容（P1 的轻量适配）。"""
        spec = icon_paint_spec(icon, text)
        t = (text or "").strip()
        base = spec.get("base", "app")
        timer = ""
        title = t or "ZenTray"
        if re.match(r"^\d{1,2}:\d{2}", t):
            timer = t.split("·")[0].strip()
            title = "专注中" if base == "tomato" else ("休息中" if base == "break" else "ZenTray")
        else:
            title = re.sub(r"^[⚡📄]\s*", "", t) or "ZenTray"
        if spec.get("spinner"):
            meta = "插件运行中"
        elif spec.get("badge"):
            meta = "报告待查看"
        elif timer:
            meta = "长按拖动可移动"
        elif not t:
            meta = "暂无活跃任务"
        else:
            meta = "单击查看详情 · 长按拖动"
        self.title = title
        self.meta = meta
        self.priority = spec.get("priority") or "none"
        self.progress = int(spec.get("progress") or 0)
        self.timer = timer
        self.base = base

    def update_detail(self, detail: dict) -> None:
        """结构化胶囊数据（P2）：标题/分类/子任务/截止/计时/进度/下一步。"""
        if not detail:
            return
        phase = str(detail.get("phase") or "idle").lower()
        title = str(detail.get("title") or "ZenTray").strip() or "ZenTray"
        category = str(detail.get("category") or "").strip()
        subs_done = int(detail.get("subs_done") or 0)
        subs_total = int(detail.get("subs_total") or 0)
        deadline = str(detail.get("deadline") or "").strip()
        timer = str(detail.get("timer") or "").strip()
        progress = int(detail.get("progress") or 0)
        priority = str(detail.get("priority") or "none").lower()
        if detail.get("meta"):
            meta = str(detail["meta"])
        else:
            parts: list[str] = []
            if category:
                parts.append(category)
            if subs_total:
                parts.append(f"子任务 {subs_done}/{subs_total}")
            if deadline:
                parts.append(f"截止 {deadline}")
            meta = " · ".join(parts) or "单击查看详情"
        self.title = title
        self.meta = meta
        self.priority = priority
        self.progress = max(0, min(100, progress))
        self.timer = timer
        if phase in ("focus", "pomodoro"):
            self.base = "tomato"
        elif phase in ("break", "short_break", "long_break"):
            self.base = "break"
        else:
            self.base = "app"


# ---------------------------------------------------------------- 绘制


def _capsule_path(rect: QRectF, edge: str, radius: float = 18.0) -> QPainterPath:
    """外侧平直贴屏、内侧圆角的半胶囊路径。"""
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    r = min(radius, w / 2, h / 2)
    p = QPainterPath()
    if edge == "bottom":
        p.moveTo(x, y + h)
        p.lineTo(x, y + r)
        p.quadTo(x, y, x + r, y)
        p.lineTo(x + w - r, y)
        p.quadTo(x + w, y, x + w, y + r)
        p.lineTo(x + w, y + h)
    elif edge == "top":
        p.moveTo(x, y)
        p.lineTo(x, y + h - r)
        p.quadTo(x, y + h, x + r, y + h)
        p.lineTo(x + w - r, y + h)
        p.quadTo(x + w, y + h, x + w, y + h - r)
        p.lineTo(x + w, y)
    elif edge == "left":
        p.moveTo(x, y)
        p.lineTo(x + w - r, y)
        p.quadTo(x + w, y, x + w, y + r)
        p.lineTo(x + w, y + h - r)
        p.quadTo(x + w, y + h, x + w - r, y + h)
        p.lineTo(x, y + h)
    else:
        p.moveTo(x + w, y)
        p.lineTo(x + r, y)
        p.quadTo(x, y, x, y + r)
        p.lineTo(x, y + h - r)
        p.quadTo(x, y + h, x + r, y + h)
        p.lineTo(x + w, y + h)
    p.closeSubpath()
    return p


def _paint_shell(p: QPainter, rect: QRectF, edge: str, hover: bool, light: bool = False, radius: float = 18.0) -> None:
    path = _capsule_path(rect, edge, radius)
    grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    if light:
        grad.setColorAt(0.0, QColor(252, 253, 255, 248))
        grad.setColorAt(1.0, QColor(226, 234, 244, 252))
    else:
        grad.setColorAt(0.0, QColor(44, 49, 61, 238))
        grad.setColorAt(1.0, QColor(22, 25, 32, 250))
    p.fillPath(path, grad)
    if light:
        p.setPen(QPen(QColor(0, 0, 0, 62 if hover else 48), 1))
    else:
        p.setPen(QPen(QColor(255, 255, 255, 42 if hover else 32), 1))
    p.drawPath(path)
    # 内侧 1px 高光
    p.setPen(QPen(QColor(0, 0, 0, 16) if light else QColor(255, 255, 255, 26), 1))
    if edge == "bottom":
        p.drawLine(QPointF(rect.left() + 18, rect.top() + 0.5), QPointF(rect.right() - 18, rect.top() + 0.5))
    elif edge == "top":
        p.drawLine(QPointF(rect.left() + 18, rect.bottom() - 0.5), QPointF(rect.right() - 18, rect.bottom() - 0.5))
    elif edge == "left":
        p.drawLine(QPointF(rect.right() - 0.5, rect.top() + 18), QPointF(rect.right() - 0.5, rect.bottom() - 18))
    else:
        p.drawLine(QPointF(rect.left() + 0.5, rect.top() + 18), QPointF(rect.left() + 0.5, rect.bottom() - 18))


def _paint_ring(p: QPainter, rect: QRectF, progress: int, color: QColor, text: str, light: bool = False) -> None:
    p.setBrush(Qt.BrushStyle.NoBrush)
    bg = QColor(color)
    bg.setAlpha(64)
    pen = QPen(bg)
    pen.setWidth(3)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawEllipse(rect.adjusted(1.5, 1.5, -1.5, -1.5))
    if progress > 0:
        pen.setColor(color)
        p.setPen(pen)
        p.drawArc(rect.adjusted(1.5, 1.5, -1.5, -1.5), 90 * 16, -int(progress * 3.6 * 16))
    p.setBrush(QColor(247, 249, 252) if light else QColor(25, 29, 37))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(rect.adjusted(5, 5, -5, -5))
    f = QFont("Cascadia Code")
    f.setPixelSize(8)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#3b4a5c") if light else QColor("#c9d6e8"))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)


def _paint_timer(p: QPainter, rect: QRectF, text: str, base: str, light: bool = False) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 14) if light else QColor(255, 255, 255, 18))
    p.drawRoundedRect(rect, 8, 8)
    dot = QColor("#3aa981") if base == "break" else QColor("#ff6b6b")
    p.setBrush(dot)
    p.drawEllipse(QRectF(rect.left() + 9, rect.center().y() - 4, 8, 8))
    f = QFont("Cascadia Code")
    f.setPixelSize(11)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#1f2a37") if light else QColor("#e8f3ff"))
    p.drawText(rect.adjusted(22, 0, -7, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)


def _paint_chevron(p: QPainter, center: QPointF, edge: str, light: bool = False) -> None:
    pen = QPen(QColor("#7a8798") if light else QColor("#9aa8bd"), 1.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    x, y = center.x(), center.y()
    if edge == "bottom":  # 指向内侧（上）
        path = QPainterPath()
        path.moveTo(x - 4, y - 1)
        path.lineTo(x, y - 5)
        path.lineTo(x + 4, y - 1)
    elif edge == "top":
        path = QPainterPath()
        path.moveTo(x - 4, y + 1)
        path.lineTo(x, y + 5)
        path.lineTo(x + 4, y + 1)
    elif edge == "left":
        path = QPainterPath()
        path.moveTo(x + 1, y - 4)
        path.lineTo(x + 5, y)
        path.lineTo(x + 1, y + 4)
    else:
        path = QPainterPath()
        path.moveTo(x - 1, y - 4)
        path.lineTo(x - 5, y)
        path.lineTo(x - 1, y + 4)
    p.drawPath(path)


def _paint_capsule(p: QPainter, rect: QRectF, edge: str, model: _CapsuleModel, hover: bool = False, light: bool = False) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    _paint_shell(p, rect, edge, hover, light)
    color = QColor(_PRI_COLOR.get(model.priority, _PRI_COLOR["none"]))
    if model.base == "tomato":
        color = QColor("#ff6b6b")
    elif model.base == "break":
        color = QColor("#3aa981")

    if edge in ("top", "bottom"):
        ring_d = 30
        ring = QRectF(rect.left() + 13, rect.center().y() - ring_d / 2, ring_d, ring_d)
        _paint_ring(p, ring, model.progress, color, str(model.progress), light)
        timer_w = 78 if model.timer else 0
        timer_x = rect.right() - timer_w - 34 if model.timer else rect.right() - 34
        text_x = ring.right() + 11
        text_w = max(20, timer_x - text_x - 8)
        tf = QFont("Segoe UI")
        tf.setPixelSize(13)
        tf.setWeight(QFont.Weight.DemiBold)
        p.setFont(tf)
        p.setPen(QColor("#17202b") if light else QColor("#e9eef8"))
        fm = QFontMetrics(tf)
        p.drawText(
            QRect(int(text_x), int(rect.top() + 7), int(text_w), 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            fm.elidedText(model.title, Qt.TextElideMode.ElideRight, int(text_w)),
        )
        mf = QFont("Segoe UI")
        mf.setPixelSize(10)
        p.setFont(mf)
        p.setPen(QColor("#6b7280") if light else QColor("#9aa8bd"))
        fm2 = QFontMetrics(mf)
        p.drawText(
            QRect(int(text_x), int(rect.top() + 27), int(text_w), 16),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            fm2.elidedText(model.meta, Qt.TextElideMode.ElideRight, int(text_w)),
        )
        if model.timer:
            _paint_timer(p, QRectF(timer_x, rect.center().y() - 14, timer_w, 28), model.timer, model.base, light)
        _paint_chevron(p, QPointF(rect.right() - 16, rect.center().y()), edge, light)
    else:
        ring_d = 30
        ring = QRectF(rect.center().x() - ring_d / 2, rect.top() + 14, ring_d, ring_d)
        _paint_ring(p, ring, model.progress, color, str(model.progress), light)
        y = ring.bottom() + 5
        if model.timer:
            f = QFont("Cascadia Code")
            f.setPixelSize(9)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#1f2a37") if light else QColor("#bfe8ff"))
            p.drawText(QRect(int(rect.left()), int(y), int(rect.width()), 14), Qt.AlignmentFlag.AlignCenter, model.timer)
            y += 17
        f = QFont("Segoe UI")
        f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QColor("#17202b") if light else QColor("#e9eef8"))
        fm = QFontMetrics(f)
        step = fm.height()
        max_chars = max(1, int((rect.bottom() - 24 - y) / step))
        chars = list(model.title)
        if len(chars) > max_chars:
            chars = chars[: max(1, max_chars - 1)] + ["…"]
        for i, ch in enumerate(chars):
            p.drawText(
                QRect(int(rect.left()), int(y + i * step), int(rect.width()), int(step)),
                Qt.AlignmentFlag.AlignCenter,
                ch,
            )
        _paint_chevron(p, QPointF(rect.center().x(), rect.bottom() - 14), edge, light)
    p.restore()


def _arrow_path() -> QPainterPath:
    """一条朝上的曲边箭头（局部坐标，中心在原点上方）。"""
    p = QPainterPath()
    p.moveTo(0, 14)
    p.cubicTo(-4, 6, -4, -2, 0, -10)
    p.moveTo(-6, -2)
    p.lineTo(0, -12)
    p.lineTo(6, -2)
    return p


def _paint_hover_arrows(p: QPainter, cap: QRectF, edge: str, light: bool = False) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    if edge == "bottom":
        cx, cy = cap.center().x(), cap.top() - _MARGIN / 2
        rot = 0.0
    elif edge == "top":
        cx, cy = cap.center().x(), cap.bottom() + _MARGIN / 2
        rot = 180.0
    elif edge == "left":
        cx, cy = cap.right() + _MARGIN / 2, cap.center().y()
        rot = 90.0
    else:
        cx, cy = cap.left() - _MARGIN / 2, cap.center().y()
        rot = -90.0
    accent = QColor("#0067c0") if light else QColor(_ACCENT)
    glow = QColor(accent)
    glow.setAlpha(55)
    for i, dx in enumerate((-34, 34)):
        p.save()
        p.translate(cx + dx, cy)
        p.rotate(rot)
        if i == 0:
            p.scale(-1, 1)
        p.setBrush(Qt.BrushStyle.NoBrush)
        pen = QPen(glow, 6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawPath(_arrow_path())
        pen = QPen(accent, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.drawPath(_arrow_path())
        p.restore()
    # 贴屏边 1px 强调线
    line_col = QColor(accent)
    line_col.setAlpha(120)
    p.setPen(QPen(line_col, 1))
    if edge == "bottom":
        p.drawLine(QPointF(cap.left() + 20, cap.bottom() - 0.5), QPointF(cap.right() - 20, cap.bottom() - 0.5))
    elif edge == "top":
        p.drawLine(QPointF(cap.left() + 20, cap.top() + 0.5), QPointF(cap.right() - 20, cap.top() + 0.5))
    elif edge == "left":
        p.drawLine(QPointF(cap.left() + 0.5, cap.top() + 20), QPointF(cap.left() + 0.5, cap.bottom() - 20))
    else:
        p.drawLine(QPointF(cap.right() - 0.5, cap.top() + 20), QPointF(cap.right() - 0.5, cap.bottom() - 20))
    p.restore()


def _paint_ear(p: QPainter, rect: QRectF, edge: str, model: _CapsuleModel, light: bool = False) -> None:
    """收纳态边缘耳：进度环 + 计时/百分比 + 箭头。"""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    _paint_shell(p, rect, edge, False, light, radius=12)
    color = QColor(_PRI_COLOR.get(model.priority, _PRI_COLOR["none"]))
    if model.base == "tomato":
        color = QColor("#ff6b6b")
    elif model.base == "break":
        color = QColor("#3aa981")
    text = model.timer or (f"{model.progress}%" if model.progress else "—")
    d = 22
    if edge in ("top", "bottom"):
        ring = QRectF(rect.left() + 9, rect.center().y() - d / 2, d, d)
        _paint_ring(p, ring, model.progress, color, str(model.progress), light)
        f = QFont("Cascadia Code")
        f.setPixelSize(10)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#1f2a37") if light else QColor("#bfe8ff"))
        p.drawText(
            QRect(int(rect.left() + 37), int(rect.top()), int(rect.width() - 56), int(rect.height())),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        _paint_chevron(p, QPointF(rect.right() - 12, rect.center().y()), edge, light)
    else:
        ring = QRectF(rect.center().x() - d / 2, rect.top() + 9, d, d)
        _paint_ring(p, ring, model.progress, color, str(model.progress), light)
        f = QFont("Cascadia Code")
        f.setPixelSize(9)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#1f2a37") if light else QColor("#bfe8ff"))
        p.drawText(
            QRect(int(rect.left()), int(ring.bottom() + 3), int(rect.width()), 14),
            Qt.AlignmentFlag.AlignCenter,
            text,
        )
        _paint_chevron(p, QPointF(rect.center().x(), rect.bottom() - 11), edge, light)
    p.restore()


class _EventPill(QWidget):
    """事件态胶囊（B）：报告完成/番茄结束短暂弹出，点击回调，3s 自动缩回。"""

    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setFixedHeight(38)
        self._text = ""
        self._kind = "info"
        self._light = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_event(self, text: str, rect: tuple[int, int, int, int], kind: str = "info",
                   duration_ms: int = 3000, light: bool = False) -> None:
        self._text = text or ""
        self._kind = kind or "info"
        self._light = bool(light)
        self.setGeometry(*rect)
        self.show()
        self.raise_()
        apply_no_activate(self)
        self._timer.start(max(800, int(duration_ms)))
        self.update()

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        self.hide()
        event.accept()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(0, 0, -1, -1)
        if self._light:
            bg, border, txt = QColor(252, 253, 255, 248), QColor(0, 0, 0, 40), QColor("#17202b")
        else:
            bg, border, txt = QColor(20, 25, 34, 245), QColor(255, 255, 255, 40), QColor("#eaf2fc")
        p.setBrush(bg)
        p.setPen(QPen(border, 1))
        p.drawRoundedRect(rect, 12, 12)
        color = {"success": "#4ade80", "error": "#ff6b6b", "report": "#4cc2ff"}.get(self._kind, "#4cc2ff")
        p.setBrush(QColor(color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(12, rect.center().y() - 4, 8, 8))
        f = QFont("Segoe UI")
        f.setPixelSize(11)
        p.setFont(f)
        fm = QFontMetrics(f)
        text = fm.elidedText(self._text, Qt.TextElideMode.ElideRight, max(40, rect.width() - 52))
        p.setPen(txt)
        p.drawText(
            QRect(28, 0, rect.width() - 44, rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        p.setPen(QPen(QColor("#9aa8bd"), 1.4))
        x, y = rect.right() - 14, rect.center().y()
        p.drawLine(QPointF(x - 2, y - 4), QPointF(x + 2, y))
        p.drawLine(QPointF(x + 2, y), QPointF(x - 2, y + 4))


# ---------------------------------------------------------------- 胶囊窗口


class _CapsuleWindow(QWidget):
    """贴边胶囊本体：四边停靠、宽边悬停/单击/长按、窄边菜单。"""

    spine_clicked = Signal(QPoint)
    content_clicked = Signal(QPoint)
    system_clicked = Signal(QPoint)
    dock_changed = Signal(str, float)

    def __init__(self, dock: EdgeDock):
        super().__init__()
        self._dock = dock
        self._model = _CapsuleModel()
        self._screen = QGuiApplication.primaryScreen()
        self._cap_rect = QRect()
        self._hover = False
        self._press_zone: str | None = None
        self._press_pos = QPoint()
        self._press_global = QPoint()
        self._press_t0 = 0.0
        self._press_progress = 0.0
        self._dragging = False
        self._overlay: _DragOverlay | None = None
        self._drag_origin = ("bottom", 0.75)
        self._light = False
        self._multi_monitor = True

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMouseTracking(True)

        self._long_timer = QTimer(self)
        self._long_timer.setSingleShot(True)
        self._long_timer.setInterval(_LONG_MS)
        self._long_timer.timeout.connect(self._begin_drag)
        self._press_tick = QTimer(self)
        self._press_tick.setInterval(30)
        self._press_tick.timeout.connect(self._tick_press)
        self._idle_enabled = True
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.setInterval(_IDLE_MS)
        self._idle_timer.timeout.connect(self._maybe_compact)
        self._idle_timer.start()

        self.reposition(show=False)
        self.show()
        apply_no_activate(self)

    # —— 几何 / 窗口 ——

    def reposition(self, show: bool = True) -> None:
        screens = QGuiApplication.screens()
        if self._screen is None or self._screen not in screens:
            self._screen = QGuiApplication.primaryScreen()
        if self._screen is None:
            return
        avail = self._screen.availableGeometry()
        self._dock.area_w = max(1, avail.width())
        self._dock.area_h = max(1, avail.height())
        x, y, w, h = self._dock.geometry()
        edge = self._dock.edge
        if edge == "bottom":
            win = QRect(x, y - _MARGIN, w, h + _MARGIN)
            self._cap_rect = QRect(0, _MARGIN, w, h)
        elif edge == "top":
            win = QRect(x, y, w, h + _MARGIN)
            self._cap_rect = QRect(0, 0, w, h)
        elif edge == "left":
            win = QRect(x, y, w + _MARGIN, h)
            self._cap_rect = QRect(0, 0, w, h)
        else:
            win = QRect(x - _MARGIN, y, w + _MARGIN, h)
            self._cap_rect = QRect(_MARGIN, 0, w, h)
        self.setGeometry(avail.x() + win.x(), avail.y() + win.y(), win.width(), win.height())
        if show and not self._dragging:
            self.show()
        self.update()

    def set_content(self, icon: str, text: str) -> None:
        self._model.update(icon, text)
        if self._model.timer and self._dock.compact:
            self.set_compact(False)
        if self._overlay is not None:
            self._overlay.update()
        self.update()

    def set_detail(self, detail: dict) -> None:
        if not detail:
            return
        self._model.update_detail(detail)
        if self._model.timer and self._dock.compact:
            self.set_compact(False)
        if self._overlay is not None:
            self._overlay.update()
        self.update()

    def set_light(self, light: bool) -> None:
        self._light = bool(light)
        if self._overlay is not None:
            self._overlay.set_light(self._light)
        self.update()

    def set_idle_ms(self, ms: int) -> None:
        self._idle_timer.setInterval(max(1000, int(ms)))

    def set_longpress_ms(self, ms: int) -> None:
        self._long_timer.setInterval(max(150, int(ms)))

    def set_multi_monitor(self, enabled: bool) -> None:
        self._multi_monitor = bool(enabled)

    def set_compact(self, compact: bool) -> None:
        compact = bool(compact)
        if compact == self._dock.compact:
            return
        self._dock.compact = compact
        if compact:
            self._hover = False
            self._idle_timer.stop()
        self.reposition()
        self.update()

    def set_idle_enabled(self, enabled: bool) -> None:
        self._idle_enabled = bool(enabled)
        if not self._idle_enabled:
            self._idle_timer.stop()
        else:
            self._schedule_idle()

    def _schedule_idle(self) -> None:
        if self._idle_enabled and not self._dock.compact and not self._dragging:
            self._idle_timer.start()

    def _maybe_compact(self) -> None:
        if self._dragging or not self._idle_enabled or self._hover or self._dock.compact:
            return
        if self._model.timer:  # 番茄 / 休息中不收纳
            self._idle_timer.start()
            return
        self.set_compact(True)

    def set_dock(self, edge: str, ratio: float) -> None:
        self._dock.set(edge, ratio)
        self.reposition()

    def edge(self) -> str:
        return self._dock.edge

    def capsule_rect_global(self) -> QRect:
        """胶囊本体（不含内侧箭头带）的屏幕矩形。"""
        return QRect(self.mapToGlobal(self._cap_rect.topLeft()), self._cap_rect.size())

    def screen(self):
        return self._screen

    def screen_name(self) -> str:
        return self._screen.name() if self._screen is not None else ""

    def set_screen(self, screen) -> None:
        if screen is not None and screen is not self._screen:
            self._screen = screen
            self.reposition()

    # —— 绘制 ——

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cap = QRectF(self._cap_rect)
        if self._dock.compact:
            _paint_ear(p, cap, self._dock.edge, self._model, light=self._light)
        else:
            if self._hover and not self._dragging:
                _paint_hover_arrows(p, cap, self._dock.edge, light=self._light)
            _paint_capsule(p, cap, self._dock.edge, self._model, hover=self._hover, light=self._light)
        if self._press_progress > 0:
            self._paint_press(p)

    def _paint_press(self, p: QPainter) -> None:
        r = 16.0
        rect = QRectF(self._press_pos.x() - r, self._press_pos.y() - r, r * 2, r * 2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(76, 194, 255, 80), 3))
        p.drawEllipse(rect)
        pen = QPen(QColor(_ACCENT), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 90 * 16, -int(360 * 16 * self._press_progress))
        f = QFont("Segoe UI")
        f.setPixelSize(7)
        p.setFont(f)
        p.setPen(QColor("#dff4ff"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "长按")

    # —— 鼠标 / 悬停 ——

    def enterEvent(self, event) -> None:
        self._idle_timer.stop()
        if self._dock.compact:
            self.set_compact(False)
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self._schedule_idle()
        self.update()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        if self._press_zone is not None:
            if (pos - self._press_pos).manhattanLength() > 8:
                self._cancel_press()
        hover = self._zone_at(pos) == "spine"
        if hover != self._hover:
            self._hover = hover
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._idle_timer.stop()
        if self._dock.compact:
            self.set_compact(False)
        pos = event.position().toPoint()
        self._press_pos = pos
        self._press_global = event.globalPosition().toPoint()
        self._press_zone = self._zone_at(pos)
        self._press_t0 = time.monotonic()
        self._press_progress = 0.0
        if self._press_zone == "spine":
            self._long_timer.start()
            self._press_tick.start()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        zone = self._press_zone
        if self._press_zone is not None:
            self._cancel_press()
            elapsed = (time.monotonic() - self._press_t0) * 1000
            if elapsed < self._long_timer.interval() + 120:
                if zone in ("spine", "body"):
                    self.spine_clicked.emit(self._press_global)
                elif zone == "content":
                    self.content_clicked.emit(self._press_global)
                elif zone == "system":
                    self.system_clicked.emit(self._press_global)
        self._press_zone = None
        self._schedule_idle()
        self.update()
        event.accept()

    def _cancel_press(self) -> None:
        self._long_timer.stop()
        self._press_tick.stop()
        self._press_progress = 0.0
        self._press_zone = None
        self.update()

    def _tick_press(self) -> None:
        self._press_progress = min(1.0, (time.monotonic() - self._press_t0) * 1000 / _LONG_MS)
        self.update()

    def _zone_at(self, pos: QPoint) -> str:
        """margin/贴屏宽边 = spine；两端 = content/system；其余 = body。"""
        cap = self._cap_rect
        edge = self._dock.edge
        # margin 整块都算宽边热区（箭头所在）
        if edge == "bottom" and pos.y() < cap.top():
            return "spine"
        if edge == "top" and pos.y() > cap.bottom():
            return "spine"
        if edge == "left" and pos.x() > cap.right():
            return "spine"
        if edge == "right" and pos.x() < cap.left():
            return "spine"
        if not cap.contains(pos):
            return "body"
        if edge in ("top", "bottom"):
            if pos.x() <= cap.left() + _END_BAND:
                return "content"
            if pos.x() >= cap.right() - _END_BAND:
                return "system"
            if edge == "bottom" and pos.y() >= cap.bottom() - _SPINE_BAND:
                return "spine"
            if edge == "top" and pos.y() <= cap.top() + _SPINE_BAND:
                return "spine"
        else:
            if pos.y() <= cap.top() + _END_BAND:
                return "content"
            if pos.y() >= cap.bottom() - _END_BAND:
                return "system"
            if edge == "left" and pos.x() <= cap.left() + _SPINE_BAND:
                return "spine"
            if edge == "right" and pos.x() >= cap.right() - _SPINE_BAND:
                return "spine"
        return "body"

    # —— 长按拖动 ——

    def _begin_drag(self) -> None:
        self._cancel_press()
        if self._dock.compact:
            self.set_compact(False)
        if self._dragging:
            return
        self._dragging = True
        self._drag_origin = (self._dock.edge, self._dock.ratio)
        self.hide()
        self._overlay = _DragOverlay(self._dock, self._model, self._screen, self, light=self._light, multi=self._multi_monitor)
        self._overlay.finished.connect(self._on_drag_finished)
        self._overlay.cancelled.connect(self._on_drag_cancelled)
        self._overlay.start()

    def _on_drag_finished(self, edge: str, ratio: float, screen_name: str = "") -> None:
        for s in QGuiApplication.screens():
            if screen_name and s.name() == screen_name:
                self._screen = s
                break
        self._dock.set(edge, ratio)
        self._dragging = False
        self._overlay = None
        self.reposition()
        self.dock_changed.emit(edge, ratio)

    def _on_drag_cancelled(self) -> None:
        self._dock.set(*self._drag_origin)
        self._dragging = False
        self._overlay = None
        self.reposition()

    def shutdown(self) -> None:
        self._long_timer.stop()
        self._press_tick.stop()
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None
        self.close()


# ---------------------------------------------------------------- 拖动覆盖层


class _DragOverlay(QWidget):
    """拖动时的全屏透明覆盖层：绘制 8 个停顿点、宽箭头与胶囊预览。"""

    finished = Signal(str, float, str)
    cancelled = Signal()

    def __init__(self, dock: EdgeDock, model: _CapsuleModel, screen, parent=None, light: bool = False, multi: bool = True):
        super().__init__(parent)
        self._light = bool(light)
        self._multi = bool(multi)
        self._dock = EdgeDock(dock.area_w, dock.area_h, dock.edge, dock.ratio, dock.magnet_px, dock.release_px)
        self._model = model
        self._screen = screen
        self._origin = QPoint()
        self._last = QPoint()
        self._angle = 0.0
        if screen is not None:
            virtual = (
                QGuiApplication.primaryScreen().virtualGeometry()
                if self._multi
                else screen.geometry()
            )
            avail = screen.availableGeometry()
            self._origin = QPoint(avail.x() - virtual.x(), avail.y() - virtual.y())
            self.setGeometry(virtual)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMouseTracking(True)

    def set_light(self, light: bool) -> None:
        self._light = bool(light)
        self.update()

    def start(self) -> None:
        self._last = QCursor.pos()
        self.show()
        self.raise_()
        apply_no_activate(self)
        try:
            self.grabMouse()
        except Exception:
            pass
        self.update()

    def mouseMoveEvent(self, event) -> None:
        pos = event.position().toPoint()
        gp = event.globalPosition().toPoint()
        scr = QGuiApplication.screenAt(gp) if self._multi else None
        if scr is not None and scr is not self._screen:
            self._screen = scr
            virtual = QGuiApplication.primaryScreen().virtualGeometry()
            avail = scr.availableGeometry()
            self._origin = QPoint(avail.x() - virtual.x(), avail.y() - virtual.y())
            self._dock.area_w = max(1, avail.width())
            self._dock.area_h = max(1, avail.height())
        dx, dy = pos.x() - self._last.x(), pos.y() - self._last.y()
        self._last = pos
        if abs(dx) >= abs(dy):
            if abs(dx) >= 1:
                self._angle = 0.0 if dx >= 0 else 180.0
        elif abs(dy) >= 1:
            self._angle = 90.0 if dy >= 0 else -90.0
        x = pos.x() - self._origin.x()
        y = pos.y() - self._origin.y()
        edge, ratio = self._dock.project(x, y)
        ratio = self._dock.magnetize(edge, ratio)
        self._dock.set(edge, ratio)
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        edge = self._dock.edge
        ratio = self._dock.release_snap(edge, self._dock.ratio)
        self._dock.set(edge, ratio)
        self._finish(edge, ratio)
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()
            event.accept()
            return
        super().keyPressEvent(event)

    def _finish(self, edge: str, ratio: float) -> None:
        try:
            self.releaseMouse()
        except Exception:
            pass
        self.hide()
        self.finished.emit(edge, ratio, self._screen.name() if self._screen is not None else "")
        self.deleteLater()

    def _cancel(self) -> None:
        try:
            self.releaseMouse()
        except Exception:
            pass
        self.hide()
        self.cancelled.emit()
        self.deleteLater()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        area = QRectF(self._origin.x(), self._origin.y(), self._dock.area_w, self._dock.area_h)
        # 8 个停顿点（4 角 + 4 边中点）
        det = self._dock.detent_name()
        w, h = self._dock.area_w, self._dock.area_h
        pts = {
            "top-left": QPointF(area.left(), area.top()),
            "top-center": QPointF(area.left() + w / 2, area.top()),
            "top-right": QPointF(area.right(), area.top()),
            "right-center": QPointF(area.right(), area.top() + h / 2),
            "bottom-right": QPointF(area.right(), area.bottom()),
            "bottom-center": QPointF(area.left() + w / 2, area.bottom()),
            "bottom-left": QPointF(area.left(), area.bottom()),
            "left-center": QPointF(area.left(), area.top() + h / 2),
        }
        for name, pt in pts.items():
            on = name == det
            p.save()
            p.translate(pt)
            p.rotate(45)
            size = 12 if on else 8
            p.setPen(QPen(QColor(76, 194, 255, 230 if on else 140), 1))
            p.setBrush(QColor(76, 194, 255, 220 if on else 60))
            p.drawRect(QRectF(-size / 2, -size / 2, size, size))
            p.restore()
        # 拖动宽箭头（在胶囊之下）
        gx, gy, gw, gh = self._dock.geometry()
        cx = self._origin.x() + gx + gw / 2
        cy = self._origin.y() + gy + gh / 2
        p.save()
        p.translate(cx, cy)
        p.rotate(self._angle)
        arrow = QPolygonF(
            [
                QPointF(0, -26),
                QPointF(150, -26),
                QPointF(150, -46),
                QPointF(230, 0),
                QPointF(150, 46),
                QPointF(150, 26),
                QPointF(0, 26),
            ]
        )
        p.setPen(QPen(QColor(76, 194, 255, 140), 1.2))
        p.setBrush(QColor(76, 194, 255, 55))
        p.drawPolygon(arrow)
        p.restore()
        # 胶囊预览
        cap = QRectF(self._origin.x() + gx, self._origin.y() + gy, gw, gh)
        _paint_capsule(p, cap, self._dock.edge, self._model, hover=True, light=self._light)


# ---------------------------------------------------------------- 托盘后端


class WindowsEdgeTray(WindowsTray):
    """通知区图标（toast/兜底）+ 贴边胶囊（主显示）。

    继承 ``WindowsTray``：动态图标、tooltip、右键菜单、通知区左键速览沿用。
    """

    def __init__(self, app):
        super().__init__(app)
        self.capsule: _CapsuleWindow | None = None
        self._flyout_provider = None
        self._flyout = None
        self._event = None
        self._event_cb = None
        self._light = self._system_is_light()
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            raise RuntimeError("no screen")
        avail = screen.availableGeometry()
        appr = self._appearance()
        edge = str(getattr(appr, "win_tray_edge", "bottom") or "bottom").lower()
        if edge not in ("top", "bottom", "left", "right"):
            edge = "bottom"
        try:
            ratio = float(getattr(appr, "win_tray_ratio", 0.75))
        except (TypeError, ValueError):
            ratio = 0.75
        ratio = max(0.0, min(1.0, ratio))
        self._dock = EdgeDock(avail.width(), avail.height(), edge, ratio)
        self._idle_ms = max(2, int(getattr(appr, "win_tray_idle_sec", 8) or 8)) * 1000
        self._long_ms = max(150, int(getattr(appr, "win_tray_longpress_ms", 400) or 400))
        self._hide_fullscreen = bool(getattr(appr, "win_tray_hide_fullscreen", True))
        self._multi_monitor = str(getattr(appr, "win_tray_monitor", "primary") or "primary") == "all"
        self._hidden_fullscreen = False
        self._hooked_screens: set[str] = set()
        self._dock_memory: dict[str, tuple[str, float]] = {}
        self._fs_timer = QTimer(self)
        self._fs_timer.setInterval(500)
        self._fs_timer.timeout.connect(self._poll_fullscreen)
        self._fs_timer.start()
        self._connect_screens()
        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_color_scheme_changed)
        except Exception:
            pass

    @staticmethod
    def _system_is_light() -> bool:
        """系统深浅：Qt colorScheme 优先，Windows 回退注册表。"""
        try:
            hints = QGuiApplication.styleHints()
            scheme = hints.colorScheme()
            light = getattr(getattr(Qt, "ColorScheme", None), "Light", None)
            dark = getattr(getattr(Qt, "ColorScheme", None), "Dark", None)
            if light is not None and scheme == light:
                return True
            if dark is not None and scheme == dark:
                return False
        except Exception:
            pass
        if sys.platform == "win32":
            try:
                import winreg

                path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as k:
                    val, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
                    return bool(val)
            except Exception:
                pass
        return False

    def _on_color_scheme_changed(self, *_args) -> None:
        light = self._system_is_light()
        if light == self._light:
            return
        self._light = light
        if self.capsule is not None:
            self.capsule.set_light(light)
        if self._event is not None:
            self._event._light = light
            self._event.update()
        if self._flyout is not None:
            self._flyout.set_light(light)

    def _connect_screens(self) -> None:
        app = QGuiApplication.instance()
        if app is not None:
            try:
                app.primaryScreenChanged.connect(self._on_screen_changed)
                app.screenAdded.connect(self._on_screen_changed)
                app.screenRemoved.connect(self._on_screen_changed)
            except Exception:
                pass
        self._on_screen_changed()

    def _on_screen_changed(self, *_args) -> None:
        """工作区/分辨率/DPI/显示器增删 → 重排胶囊；屏幕被拔掉回主屏。"""
        for s in QGuiApplication.screens():
            key = s.name()
            if key in self._hooked_screens:
                continue
            self._hooked_screens.add(key)
            try:
                s.availableGeometryChanged.connect(self._on_screen_changed)
                s.geometryChanged.connect(self._on_screen_changed)
            except Exception:
                pass
        if self.capsule is None:
            return
        names = {s.name() for s in QGuiApplication.screens()}
        if self.capsule.screen_name() not in names:
            self.capsule.set_screen(QGuiApplication.primaryScreen())
        else:
            self.capsule.reposition()

    def _poll_fullscreen(self) -> None:
        """全屏/演示让路：隐藏胶囊与 flyout，退出后恢复（Windows only）。"""
        if sys.platform != "win32" or not self._hide_fullscreen:
            return
        hide = False
        try:
            state = ctypes.c_int(0)
            hr = ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state))
            hide = hr == 0 and fullscreen_should_hide(state.value)
        except Exception:
            hide = False
        if hide == self._hidden_fullscreen:
            return
        self._hidden_fullscreen = hide
        if hide:
            self._close_flyout()
            if self._event is not None:
                self._event.hide()
            if self.capsule is not None and not self.capsule._dragging:
                self.capsule.hide()
        elif self.capsule is not None:
            self.capsule.show()

    @staticmethod
    def _appearance():
        try:
            from zentray.services.settings_manager import SettingsManager

            return SettingsManager().appearance
        except Exception:
            return None

    @staticmethod
    def _enabled() -> bool:
        appr = WindowsEdgeTray._appearance()
        if appr is None:
            return True
        return bool(
            getattr(appr, "win_tray_enabled", getattr(appr, "statusbar_enabled", True))
        )

    def _ensure_capsule(self) -> _CapsuleWindow:
        if self.capsule is None:
            self.capsule = _CapsuleWindow(self._dock)
            self.capsule.spine_clicked.connect(self._on_spine)
            self.capsule.content_clicked.connect(self._on_content)
            self.capsule.system_clicked.connect(self._on_system)
            self.capsule.dock_changed.connect(self._on_dock_changed)
        self.capsule.set_idle_ms(self._idle_ms)
        self.capsule.set_longpress_ms(self._long_ms)
        self.capsule.set_multi_monitor(self._multi_monitor)
        self.capsule.set_light(self._light)
        return self.capsule

    def set_state(self, icon: str, text: str):
        super().set_state(icon, text)
        if not self._enabled():
            self._close_capsule()
            return
        self._ensure_capsule().set_content(icon, text)

    def set_detail(self, detail: dict) -> None:
        if not detail:
            return
        if not self._enabled():
            self._close_capsule()
            return
        self._ensure_capsule().set_detail(detail)

    def _on_dock_changed(self, edge: str, ratio: float) -> None:
        name = self.capsule.screen_name() if self.capsule is not None else ""
        self._dock_memory[name] = (edge, ratio)
        logger.info("贴边胶囊位置: %s %.2f (%s)", edge, ratio, name)
        # 拖动后记忆默认位置（测试进程不写真实设置）
        if sys.platform == "win32" and not os.environ.get("PYTEST_CURRENT_TEST"):
            try:
                from zentray.services.settings_manager import SettingsManager

                sm = SettingsManager()
                sm.appearance.win_tray_edge = edge
                sm.appearance.win_tray_ratio = round(float(ratio), 4)
                sm.save()
            except Exception:
                logger.exception("贴边位置持久化失败")

    def set_icon(self, name: str) -> None:
        # 图标变化同样刷新胶囊（父类 set_icon 只重绘通知区）
        self.set_state(name, self._last_label)

    def _on_spine(self, pos: QPoint) -> None:
        # P1：复用现有 /glance 详情面板；P2 再补「下一步操作」卡
        self.glance_requested.emit(pos)

    def show_event(self, text: str, kind: str = "info", on_click=None, duration_ms: int = 3000) -> None:
        """事件态胶囊：报告完成/番茄结束短暂弹出（P4）。"""
        if self.capsule is None or not self._enabled():
            return
        if self._event is None:
            self._event = _EventPill()
            self._event.clicked.connect(self._on_event_clicked)
        self._event_cb = on_click
        screen = self.capsule.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            return
        cap = self.capsule.capsule_rect_global()
        area = screen.availableGeometry()
        rect = event_rect(
            (cap.x(), cap.y(), cap.width(), cap.height()),
            (area.x(), area.y(), area.width(), area.height()),
            self.capsule.edge(),
            (300, 38),
        )
        self._event.show_event(text, rect, kind=kind, duration_ms=duration_ms, light=self._light)

    def _on_event_clicked(self) -> None:
        cb, self._event_cb = self._event_cb, None
        if cb is not None:
            try:
                cb()
            except Exception:
                logger.exception("事件胶囊点击回调失败")

    def set_flyout_provider(self, provider) -> None:
        """P2b：控制器注入 snapshot / 动作回调。"""
        self._flyout_provider = provider

    def _on_content(self, pos: QPoint) -> None:
        self._open_flyout(TaskPluginFlyout, "content", pos)

    def _on_system(self, pos: QPoint) -> None:
        self._open_flyout(SystemFlyout, "system", pos)

    def _open_flyout(self, cls, end: str, pos: QPoint) -> None:
        if self.capsule is None or self._flyout_provider is None:
            self._popup_filtered(
                pos, ("任务列表", "插件") if end == "content" else ("设置", "退出")
            )
            return
        self._close_flyout()
        screen = self.capsule.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.menu.popup(pos)
            return
        flyout = cls(self._flyout_provider, light=self._light)
        area = screen.availableGeometry()
        cap = self.capsule.capsule_rect_global()
        rect = flyout_rect(
            (cap.x(), cap.y(), cap.width(), cap.height()),
            (area.x(), area.y(), area.width(), area.height()),
            self.capsule.edge(),
            end,
            (flyout.WIDTH, flyout.HEIGHT),
        )
        if self.capsule is not None:
            self.capsule.set_idle_enabled(False)
        flyout.closed.connect(self._on_flyout_closed)
        flyout.open_at(rect)
        self._flyout = flyout

    def _on_flyout_closed(self) -> None:
        self._flyout = None
        if self.capsule is not None:
            self.capsule.set_idle_enabled(True)

    def _close_flyout(self) -> None:
        if self._flyout is not None:
            try:
                self._flyout.close()
            except Exception:
                pass
            self._flyout = None
        if self.capsule is not None:
            self.capsule.set_idle_enabled(True)

    def _popup_filtered(self, pos: QPoint, needles: tuple[str, ...]) -> None:
        picked = [a for a in self.menu.actions() if a.text() and any(n in a.text() for n in needles)]
        if not picked or any(a.menu() is not None for a in picked):
            self.menu.popup(pos)
            return
        menu = QMenu()
        for act in picked:
            menu.addAction(act)
        menu.exec(pos)

    def _close_capsule(self) -> None:
        self._close_flyout()
        if self.capsule is not None:
            self.capsule.shutdown()
            self.capsule = None

    def apply_settings(self) -> None:
        """设置页保存后热应用：开关/边/位置/收纳/长按/全屏/多屏/主题。"""
        appr = self._appearance()
        if appr is None:
            return
        if not self._enabled():
            self._close_capsule()
            return
        self._idle_ms = max(2, int(getattr(appr, "win_tray_idle_sec", 8) or 8)) * 1000
        self._long_ms = max(150, int(getattr(appr, "win_tray_longpress_ms", 400) or 400))
        self._hide_fullscreen = bool(getattr(appr, "win_tray_hide_fullscreen", True))
        self._multi_monitor = str(getattr(appr, "win_tray_monitor", "primary") or "primary") == "all"
        edge = str(getattr(appr, "win_tray_edge", "bottom") or "bottom").lower()
        if edge not in ("top", "bottom", "left", "right"):
            edge = "bottom"
        try:
            ratio = float(getattr(appr, "win_tray_ratio", 0.75))
        except (TypeError, ValueError):
            ratio = 0.75
        ratio = max(0.0, min(1.0, ratio))
        self._light = self._system_is_light()
        if self.capsule is not None:
            self.capsule.set_idle_ms(self._idle_ms)
            self.capsule.set_longpress_ms(self._long_ms)
            self.capsule.set_multi_monitor(self._multi_monitor)
            self.capsule.set_light(self._light)
            self.capsule.set_dock(edge, ratio)
        if self._event is not None:
            self._event._light = self._light
            self._event.update()
        if self._flyout is not None:
            self._flyout.set_light(self._light)

    def shutdown(self):
        self._fs_timer.stop()
        self._close_flyout()
        if self._event is not None:
            self._event.close()
            self._event = None
        self._close_capsule()
        super().shutdown()
