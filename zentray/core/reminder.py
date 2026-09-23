"""任务弹窗提醒领域逻辑（纯函数）。"""
from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class ReminderSlot:
    """单条提醒计划。weekly 用 weekday；monthly 用 day_of_month。"""

    time_of_day: str = "17:00"  # HH:mm
    weekday: Optional[int] = None  # 0=周一 .. 6=周日
    day_of_month: Optional[int] = None  # 1..31

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "ReminderSlot":
        if not data:
            return cls()
        return cls(
            time_of_day=str(data.get("time_of_day") or "17:00"),
            weekday=data.get("weekday"),
            day_of_month=data.get("day_of_month"),
        )


@dataclass
class TaskReminder:
    enabled: bool = False
    time_of_day: str = "17:00"
    slots: List[ReminderSlot] = field(default_factory=list)
    last_fired_key: Optional[str] = None
    snooze_until: Optional[str] = None  # ISO datetime

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "time_of_day": self.time_of_day,
            "slots": [s.to_dict() for s in self.slots],
            "last_fired_key": self.last_fired_key,
            "snooze_until": self.snooze_until,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "TaskReminder":
        if not data:
            return cls()
        slots_raw = data.get("slots") or []
        slots = [
            ReminderSlot.from_dict(s) for s in slots_raw if isinstance(s, dict)
        ]
        return cls(
            enabled=bool(data.get("enabled", False)),
            time_of_day=str(data.get("time_of_day") or "17:00"),
            slots=slots,
            last_fired_key=data.get("last_fired_key"),
            snooze_until=data.get("snooze_until"),
        )

    def effective_slots(self) -> List[ReminderSlot]:
        if self.slots:
            return self.slots
        return [ReminderSlot(time_of_day=self.time_of_day or "17:00")]


def parse_hhmm(value: str) -> tuple[int, int]:
    try:
        parts = (value or "17:00").strip().split(":")
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
        return max(0, min(23, h)), max(0, min(59, m))
    except (ValueError, IndexError, TypeError):
        return 17, 0


def fire_key(day: datetime.date, time_of_day: str) -> str:
    h, m = parse_hhmm(time_of_day)
    return f"{day.isoformat()}|{h:02d}:{m:02d}"


def _slot_matches_today(
    slot: ReminderSlot,
    today: datetime.date,
    *,
    periodicity: Optional[str],
) -> bool:
    """判断 slot 是否适用于「今天」这一日历日。"""
    # one-time / daily / 无周期：每天可匹配 time
    if not periodicity or periodicity == "daily" or periodicity == "one-time":
        if slot.weekday is not None or slot.day_of_month is not None:
            # 显式约束时仍校验
            if slot.weekday is not None and today.weekday() != slot.weekday:
                return False
            if slot.day_of_month is not None and today.day != slot.day_of_month:
                return False
        return True

    if periodicity == "weekly":
        if slot.weekday is None:
            return True  # 未指定周几则每天（回退）
        return today.weekday() == int(slot.weekday)

    if periodicity == "monthly":
        if slot.day_of_month is None:
            return True
        return today.day == int(slot.day_of_month)

    return True


def is_snoozed(reminder: TaskReminder, now: datetime.datetime) -> bool:
    if not reminder.snooze_until:
        return False
    try:
        until = datetime.datetime.fromisoformat(reminder.snooze_until)
        return now < until
    except (ValueError, TypeError):
        return False


def due_reminder_keys(
    reminder: TaskReminder,
    now: datetime.datetime,
    *,
    periodicity: Optional[str] = None,
    window_seconds: int = 60,
) -> List[str]:
    """
    返回当前时刻应触发的 fire_key 列表（通常 0 或 1 个）。

    在 time_of_day 对应分钟的 [0, window_seconds) 内视为到期。
    """
    if not reminder or not reminder.enabled:
        return []
    if is_snoozed(reminder, now):
        return []

    today = now.date()
    keys: List[str] = []
    for slot in reminder.effective_slots():
        if not _slot_matches_today(slot, today, periodicity=periodicity):
            continue
        h, m = parse_hhmm(slot.time_of_day)
        target = datetime.datetime.combine(today, datetime.time(h, m))
        delta = (now - target).total_seconds()
        if 0 <= delta < window_seconds:
            key = fire_key(today, slot.time_of_day)
            if key != reminder.last_fired_key:
                keys.append(key)
    return keys
