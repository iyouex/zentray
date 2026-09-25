"""每日计划 / 复盘调度判定与状态持久化。

规则（api_version 行为约定）：
1. 每个日历日每个 job 最多成功触发一次（跳过周末/节假日也记为已处理）。
2. 到达或超过设定的时:分后即可触发（含应用晚启动的补跑），不再要求 hour 全等。
3. 若用户修改了该 job 的触发时刻，清除该 job 的「今日已跑」标记，以便按新时间再跑。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from zentray.config import DATA_DIR

logger = logging.getLogger(__name__)

STATE_FILE = DATA_DIR / "ai_schedule_state.json"


@dataclass
class JobScheduleState:
    last_plan_date: Optional[str] = None
    last_review_date: Optional[str] = None
    plan_hm: Optional[str] = None  # "H:M" 上次已知触发点
    review_hm: Optional[str] = None
    # 自动备份（每 N 天粒度，不复用每日 last_date == today 判定）
    last_backup_date: Optional[str] = None
    last_backup_at: Optional[str] = None  # ISO 时间戳，供设置页展示

    def to_dict(self) -> dict:
        return {
            "last_plan_date": self.last_plan_date,
            "last_review_date": self.last_review_date,
            "plan_hm": self.plan_hm,
            "review_hm": self.review_hm,
            "last_backup_date": self.last_backup_date,
            "last_backup_at": self.last_backup_at,
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "JobScheduleState":
        data = data or {}
        return cls(
            last_plan_date=data.get("last_plan_date") or None,
            last_review_date=data.get("last_review_date") or None,
            plan_hm=data.get("plan_hm") or None,
            review_hm=data.get("review_hm") or None,
            last_backup_date=data.get("last_backup_date") or None,
            last_backup_at=data.get("last_backup_at") or None,
        )


def hm_key(hour: int, minute: int) -> str:
    return f"{int(hour)}:{int(minute)}"


def is_at_or_after(now: datetime, hour: int, minute: int) -> bool:
    """当前时间是否已到达或超过今日触发点（同日比较）。"""
    return (now.hour, now.minute) >= (int(hour), int(minute))


def should_fire_job(
    now: datetime,
    *,
    enabled: bool,
    last_date: Optional[str],
    trigger_hour: int,
    trigger_minute: int,
) -> bool:
    """是否应在本轮触发（不含周末/节假日跳过逻辑）。"""
    if not enabled:
        return False
    today = now.strftime("%Y-%m-%d")
    if last_date == today:
        return False
    return is_at_or_after(now, trigger_hour, trigger_minute)


def should_fire_backup(
    now: datetime,
    *,
    enabled: bool,
    last_date: Optional[str],
    trigger_hour: int,
    interval_days: int,
) -> bool:
    """自动备份：到点或过点补跑 + 距上次成功备份 >= interval_days 天。
    频率切换无需清标记（间隔判定天然兼容）。"""
    if not enabled:
        return False
    if not is_at_or_after(now, trigger_hour, 0):
        return False
    if not last_date:
        return True
    try:
        last = datetime.strptime(last_date, "%Y-%m-%d").date()
    except ValueError:
        return True
    return (now.date() - last).days >= int(interval_days)


def load_state(path: Optional[Path] = None) -> JobScheduleState:
    p = path or STATE_FILE
    if not p.is_file():
        return JobScheduleState()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return JobScheduleState()
        return JobScheduleState.from_dict(data)
    except Exception as e:
        logger.warning("load ai_schedule_state failed: %s", e)
        return JobScheduleState()


def save_state(state: JobScheduleState, path: Optional[Path] = None) -> None:
    p = path or STATE_FILE
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(state.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as e:
        logger.warning("save ai_schedule_state failed: %s", e)


def sync_trigger_keys(
    state: JobScheduleState,
    *,
    plan_hour: int,
    plan_minute: int,
    review_hour: int,
    review_minute: int,
    path: Optional[Path] = None,
) -> JobScheduleState:
    """触发时刻变更时清除对应 last_*_date，允许同日按新时刻再跑。"""
    ph = hm_key(plan_hour, plan_minute)
    rh = hm_key(review_hour, review_minute)
    changed = False
    if state.plan_hm is not None and state.plan_hm != ph:
        logger.info(
            "每日计划触发时刻变更 %s → %s，清除 last_plan_date",
            state.plan_hm,
            ph,
        )
        state.last_plan_date = None
        changed = True
    if state.review_hm is not None and state.review_hm != rh:
        logger.info(
            "每日复盘触发时刻变更 %s → %s，清除 last_review_date",
            state.review_hm,
            rh,
        )
        state.last_review_date = None
        changed = True
    if state.plan_hm != ph or state.review_hm != rh:
        state.plan_hm = ph
        state.review_hm = rh
        changed = True
    if changed:
        save_state(state, path)
    return state
