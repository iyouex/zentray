"""任务到点弹窗提醒。"""
from __future__ import annotations

import datetime

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from zentray.core.models import Task
from zentray.core.reminder import TaskReminder
class ReminderDialog(QDialog):
    """提醒弹窗"""

    def __init__(self, task: Task, parent=None):
        super().__init__(parent)
        self.task = task
        self.result_action = "dismiss"
        self.snooze_minutes = 10

        from zentray.ui.dialog_utils import apply_dialog_chrome, style_action_button

        self.setWindowTitle("⏰ 任务提醒")
        apply_dialog_chrome(self, width=560, height=220, stay_on_top=True)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        title = QLabel(f"「{task.title}」")
        title.setWordWrap(True)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        meta = QLabel(
            f"分类: {task.category}　优先级: {task.priority}　"
            f"进度: {getattr(task, 'progress', 0)}%"
        )
        meta.setStyleSheet("color: #666;")
        meta.setWordWrap(True)
        layout.addWidget(meta)

        if task.details:
            detail = QLabel(task.details[:300])
            detail.setWordWrap(True)
            layout.addWidget(detail)

        hint = QLabel("到点提醒 — 请选择操作：")
        hint.setStyleSheet("margin-top: 4px;")
        layout.addWidget(hint)

        # 单行横排四个操作，保证文字完整
        row = QHBoxLayout()
        row.setSpacing(10)
        btn_update = style_action_button(QPushButton("📊 更新状态"), min_w=110)
        btn_update.clicked.connect(lambda: self._finish("update"))
        btn_done = style_action_button(QPushButton("✅ 完成"), min_w=88)
        btn_done.clicked.connect(lambda: self._finish("done"))
        btn_snooze = style_action_button(QPushButton("😴 忽略 10 分钟"), min_w=130)
        btn_snooze.clicked.connect(lambda: self._finish("snooze"))
        btn_dismiss = style_action_button(QPushButton("关闭本次"), min_w=96)
        btn_dismiss.clicked.connect(lambda: self._finish("dismiss"))
        row.addWidget(btn_update)
        row.addWidget(btn_done)
        row.addWidget(btn_snooze)
        row.addWidget(btn_dismiss)
        layout.addLayout(row)

    def _finish(self, action: str) -> None:
        self.result_action = action
        self.accept()


def apply_reminder_action(
    task: Task,
    action: str,
    fire_key: str,
    *,
    snooze_minutes: int = 10,
) -> TaskReminder:
    """根据弹窗操作返回更新后的 TaskReminder。"""
    rem = task.reminder or TaskReminder(enabled=True)
    rem.last_fired_key = fire_key
    if action == "snooze":
        until = datetime.datetime.now() + datetime.timedelta(minutes=snooze_minutes)
        rem.snooze_until = until.isoformat(timespec="seconds")
    else:
        rem.snooze_until = None
    return rem
