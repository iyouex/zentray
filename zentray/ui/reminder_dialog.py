"""任务到点弹窗提醒。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from zentray.core.models import Task


class ReminderDialog(QDialog):
    """提醒弹窗：完成 / 稍后N分钟(默认30可改) / 跳转 / 忽略本次 / 废弃"""

    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self.task = task
        self.result_action = "dismiss"
        self.snooze_minutes = 30

        from zentray.ui.dialog_utils import apply_dialog_chrome, style_action_button

        self.setWindowTitle("⏰ 任务提醒")
        apply_dialog_chrome(self, width=560, height=240, stay_on_top=True)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        title = QLabel(f"「{task.title}」")
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        meta = QLabel(
            f"分类: {task.category}　优先级: {task.priority}"
        )
        meta.setStyleSheet("color: #666;")
        meta.setWordWrap(True)
        layout.addWidget(meta)

        if task.details:
            detail = QLabel(task.details[:300])
            detail.setWordWrap(True)
            layout.addWidget(detail)

        # 两行排布：上行主操作（完成/稍后/跳转），下行轻与破坏性操作
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        btn_done = style_action_button(QPushButton("✅ 完成"), min_w=96)
        btn_done.clicked.connect(lambda: self._finish("done"))
        btn_snooze = style_action_button(QPushButton("😴 稍后"), min_w=96)
        btn_snooze.clicked.connect(self._snooze)
        self.snooze_spin = QSpinBox()
        self.snooze_spin.setRange(1, 1440)
        self.snooze_spin.setValue(30)
        unit = QLabel("分钟")
        btn_jump = style_action_button(QPushButton("↗ 跳转"), min_w=88)
        btn_jump.clicked.connect(lambda: self._finish("jump"))
        for w in (btn_done, btn_snooze, self.snooze_spin, unit, btn_jump):
            row1.addWidget(w)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(10)
        btn_dismiss = style_action_button(QPushButton("忽略本次"), min_w=96)
        btn_dismiss.clicked.connect(lambda: self._finish("dismiss"))
        btn_abandon = style_action_button(QPushButton("🗑 废弃"), min_w=88)
        btn_abandon.clicked.connect(lambda: self._finish("abandon"))
        row2.addWidget(btn_dismiss)
        row2.addWidget(btn_abandon)
        row2.addStretch(1)
        layout.addLayout(row2)

    def _snooze(self) -> None:
        self.snooze_minutes = self.snooze_spin.value()
        self._finish("snooze")

    def _finish(self, action: str) -> None:
        self.result_action = action
        self.accept()


# 领域逻辑已移至 core/reminder.py，保留转发以兼容既有 import
from zentray.core.reminder import apply_reminder_action  # noqa: E402,F401
