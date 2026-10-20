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


def normalize_deliveries(raw) -> List[dict]:
    """关键交付时间点归一：[{at, notify}]；非法/缺 at 丢弃，保留已触发标记。"""
    out: List[dict] = []
    for d in raw or []:
        if not isinstance(d, dict):
            continue
        at = str(d.get("at") or "").strip()
        try:
            datetime.datetime.fromisoformat(at)
        except (ValueError, TypeError):
            continue
        item = {"at": at, "notify": bool(d.get("notify", False))}
        if d.get("fired"):
            item["fired"] = True
        out.append(item)
    out.sort(key=lambda d: d["at"])
    return out


def due_delivery_ats(deliveries: List[dict], now: datetime.datetime) -> List[str]:
    """到点且需弹窗、尚未触发过的交付时间（60s 窗口，与提醒槽一致）。"""
    out: List[str] = []
    for d in deliveries or []:
        if not d.get("notify") or d.get("fired"):
            continue
        try:
            at = datetime.datetime.fromisoformat(str(d.get("at")))
        except (ValueError, TypeError):
            continue
        delta = (now - at).total_seconds()
        if 0 <= delta < 60:
            out.append(str(d.get("at")))
    return out


def normalize_due_time(raw) -> Optional[str]:
    """截止时分归一：HH:MM（时/分越界钳制）；空/格式非法 → None（按 23:59 语义）。"""
    if raw is None:
        return None
    s = str(raw).strip()
    parts = s.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return None
    h, m = min(23, int(parts[0])), min(59, int(parts[1]))
    return f"{h:02d}:{m:02d}"


def due_moment(task) -> Optional[datetime.datetime]:
    """截止时刻 = deadline 日期 + due_time（缺省 23:59）；无截止返回 None。"""
    dl = getattr(task, "deadline", None)
    if not dl:
        return None
    try:
        d = datetime.date.fromisoformat(str(dl)[:10])
    except (ValueError, TypeError):
        return None
    h, m = parse_hhmm(getattr(task, "due_time", None) or "23:59")
    return datetime.datetime.combine(d, datetime.time(h, m))


def due_popup_at(task, now: datetime.datetime) -> Optional[str]:
    """截止时刻弹窗：popup_at_due 且时刻入 60s 窗、未弹过 → 返回时刻 ISO；否则 None。

    返回值同时是去重键（写入 task.due_fired）；改截止/时分即换时刻重弹。
    """
    if not getattr(task, "popup_at_due", False):
        return None
    moment = due_moment(task)
    if moment is None:
        return None
    iso = moment.isoformat(timespec="minutes")
    if getattr(task, "due_fired", None) == iso:
        return None
    if 0 <= (now - moment).total_seconds() < 60:
        return iso
    return None


def is_task_overdue(task, now: datetime.datetime) -> bool:
    """逾期判定：截止日早于今天→逾期；同日有 due_time→到时刻即逾期（分钟级）。"""
    moment = due_moment(task)
    if moment is None:
        return False
    if moment.date() < now.date():
        return True
    if moment.date() > now.date():
        return False
    return bool(getattr(task, "due_time", None)) and now >= moment


def apply_reminder_action(
    task,
    action: str,
    fire_key: str,
    *,
    snooze_minutes: int = 10,
) -> TaskReminder:
    """根据弹窗操作返回更新后的 TaskReminder（自 ui/reminder_dialog.py 移入，纯领域操作）。

    无条件写 last_fired_key（防 60s 窗口内重触发）；仅 snooze 设 snooze_until。
    """
    rem = task.reminder or TaskReminder(enabled=True)
    rem.last_fired_key = fire_key
    if action == "snooze":
        until = datetime.datetime.now() + datetime.timedelta(minutes=snooze_minutes)
        rem.snooze_until = until.isoformat(timespec="seconds")
    else:
        rem.snooze_until = None
    return rem
