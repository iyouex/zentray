"""周期任务调度纯函数：周期键、是否应派发、实例截止日期、暂停/跳过水位。"""
from __future__ import annotations

import calendar
import datetime
import uuid
from typing import Optional, Tuple

from zentray.core.models import PeriodicTemplate, Task


def _bucket_index(periodicity: str, today: datetime.date, n: int) -> int:
    """周期桶序号。interval=N 表示每 N 天/周/月合并为一桶。"""
    if periodicity == "weekly":
        iso_year, iso_week, _ = today.isocalendar()
        # 连续周序号
        return (iso_year * 53 + iso_week) // n
    if periodicity == "monthly":
        return (today.year * 12 + (today.month - 1)) // n
    # daily（默认）
    return today.toordinal() // n


def _key_from_bucket(periodicity: str, bucket: int, n: int) -> str:
    if periodicity == "weekly":
        return f"W{bucket}"
    if periodicity == "monthly":
        y, m0 = divmod(bucket * n, 12)
        return f"M{y:04d}{(m0 + 1):02d}x{n}"
    return f"D{bucket}"


def period_key(
    periodicity: str,
    today: datetime.date,
    interval: int = 1,
) -> str:
    """
    当前「周期桶」标识。interval=N 表示每 N 天/周/月合并为一桶。
    """
    n = max(1, int(interval or 1))
    return _key_from_bucket(periodicity, _bucket_index(periodicity, today, n), n)


