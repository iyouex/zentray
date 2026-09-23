import datetime
import random
from typing import List, Optional

from zentray.core.models import Task


class Scheduler:
    """
    核心轮播调度引擎。

    两阶段轮播：
      1. 逾期轮播（如果启用）：先轮播完所有逾期任务一次
      2. 活跃任务轮播：按配置模式（随机/优先级无限轮播）

    逾期前缀仅用于展示（format_display_title），绝不修改 Task 本体。
    """

    def __init__(self):
        self._overdue_queue: List[Task] = []
        self._active_queue: List[Task] = []
        self._overdue_cursor: int = 0
        self._active_cursor: int = 0
        self.is_paused: bool = False

        self.mode: str = "random"
        self.overdue_enabled: bool = True
        self.overdue_prefix: str = "【已逾期】"

        self._current: Optional[Task] = None
        self._overdue_phase_done: bool = False

    def build_queue(self, tasks: List[Task]) -> None:
        today = datetime.date.today()
        overdue: List[Task] = []
        active: List[Task] = []

        for t in tasks:
            if t.deadline and self._is_overdue(t.deadline, today):
                overdue.append(t)
            else:
                active.append(t)

        self._build_overdue_queue(overdue)
        self._build_active_queue(active)

        self._overdue_phase_done = False
        # 保留 focus：若当前任务仍在新队列中则继续；否则清空
        if self._current is not None:
            ids = {t.id for t in self._overdue_queue + self._active_queue}
            if self._current.id not in ids:
                self._current = None

    def configure(self, mode: str, overdue_enabled: bool, overdue_prefix: str) -> None:
        self.mode = mode
        self.overdue_enabled = overdue_enabled
        self.overdue_prefix = overdue_prefix

    def _build_overdue_queue(self, tasks: List[Task]) -> None:
        self._overdue_queue.clear()
        self._overdue_cursor = 0
        if not tasks:
            return
        priority_order = {"high": 0, "medium": 1, "low": 2}
        self._overdue_queue = sorted(
            tasks, key=lambda t: priority_order.get(t.priority, 1)
        )

    def _build_active_queue(self, tasks: List[Task]) -> None:
        self._active_queue.clear()
        self._active_cursor = 0
        if not tasks:
            return

        if self.mode == "priority_high_first":
            order = {"high": 0, "medium": 1, "low": 2}
            self._active_queue = sorted(tasks, key=lambda t: order.get(t.priority, 1))

        elif self.mode == "priority_low_first":
            order = {"low": 0, "medium": 1, "high": 2}
            self._active_queue = sorted(tasks, key=lambda t: order.get(t.priority, 1))

        else:  # random — 优先级加权穿插
            temp = []
            for t in tasks:
                weight = 2 if t.priority == "high" else 1
                for _ in range(weight):
                    temp.append(t)
            high_tasks = [t for t in temp if t.priority == "high"]
            other_tasks = [t for t in temp if t.priority != "high"]
            random.shuffle(high_tasks)
            random.shuffle(other_tasks)
            while high_tasks or other_tasks:
                if high_tasks:
                    self._active_queue.append(high_tasks.pop(0))
                if other_tasks:
                    self._active_queue.append(other_tasks.pop(0))

    def get_next(self) -> Optional[Task]:
        """推进轮播并返回下一个任务"""
        if self.is_paused:
            return None

        if self.overdue_enabled and self._overdue_queue and not self._overdue_phase_done:
            task = self._overdue_queue[self._overdue_cursor]
            self._overdue_cursor += 1
            if self._overdue_cursor >= len(self._overdue_queue):
                self._overdue_phase_done = True
                self._overdue_cursor = 0
            self._current = task
            return task

        if self._active_queue:
            n = len(self._active_queue)
            # 多任务时尽量不连续展示同一条（随机加权队列可能相邻重复）
            for _ in range(n):
                task = self._active_queue[self._active_cursor % n]
                self._active_cursor += 1
                if (
                    self._current is None
                    or n == 1
                    or task.id != self._current.id
                ):
                    self._current = task
                    return task
            # 全部相同 id 时退回当前项
            task = self._active_queue[self._active_cursor % n]
            self._active_cursor += 1
            self._current = task
            return task

        self._current = None
        return None

    def get_current(self) -> Optional[Task]:
        """获取当前正在展示的任务（原始 Task，无展示前缀）。"""
        if self.is_paused:
            return None
        return self._current

    def focus(self, task: Task) -> None:
        """将焦点钉到指定任务，不缩减轮播队列。"""
        self._current = task

    @staticmethod
    def _is_overdue(deadline_str: str, today: datetime.date) -> bool:
        try:
            dl = datetime.date.fromisoformat(deadline_str)
            return dl < today
        except (ValueError, TypeError):
            return False
