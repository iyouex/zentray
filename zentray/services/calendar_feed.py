# zentray/services/calendar_feed.py
"""
系统日历订阅源 —— 维护 <数据目录>/calendar/zentray.ics 固定路径源文件。

日历应用订阅该文件后自行重读（UID 稳定则原位更新/删除），任务/模板
任何变更都全量重写快照。开关关闭时写空 VCALENDAR，订阅方自动清空。

可靠性约定同飞书同步：refresh 在任务操作路径上绝不抛错，失败只记日志。
Windows Outlook 不支持本地文件订阅，设置卡提供「导出一次」兜底。
"""
from __future__ import annotations

import datetime
import logging
import os

from zentray.core.periodic import period_display_prefix, project_future_instances

logger = logging.getLogger(__name__)

FEED_SUBDIR = "calendar"
FEED_NAME = "zentray.ics"

_PRIORITY_TAG = {"high": "🔴", "medium": "", "low": "⬇"}


def ics_escape(text: str) -> str:
    """ics 文本转义（反斜杠/换行/分号/逗号），行超 75 字节折叠从简。"""
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace("\r", "")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def build_tasks_ics(tasks, templates=None, today: datetime.date = None) -> str:
    """活跃任务（+可选模板未来日程投影）→ VCALENDAR 文本。

    纯函数便于单测；CRLF 为 ics 规范行尾。截止日=全天事件；
    提醒开启时以提醒时间起 30 分钟。已派发的真实周期实例与投影同日去重。
    """
    today = today or datetime.date.today()
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ZenTray//Task Export//CN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:ZenTray",
        "X-PUBLISHED-TTL:PT1H",
    ]
    now = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    # 已派发真实实例占用的 (template_id, deadline)：投影跳过避免同日双事件
    spawned = {
        (t.template_id, str(t.deadline))
        for t in tasks
        if getattr(t, "task_type", "") == "periodic_instance"
        and getattr(t, "template_id", None)
        and getattr(t, "deadline", None)
    }
    for t in tasks:
        deadline = getattr(t, "deadline", None)
        rem = getattr(t, "reminder", None)
        rem_time = None
        if rem is not None and getattr(rem, "enabled", False):
            rem_time = getattr(rem, "time_of_day", None) or "17:00"
        if not deadline and not rem_time:
            continue
        title = f"{_PRIORITY_TAG.get(getattr(t, 'priority', ''), '')}{t.title}".strip()
        desc = ics_escape(f"分类: {t.category or '未分类'}\n{getattr(t, 'details', '') or ''}")
        if deadline:
            try:
                datetime.date.fromisoformat(str(deadline))
            except ValueError:
                deadline = None
        if deadline and rem_time:
            start = f"{str(deadline).replace('-', '')}T{rem_time.replace(':', '')}00"
            end_t = (
                datetime.datetime.combine(
                    datetime.date.fromisoformat(str(deadline)),
                    datetime.time.fromisoformat(rem_time),
                )
                + datetime.timedelta(minutes=30)
            ).strftime("%Y%m%dT%H%M%S")
        elif deadline:
            start = str(deadline).replace("-", "")
            end_t = None
        elif rem_time:
            # 无截止日但开了提醒：今天起 30 分钟事件
            start = (datetime.datetime.combine(today, datetime.time.fromisoformat(rem_time))).strftime(
                "%Y%m%dT%H%M%S"
            )
            end_t = (
                datetime.datetime.combine(today, datetime.time.fromisoformat(rem_time))
                + datetime.timedelta(minutes=30)
            ).strftime("%Y%m%dT%H%M%S")
        else:
            continue
        lines += [
            "BEGIN:VEVENT",
            f"UID:zentray-{t.id}@zentray.local",
            f"DTSTAMP:{now}",
        ]
        if deadline and end_t is None:
            lines.append(f"DTSTART;VALUE=DATE:{start}")
        else:
            lines.append(f"DTSTART:{start}")
            lines.append(f"DTEND:{end_t}")
        lines += [
            f"SUMMARY:{ics_escape(title)}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT",
        ]
    # 模板投影（在真实实例之后统一追加，避免打断任务循环）
    for tmpl in templates or []:
        if not getattr(tmpl, "calendar_enabled", False):
            continue
        n = max(1, int(getattr(tmpl, "interval", 1) or 1))
        for spawn_day, deadline in project_future_instances(tmpl, today):
            if not deadline or (tmpl.template_id, deadline) in spawned:
                continue
            prefix = period_display_prefix(
                tmpl.periodicity or "daily", spawn_day, n
            )
            title = f"【{prefix}】{tmpl.base_title}"
            lines += [
                "BEGIN:VEVENT",
                f"UID:zentray-tpl-{tmpl.template_id}-{deadline}@zentray.local",
                f"DTSTAMP:{now}",
                f"DTSTART;VALUE=DATE:{str(deadline).replace('-', '')}",
                f"SUMMARY:{ics_escape(title)}",
                "END:VEVENT",
            ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


EMPTY_ICS = (
    "\r\n".join(
        [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//ZenTray//Task Export//CN",
            "CALSCALE:GREGORIAN",
            "X-WR-CALNAME:ZenTray",
            "END:VCALENDAR",
        ]
    )
    + "\r\n"
)


class CalendarFeedService:
    """单例。refresh 全量重写订阅源文件；未启用且有文件时写空日历。"""

    _instance = None

    @classmethod
    def instance(cls) -> "CalendarFeedService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def feed_path(self):
        from zentray import config

        return config.DATA_DIR / FEED_SUBDIR / FEED_NAME

    def refresh(self, tasks, templates) -> None:
        """任务操作路径上调用，绝不抛错。"""
        try:
            from zentray.services.settings_manager import SettingsManager

            enabled = SettingsManager().calendar.enabled
            path = self.feed_path
            if not enabled:
                if path.exists():
                    self._atomic_write(path, EMPTY_ICS)
                return
            ics = build_tasks_ics(tasks, templates)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._atomic_write(path, ics)
        except Exception:
            logger.exception("日历订阅源刷新失败")

    @staticmethod
    def _atomic_write(path, content: str) -> None:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
