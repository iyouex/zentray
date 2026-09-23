"""任务弹窗提醒扫描线程。"""
from __future__ import annotations

import datetime
import logging
import time
from typing import Optional

from PySide6.QtCore import QThread, Signal

from zentray.core.models import Task
from zentray.core.reminder import due_reminder_keys
from zentray.core.repository import TaskRepository

logger = logging.getLogger(__name__)


class ReminderWorker(QThread):
    """
    每 30s 扫描一次到期提醒。
    命中时一轮聚合成 reminder_due([(task, fire_key), ...]) 单次发出，
    由主线程弹聚合窗（多提醒一窗卡片式）。
    """

    reminder_due = Signal(list)  # [(Task, fire_key), ...]

    def __init__(self, task_repo: TaskRepository, parent=None):
        super().__init__(parent)
        self.task_repo = task_repo
        self.is_running = True
        self._pending_ids: set[str] = set()  # 弹窗排队中，避免重复 emit

    def run(self):
        while self.is_running:
            try:
                self._scan()
            except Exception:
                logger.exception("Reminder scan error")
            for _ in range(30):
                if not self.is_running:
                    break
                time.sleep(1)

    def _scan(self):
        now = datetime.datetime.now()
        tasks = self.task_repo.find_all()
        batch = []
        for task in tasks:
            rem = getattr(task, "reminder", None)
            if not rem or not rem.enabled:
                continue
            if task.id in self._pending_ids:
                continue
            # 周期实例沿用 task_type；periodicity 仅在模板上，实例无此字段 → 按 daily/one-time
            periodicity = None
            if task.task_type == "periodic_instance":
                periodicity = "daily"  # 实例每天可提醒；多 slot 靠 weekday/dom 约束
            keys = due_reminder_keys(rem, now, periodicity=periodicity)
            if keys:
                self._pending_ids.add(task.id)
                batch.append((task, keys[0]))
        if batch:
            self.reminder_due.emit(batch)

    def clear_pending(self, task_id: str) -> None:
        self._pending_ids.discard(task_id)

    def clear_pending_batch(self, task_ids) -> None:
        for tid in task_ids:
            self._pending_ids.discard(tid)

    def stop(self):
        self.is_running = False
        self.wait(3000)
