# zentray/ui/progress_slider.py
"""
10% 步进的渐变进度拖拽条。

进度条填充与拖拽手柄合一：拖动手柄时，左侧按位置渐变填充。
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPen,
    QBrush,
    QFont,
    QPainterPath,
)
from PySide6.QtWidgets import QWidget, QSizePolicy


def snap_progress_10(value: int | float | None) -> int:
    """将进度对齐到 0/10/…/100。"""
    try:
        v = int(value if value is not None else 0)
    except (TypeError, ValueError):
        v = 0
    v = max(0, min(100, v))
    snapped = int(round(v / 10.0) * 10)
    return max(0, min(100, snapped))


class GradientProgressSlider(QWidget):
    """
    可拖拽的渐变进度条（仅 10% 步进）。

    - 轨道：深色底
    - 已完成段：红→橙→绿水平渐变，宽度随 value 变化
    - 手柄：圆形按钮叠在填充末端
    """

    valueChanged = Signal(int)

    def __init__(self, parent=None, value: int = 0):
        super().__init__(parent)
        self._value = snap_progress_10(value)
        self._dragging = False
        self.setMinimumHeight(40)
        self.setMaximumHeight(48)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip("拖动调整进度（每格 10%）")

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:
        v = snap_progress_10(value)
        if v != self._value:
            self._value = v
            self.update()
            self.valueChanged.emit(self._value)

    # —— 几何 ——
    def _track_rect(self) -> QRectF:
        m = 10.0
        h = 14.0
        y = (self.height() - h) / 2.0
        return QRectF(m, y, max(1.0, self.width() - 2 * m), h)

    def _value_from_x(self, x: float) -> int:
        tr = self._track_rect()
        if tr.width() <= 0:
            return 0
        ratio = (x - tr.left()) / tr.width()
        ratio = max(0.0, min(1.0, ratio))
        return snap_progress_10(ratio * 100)

    def _handle_center(self) -> QPointF:
        tr = self._track_rect()
        x = tr.left() + tr.width() * (self._value / 100.0)
        return QPointF(x, tr.center().y())

    # —— 绘制 ——
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        tr = self._track_rect()
        radius = tr.height() / 2.0

        # 轨道底
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2a2a2e"))
        p.drawRoundedRect(tr, radius, radius)

        # 10% 刻度（淡线）
        p.setPen(QPen(QColor(255, 255, 255, 28), 1))
        for i in range(1, 10):
            x = tr.left() + tr.width() * (i / 10.0)
            p.drawLine(QPointF(x, tr.top() + 2), QPointF(x, tr.bottom() - 2))

        # 填充段 + 渐变
        if self._value > 0:
            fill_w = tr.width() * (self._value / 100.0)
            fill = QRectF(tr.left(), tr.top(), max(fill_w, radius * 2), tr.height())
            if fill.right() > tr.right():
                fill.setRight(tr.right())

            grad = QLinearGradient(tr.left(), 0, tr.right(), 0)
            # 整条轨道坐标系上的渐变，使拖到哪一段对应哪段色相
            grad.setColorAt(0.0, QColor("#ef4444"))   # 红
            grad.setColorAt(0.35, QColor("#f59e0b"))  # 橙
            grad.setColorAt(0.7, QColor("#eab308"))   # 黄
            grad.setColorAt(1.0, QColor("#22c55e"))   # 绿

            path = QPainterPath()
            path.addRoundedRect(fill, radius, radius)
            p.fillPath(path, QBrush(grad))

            # 内高光
            hi = QRectF(fill.left() + 2, fill.top() + 2, fill.width() - 4, fill.height() * 0.35)
            if hi.width() > 4:
                p.setBrush(QColor(255, 255, 255, 45))
                p.drawRoundedRect(hi, 4, 4)

        # 手柄
        c = self._handle_center()
        hr = 11.0
        # 外圈阴影
        p.setBrush(QColor(0, 0, 0, 60))
        p.setPen(Qt.NoPen)
        p.drawEllipse(c + QPointF(0.5, 1.0), hr, hr)
        # 本体
        p.setBrush(QColor("#f8fafc"))
        p.setPen(QPen(QColor("#0f172a"), 1.5))
        p.drawEllipse(c, hr, hr)
        # 内点（当前色相）
        t = self._value / 100.0
        if t < 0.35:
            inner = QColor("#ef4444")
        elif t < 0.7:
            inner = QColor("#f59e0b")
        else:
            inner = QColor("#22c55e")
        p.setBrush(inner)
        p.setPen(Qt.NoPen)
        p.drawEllipse(c, 4.5, 4.5)

        # 百分比文字（轨道右侧上方区域不挤时画在手柄旁）
        p.setPen(QColor("#e2e8f0"))
        font = QFont(self.font())
        font.setPointSize(max(9, font.pointSize()))
        font.setBold(True)
        p.setFont(font)
        label = f"{self._value}%"
        # 放在控件右侧内侧
        p.drawText(
            QRectF(tr.right() - 42, tr.top() - 16, 42, 14),
            Qt.AlignRight | Qt.AlignVCenter,
            label,
        )

    # —— 交互 ——
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self.setValue(self._value_from_x(event.position().x()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and (event.buttons() & Qt.LeftButton):
            self.setValue(self._value_from_x(event.position().x()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Left, Qt.Key_Down, Qt.Key_Minus):
            self.setValue(self._value - 10)
            event.accept()
            return
        if event.key() in (Qt.Key_Right, Qt.Key_Up, Qt.Key_Plus):
            self.setValue(self._value + 10)
            event.accept()
            return
        if event.key() == Qt.Key_Home:
            self.setValue(0)
            event.accept()
            return
        if event.key() == Qt.Key_End:
            self.setValue(100)
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self.setValue(self._value + 10)
        elif delta < 0:
            self.setValue(self._value - 10)
        event.accept()
