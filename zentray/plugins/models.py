"""插件清单数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class PluginType(str, Enum):
    SCRIPT = "script"
    SERVICE = "service"


class TriggerType(str, Enum):
    DAILY = "daily"
    INTERVAL = "interval"
    CRON = "cron"
    EVENT = "event"


class TriggerEvent(str, Enum):
    TASK_DONE = "task_done"
    POMODORO_END = "pomodoro_end"
    STARTUP = "startup"


@dataclass(frozen=True)
class PluginTrigger:
    """manifest 声明的单个触发器（api_version: 2）。"""

    type: TriggerType
    time: Optional[str] = None       # daily: "HH:MM"
    minutes: Optional[int] = None    # interval: 每 N 分钟
    expr: Optional[str] = None       # cron: 5 字段表达式
    event: Optional[TriggerEvent] = None  # event: 事件名

    def describe(self) -> str:
        """人读描述（托盘/前端展示用）。"""
        if self.type == TriggerType.DAILY:
            return f"每日 {self.time}"
        if self.type == TriggerType.INTERVAL:
            return f"每 {self.minutes} 分钟"
        if self.type == TriggerType.CRON:
            return f"cron {self.expr}"
        labels = {
            TriggerEvent.TASK_DONE: "任务完成",
            TriggerEvent.POMODORO_END: "番茄结束",
            TriggerEvent.STARTUP: "启动时",
        }
        return f"事件: {labels.get(self.event, self.event)}"


@dataclass(frozen=True)
class PluginParam:
    """manifest 声明的命名入参（api_version: 2，仅 script；顺序即 argv 顺序）。"""

    name: str
    default: str = ""
    description: str = ""


@dataclass(frozen=True)
class PluginManifest:
    """已解析的 plugin.yaml。"""

    id: str
    name: str
    version: str
    type: PluginType
    api_version: int
    entry: str
    root: Path
    args: List[str] = field(default_factory=list)
    workdir: Optional[str] = None
    timeout_sec: int = 300
    env: Dict[str, str] = field(default_factory=dict)
    description: str = ""
    triggers: List[PluginTrigger] = field(default_factory=list)
    params: List[PluginParam] = field(default_factory=list)
    write_back: bool = False

    @property
    def entry_path(self) -> Path:
        return (self.root / self.entry).resolve()

    @property
    def work_path(self) -> Path:
        if self.workdir:
            return (self.root / self.workdir).resolve()
        return self.root.resolve()
