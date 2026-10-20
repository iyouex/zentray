"""一次性迁移（幂等）：朝闻/暮省参数预设 → 关联周期任务。

插件自调度已删除（2026-10-20），调度唯一去处=任务时间四要素。
旧 plugin_triggers.json 存在且未打标记时，按两插件参数预设各建一条
周期模板（period→周期类型、time→截止弹窗时刻、skip_*→跳过公休日、
plugin_id 关联），随后在文件内打标记停读；无预设/未授权自动运行则不建。
"""
from __future__ import annotations

import json
import logging

from zentray.config import DATA_DIR
from zentray.core.models import PeriodicTemplate

logger = logging.getLogger(__name__)

STATE_FILE = DATA_DIR / "plugin_triggers.json"
MARKER = "tasks_migrated"

_PLUGINS = {
    "chaowen": "朝闻",
    "musheng": "暮省",
}


def migrate_legacy_scheduling(template_repo) -> None:
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return  # 文件缺失/损坏：无存量，跳过
    if not isinstance(raw, dict) or raw.get(MARKER):
        return

    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager()
    authorized = raw.get("authorized") or {}
    existing = template_repo.find_all()
    built = []
    for pid, name in _PLUGINS.items():
        preset = sm.ops.param_presets.get(pid)
        if not preset or authorized.get(pid) is False:
            continue  # 无预设/曾拒绝自动运行：由用户手动建关联任务
        if any(t.plugin_id == pid and t.base_title == name for t in existing):
            continue  # 已有同名关联模板（含标记丢失重跑）：不重复建
        try:  # 坏时刻（缺省/非法）不建任务，由用户手动建
            hh, mm = str(preset.get("time") or "").strip().split(":")
            h, m = int(hh), int(mm)
            if not (0 <= h <= 23 and 0 <= m <= 59):
                raise ValueError
        except (ValueError, IndexError, TypeError):
            continue
        due_time = f"{h:02d}:{m:02d}"
        period = str(preset.get("period") or "daily")
        tmpl = PeriodicTemplate(
            base_title=name,
            category="工作",
            periodicity=period if period in ("daily", "weekly", "monthly") else "daily",
            plugin_id=pid,
            # 旧 skip 语义并入跳过公休日（周末+法定节假日）
            skip_holidays=str(preset.get("skip_holidays")).lower() == "true"
            or str(preset.get("skip_weekends")).lower() == "true",
            due_time=due_time,
            popup_at_due=True,
        )
        try:
            if tmpl.periodicity == "weekly":
                tmpl.deadline_weekday = max(0, min(6, int(preset.get("weekday") or 1) - 1))
            elif tmpl.periodicity == "monthly":
                tmpl.deadline_day_of_month = max(1, min(31, int(preset.get("day_of_month") or 1)))
        except (TypeError, ValueError):
            continue  # 周几/几号脏值：不建任务，由用户手动建
        built.append(tmpl)

    if built:
        template_repo.save_all(template_repo.find_all() + built)
        logger.info("插件调度已迁移为关联周期任务: %s", [t.base_title for t in built])

    raw[MARKER] = True
    try:
        STATE_FILE.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        logger.exception("plugin_triggers.json 迁移标记写入失败（下次启动重试）")
