import datetime
import random
from typing import Callable, List, Optional

from zentray.core.models import Task


def task_reminder_gated(task, now: datetime.datetime, cats) -> bool:
    """
    提醒门控（轮播与弹窗共用，2026-10-19）：
    1) 开始提醒时间未到（remind_start，空=即时）；
    2) 分类提醒时间窗外（如工作 9:00-18:00，支持跨夜窗）；
    3) 跳过公休日（任务级，创建未显式给值时由服务层取分类预设）。
    """
    from zentray.core.categories import resolve_primary_secondary
    from zentray.core.holidays import is_cn_holiday, is_weekend
    from zentray.core.reminder import parse_hhmm

    rs = getattr(task, "remind_start", None)
    if rs:
        try:
            if now < datetime.datetime.fromisoformat(str(rs)):
                return True
        except (ValueError, TypeError):
            pass
    primary, _ = resolve_primary_secondary(
        cats,
        primary_id=getattr(task, "category_primary_id", None),
        category_name=task.category,
    )
    if primary is not None:
        if primary.remind_window_enabled:
            sh, sm = parse_hhmm(primary.remind_window_start or "09:00")
            eh, em = parse_hhmm(primary.remind_window_end or "18:00")
            start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
            end = now.replace(hour=eh, minute=em, second=0, microsecond=0)
            inside = start <= now < end if start <= end else (now >= start or now < end)
            if not inside:
                return True
        if primary.skip_holidays or getattr(task, "skip_holidays", False):
            if is_weekend(now.date()) or is_cn_holiday(now.date()):
                return True
    elif getattr(task, "skip_holidays", False):
        if is_weekend(now.date()) or is_cn_holiday(now.date()):
            return True
    return False


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
        # 提醒门控（task, now) -> bool：True=门外（不轮播）。None=不门控
        self.gate: Optional[Callable[[Task, datetime.datetime], bool]] = None

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

    def _passes_gate(self, task: Task) -> bool:
        if self.gate is None:
            return True
        try:
            return not self.gate(task, datetime.datetime.now())
        except Exception:
            return True  # 门控异常不吞任务

    def get_next(self) -> Optional[Task]:
        """推进轮播并返回下一个任务（门外任务跳过）"""
        if self.is_paused:
            return None

        if self.overdue_enabled and self._overdue_queue and not self._overdue_phase_done:
            task: Optional[Task] = None
            while self._overdue_cursor < len(self._overdue_queue):
                cand = self._overdue_queue[self._overdue_cursor]
                self._overdue_cursor += 1
                if self._passes_gate(cand):
                    task = cand
                    break
            if self._overdue_cursor >= len(self._overdue_queue):
                self._overdue_phase_done = True
                self._overdue_cursor = 0
            if task is not None:
                self._current = task
                return task

        if self._active_queue:
            n = len(self._active_queue)
            # 多任务时尽量不连续展示同一条；2n 窗口兼顾跳过重复与门外任务
            for _ in range(2 * n):
                cand = self._active_queue[self._active_cursor % n]
                self._active_cursor += 1
                if not self._passes_gate(cand):
                    continue
                if (
                    self._current is None
                    or n == 1
                    or cand.id != self._current.id
                ):
                    self._current = cand
                    return cand
            # 兜底：首个门内任务（含加权队列全同 id 场景）；全在门外则轮播空转
            for cand in self._active_queue:
                if self._passes_gate(cand):
                    self._current = cand
                    return cand

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
