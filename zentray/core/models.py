from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional
import datetime
import uuid

from zentray.core.reminder import ReminderSlot, TaskReminder


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
    # 关联插件 id（运行入口见任务列表/编辑页）
    plugin_id: Optional[str] = None
    # 飞书同步回写的远端对象 id（ZenTray → 飞书单向；空=尚未推送）
    feishu_event_id: Optional[str] = None
    feishu_task_id: Optional[str] = None
    # 提醒重设计（2026-10-19）：开始提醒时间（ISO datetime，空=创建后即时）；
    # 跳过公休日（周末+法定节假日，创建时未显式给值则取分类预设）
    # 时间重设计（2026-10-20）：截止时分 due_time（HH:MM，空=按 23:59 语义）；
    # popup_at_due=截止时刻弹窗一次；deliveries 语义改「额外弹窗时间」（不再推导截止）；
    # due_fired 记录已弹过的截止时刻，改截止/时分即重置再弹
    remind_start: Optional[str] = None
    deliveries: List[dict] = field(default_factory=list)
    skip_holidays: bool = False
    due_time: Optional[str] = None
    popup_at_due: bool = False
    due_fired: Optional[str] = None

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
        if self.deliveries is None:
            self.deliveries = []
        if isinstance(self.plugin_id, str) and not self.plugin_id.strip():
            self.plugin_id = None
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
    # 关联插件 id（派发实例时继承）
    plugin_id: Optional[str] = None
    # 系统日历未来日程投影：开关 + 范围（count=未来几次 1-60 / days=未来几天 7-365）
    calendar_enabled: bool = False
    calendar_horizon_mode: str = "count"
    calendar_horizon_value: int = 4
    # 提醒重设计（2026-10-19）：周/月模板的开始提醒点（周几/几号+时分，可多个）；
    # 派发实例时解析为本周期内首个到来的 ISO datetime。跳过公休日随实例继承。
    # 时间重设计（2026-10-20）：日模板开始点=仅时分的单 slot；截止时分/截止弹窗随实例继承
    remind_start_slots: list = field(default_factory=list)
    skip_holidays: bool = False
    due_time: Optional[str] = None
    popup_at_due: bool = False

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
        if isinstance(self.plugin_id, str) and not self.plugin_id.strip():
            self.plugin_id = None
        if isinstance(self.reminder, dict):
            self.reminder = TaskReminder.from_dict(self.reminder)
        if self.remind_start_slots is None:
            self.remind_start_slots = []
        self.remind_start_slots = [
            s if isinstance(s, ReminderSlot) else ReminderSlot.from_dict(s)
            for s in self.remind_start_slots
            if isinstance(s, (dict, ReminderSlot))
        ]
        try:
            self.interval = max(1, int(self.interval or 1))
        except (TypeError, ValueError):
            self.interval = 1
        if self.calendar_horizon_mode not in ("count", "days"):
            self.calendar_horizon_mode = "count"
        try:
            self.calendar_horizon_value = max(1, int(self.calendar_horizon_value or 4))
        except (TypeError, ValueError):
            self.calendar_horizon_value = 4

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
        if "remind_start_slots" in known:
            known["remind_start_slots"] = [
                s if isinstance(s, ReminderSlot) else ReminderSlot.from_dict(s)
                for s in (known["remind_start_slots"] or [])
                if isinstance(s, (dict, ReminderSlot))
            ]
        return cls(**known)
