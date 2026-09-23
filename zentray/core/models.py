from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import datetime
import uuid

from zentray.core.reminder import TaskReminder


@dataclass
class Task:
    title: str
    category: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    details: str = ""
    priority: str = "medium"  # high, medium, low
    deadline: Optional[str] = None  # YYYY-MM-DD
    attachments: List[str] = field(default_factory=list)
    task_type: str = "one-time"  # one-time, periodic_instance
    template_id: Optional[str] = None
    overdue_penalty_date: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now().isoformat()
    )
    # v3.8 二级分类
    category_primary_id: Optional[str] = None
    category_secondary_id: Optional[str] = None
    # v3.8 弹窗提醒
    reminder: Optional[TaskReminder] = None
    # v3.9 逾期自动废弃（常从周期模板继承）
    auto_abandon_on_overdue: bool = False
    # 子任务清单（取代进度条）：[{id, title, status: active|done|abandoned}]
    subtasks: List[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.attachments is None:
            self.attachments = []
        if self.details is None:
            self.details = ""
        if self.priority is None:
            self.priority = "medium"
        if not self.title:
            self.title = "Untitled"
        if not self.category:
            self.category = "工作"
        if self.subtasks is None:
            self.subtasks = []
        if isinstance(self.reminder, dict):
            self.reminder = TaskReminder.from_dict(self.reminder)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.reminder is not None:
            d["reminder"] = (
                self.reminder.to_dict()
                if hasattr(self.reminder, "to_dict")
                else self.reminder
            )
        else:
            d["reminder"] = None
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        known = {k: v for k, v in data.items() if k in cls.__annotations__}
        if "reminder" in known and isinstance(known["reminder"], dict):
            known["reminder"] = TaskReminder.from_dict(known["reminder"])
        return cls(**known)


@dataclass
class PeriodicTemplate:
    base_title: str
    category: str
    periodicity: str  # daily, weekly, monthly
    template_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    details: str = ""
    priority: str = "medium"
    last_generated_period: Optional[str] = None
    created_at: str = field(
        default_factory=lambda: datetime.datetime.now().isoformat()
    )
    category_primary_id: Optional[str] = None
    category_secondary_id: Optional[str] = None
    reminder: Optional[TaskReminder] = None
    # v3.9 调度增强
    interval: int = 1  # 每 N 天/周/月
    # 实例截止日期规则：weekly 用 weekday 0=周一..6=周日；monthly 用 day_of_month
    deadline_weekday: Optional[int] = None
    deadline_day_of_month: Optional[int] = None
    auto_abandon_on_overdue: bool = False
    long_term: bool = True  # True=长期有效；False 时看 schedule_end_date
    schedule_end_date: Optional[str] = None  # YYYY-MM-DD 停止派发日
    # v3.10 暂停派发（恢复后为当前周期生成一次，不回填历史）
    paused: bool = False
    # 预设子任务：每次派发实例时复制（新 id、status=active）
    subtasks: List[dict] = field(default_factory=list)

    def __post_init__(self):
        if self.details is None:
            self.details = ""
        if self.priority is None:
            self.priority = "medium"
        if not self.base_title:
            self.base_title = "Untitled"
        if not self.category:
            self.category = "工作"
        if self.subtasks is None:
            self.subtasks = []
        if isinstance(self.reminder, dict):
            self.reminder = TaskReminder.from_dict(self.reminder)
        try:
            self.interval = max(1, int(self.interval or 1))
        except (TypeError, ValueError):
            self.interval = 1

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.reminder is not None:
            d["reminder"] = (
                self.reminder.to_dict()
                if hasattr(self.reminder, "to_dict")
                else self.reminder
            )
        else:
            d["reminder"] = None
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PeriodicTemplate":
        known = {k: v for k, v in data.items() if k in cls.__annotations__}
        if "reminder" in known and isinstance(known["reminder"], dict):
            known["reminder"] = TaskReminder.from_dict(known["reminder"])
        return cls(**known)