def parse_period_key(key: Optional[str]) -> Optional[Tuple[str, int]]:
    """
    解析周期键为 (periodicity, 桶序号)；无法解析返回 None。
    monthly 键携带 x{interval} 后缀，需还原到统一桶序号。
    """
    if not key:
        return None
    s = str(key).strip()
    if s.startswith("D") and s[1:].isdigit():
        return ("daily", int(s[1:]))
    if s.startswith("W") and s[1:].isdigit():
        return ("weekly", int(s[1:]))
    if s.startswith("M"):
        body, sep, tail = s[1:].partition("x")
        if sep and len(body) == 6 and body.isdigit() and tail.isdigit():
            y, m = int(body[:4]), int(body[4:])
            n = max(1, int(tail))
            return ("monthly", (y * 12 + (m - 1)) // n)
    return None


def period_display_prefix(
    periodicity: str,
    today: datetime.date,
    interval: int = 1,
) -> str:
    """用于任务标题的可读前缀。"""
    n = max(1, int(interval or 1))
    if periodicity == "weekly":
        iso_year, iso_week, _ = today.isocalendar()
        base = f"{str(iso_year)[2:]}第{iso_week}周"
        return f"{base}/每{n}周" if n > 1 else base
    if periodicity == "monthly":
        base = today.strftime("%y%m")
        return f"{base}/每{n}月" if n > 1 else base
    base = today.strftime("%y%m%d")
    return f"{base}/每{n}天" if n > 1 else base


def is_schedule_active(tmpl: "PeriodicTemplate", today: datetime.date) -> bool:
    """模板是否仍在调度有效期内。"""
    if getattr(tmpl, "long_term", True):
        return True
    end = getattr(tmpl, "schedule_end_date", None) or ""
    end = str(end).strip()
    if not end:
        return True
    try:
        end_d = datetime.date.fromisoformat(end)
    except ValueError:
        return True
    return today <= end_d


def should_spawn(tmpl: "PeriodicTemplate", today: datetime.date) -> bool:
    if getattr(tmpl, "paused", False):
        return False
    if not is_schedule_active(tmpl, today):
        return False
    periodicity = tmpl.periodicity or "daily"
    n = max(1, int(getattr(tmpl, "interval", 1) or 1))
    cur = _bucket_index(periodicity, today, n)
    wb = parse_period_key(tmpl.last_generated_period)
    # 无法比较（从未派发/改过 periodicity/键损坏）→ 与历史 != 行为一致，派发
    if wb is None or wb[0] != periodicity:
        return True
    # 有序水位：仅当水位严格落后当前桶才派发（领先=跳过中，相等=本桶已派）
    return wb[1] < cur


def skip_watermark_key(
    tmpl: "PeriodicTemplate", today: datetime.date, count: int
) -> str:
    """
    「跳过接下来 count 个未派发周期」应写回的水位键。
    当前桶已派发（水位≥当前桶，含连续跳过）→ 从水位起再压 count 桶；
    当前桶未派发（水位落后/无）→ 含当前桶共 count 桶。
    """
    count = max(1, int(count))
    periodicity = tmpl.periodicity or "daily"
    n = max(1, int(getattr(tmpl, "interval", 1) or 1))
    cur = _bucket_index(periodicity, today, n)
    wb = parse_period_key(tmpl.last_generated_period)
    if wb and wb[0] == periodicity and wb[1] >= cur:
        return _key_from_bucket(periodicity, wb[1] + count, n)
    return _key_from_bucket(periodicity, cur + count - 1, n)


def next_spawn_date(
    tmpl: "PeriodicTemplate", today: datetime.date
) -> Optional[datetime.date]:
    """今天或之后的首个派发日；暂停/过期返回 None。"""
    if getattr(tmpl, "paused", False) or not is_schedule_active(tmpl, today):
        return None
    # ponytail: 日步进循环，interval>13 月时再改桶算术
    for i in range(400):
        d = today + datetime.timedelta(days=i)
        if should_spawn(tmpl, d):
            return d
    return None


def compute_instance_deadline(
    tmpl: "PeriodicTemplate",
    today: datetime.date,
) -> str:
    """
    按模板规则计算派发实例的截止日期 YYYY-MM-DD；无规则返回空串。
    """
    periodicity = tmpl.periodicity or "daily"
    if periodicity == "weekly":
        wd = getattr(tmpl, "deadline_weekday", None)
        if wd is None:
            return ""
        wd = int(wd) % 7
        # 本周目标 weekday；若已过则仍用本周该日（可能已逾期，交给 overdue 逻辑）
        delta = (wd - today.weekday()) % 7
        target = today + datetime.timedelta(days=delta)
        return target.isoformat()
    if periodicity == "monthly":
        dom = getattr(tmpl, "deadline_day_of_month", None)
        if dom is None:
            return ""
        dom = max(1, min(31, int(dom)))
        last = calendar.monthrange(today.year, today.month)[1]
        day = min(dom, last)
        return datetime.date(today.year, today.month, day).isoformat()
    # daily：默认当天
    return today.isoformat()


def spawn_key_after_create(tmpl: "PeriodicTemplate", today: datetime.date) -> str:
    return period_key(
        tmpl.periodicity,
        today,
        getattr(tmpl, "interval", 1) or 1,
    )


def build_due_instance(tmpl: "PeriodicTemplate", today: datetime.date) -> Optional[Task]:
    """
    到期则构造实例任务并推进模板水位；否则返回 None。纯构造，不落盘。
    task_service 与 watcher 的派发路径统一经此，暂停/跳过判断天然双路径生效。
    """
    if not should_spawn(tmpl, today):
        return None
    prefix = period_display_prefix(
        tmpl.periodicity, today, getattr(tmpl, "interval", 1) or 1
    )
    new_task = Task(
        id=str(uuid.uuid4()),
        title=f"【{prefix}】{tmpl.base_title}",
        category=tmpl.category,
        details=tmpl.details,
        priority=tmpl.priority,
        deadline=compute_instance_deadline(tmpl, today) or "",
        task_type="periodic_instance",
        template_id=tmpl.template_id,
        category_primary_id=getattr(tmpl, "category_primary_id", None),
        category_secondary_id=getattr(tmpl, "category_secondary_id", None),
        reminder=getattr(tmpl, "reminder", None),
        auto_abandon_on_overdue=bool(
            getattr(tmpl, "auto_abandon_on_overdue", False)
        ),
        # 预设子任务逐项新 dict 新 id（watcher 常驻持有模板对象，禁共享引用）
        subtasks=[
            {"id": str(uuid.uuid4()), "title": s["title"], "status": "active"}
            for s in (getattr(tmpl, "subtasks", None) or [])
            if isinstance(s, dict) and s.get("title")
        ],
    )
    tmpl.last_generated_period = spawn_key_after_create(tmpl, today)
    return new_task
