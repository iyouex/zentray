"""插件触发器：状态、判定与事件分发。

纯逻辑部分（should_fire / trigger_key）无 Qt 依赖可直接单测；
dispatch_event / poll_timers 为薄布线层，依赖经 configure() 注入。

状态文件 DATA_DIR/plugin_triggers.json：
  authorized: {pid: bool}   三态——缺失=从未询问；false=已拒绝（持久不再问）
  watermarks: {key: str}    daily=日期 / interval=ISO 时间 / cron=分钟键
  last_skip:  {pid: {reason,time}}  busy/番茄跳过记录（排查用，不通知）
  legacy_migrated: bool     内置计划/复盘 → chaowen/musheng 一次性迁移标记
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QObject, Signal

from zentray.config import DATA_DIR
from zentray.core.models import Task
from zentray.plugins.loader import LoadedPlugin
from zentray.plugins.models import PluginTrigger, TriggerEvent, TriggerType

logger = logging.getLogger(__name__)

STATE_FILE = DATA_DIR / "plugin_triggers.json"

_state_lock = threading.Lock()
_deps_lock = threading.Lock()
# 授权弹窗在途：pid -> 待补跑上下文 {trigger, task}；内存态，重启即清
_auth_pending: Dict[str, dict] = {}


@dataclass
class TriggerState:
    authorized: Dict[str, bool] = field(default_factory=dict)
    watermarks: Dict[str, str] = field(default_factory=dict)
    last_skip: Dict[str, dict] = field(default_factory=dict)
    # 内置计划/复盘 → chaowen/musheng 插件的一次性迁移已完成
    legacy_migrated: bool = False


def load_state() -> TriggerState:
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return TriggerState(
            authorized=dict(raw.get("authorized") or {}),
            watermarks=dict(raw.get("watermarks") or {}),
            last_skip=dict(raw.get("last_skip") or {}),
            legacy_migrated=bool(raw.get("legacy_migrated")),
        )
    except Exception:
        return TriggerState()


def save_state(state: TriggerState) -> None:
    with _state_lock:
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(
                json.dumps(
                    {
                        "authorized": state.authorized,
                        "watermarks": state.watermarks,
                        "last_skip": state.last_skip,
                        "legacy_migrated": state.legacy_migrated,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            logger.exception("插件触发状态落盘失败")


# ==========================================
# 判定（纯函数）
# ==========================================


def trigger_key(pid: str, trig: PluginTrigger) -> str:
    if trig.type == TriggerType.DAILY:
        return f"{pid}:daily:{trig.time}"
    if trig.type == TriggerType.INTERVAL:
        return f"{pid}:interval:{trig.minutes}"
    if trig.type == TriggerType.CRON:
        return f"{pid}:cron:{trig.expr}"
    return f"{pid}:event:{trig.event}"


def should_fire(
    trig: PluginTrigger, now: _dt.datetime, watermark: Optional[str]
) -> tuple[bool, str]:
    """定时触发判定 → (是否触发, 新水位)。

    daily 复用 ai_schedule 的 fire-or-catch-up 语义（到点或过点补跑、当日去重）。
    """
    from zentray.workers.ai_schedule import should_fire_job

    if trig.type == TriggerType.DAILY:
        hour, minute = (int(x) for x in (trig.time or "00:00").split(":"))
        fire = should_fire_job(
            now,
            enabled=True,
            last_date=watermark,
            trigger_hour=hour,
            trigger_minute=minute,
        )
        return fire, now.strftime("%Y-%m-%d")

    if trig.type == TriggerType.INTERVAL:
        if not watermark:
            return True, now.isoformat(timespec="seconds")  # 刚授权立即跑一次
        try:
            last = _dt.datetime.fromisoformat(watermark)
        except ValueError:
            return True, now.isoformat(timespec="seconds")
        elapsed = (now - last).total_seconds() / 60.0
        if elapsed >= int(trig.minutes or 0):
            return True, now.isoformat(timespec="seconds")
        return False, watermark

    if trig.type == TriggerType.CRON:
        from zentray.plugins import cron as plugin_cron

        minute_key = now.strftime("%Y%m%d_%H%M")
        if minute_key == watermark:
            return False, watermark  # 同分钟已触发，防双发
        if plugin_cron.matches(trig.expr or "", now):
            return True, minute_key
        return False, watermark

    return False, watermark or ""


def effective_triggers(pid: str, manifest_triggers: list) -> list:
    """调度规则覆盖层：settings.ops.trigger_overrides[pid] 优先，缺失回落 manifest。

    覆盖层整体非列表 → 回落 manifest；条目非法 → 丢弃该条并记日志
    （坏数据不打断轮询线程）。空列表=显式禁用全部触发。
    """
    try:
        from zentray.services.settings_manager import SettingsManager

        raw = SettingsManager().ops.trigger_overrides.get(pid)
    except Exception:
        raw = None
    if raw is None:
        return list(manifest_triggers)
    if not isinstance(raw, list):
        logger.warning("插件 %s 调度规则覆盖层非法（非列表），回落 manifest", pid)
        return list(manifest_triggers)

    from zentray.plugins.manifest import _validate_triggers
    from zentray.plugins.models import PluginType

    errors: list = []
    out = _validate_triggers(raw, PluginType.SCRIPT, 2, errors)
    if errors:
        logger.warning("插件 %s 调度规则覆盖层含非法条目，已忽略: %s", pid, errors)
    return out


def event_triggers(plug: LoadedPlugin, event: str) -> list:
    return [
        t
        for t in effective_triggers(plug.manifest.id, plug.manifest.triggers)
        if t.type == TriggerType.EVENT and t.event is not None and t.event.value == event
    ]


# ==========================================
# 周期参数插件（朝闻/暮省范式）：参数预设推导定时
# ==========================================


def _preset_params(pid: str, manifest) -> dict:
    """manifest 参数默认值，被参数预设覆盖（预设 > manifest default）。"""
    out = {p.name: (p.default or "") for p in manifest.params}
    try:
        from zentray.services.settings_manager import SettingsManager

        presets = SettingsManager().ops.param_presets.get(pid)
        if isinstance(presets, dict):
            out.update(presets)
    except Exception:
        pass
    return out


def _is_period_plugin(manifest) -> bool:
    """声明 period 入参 = 周期由参数预设推导（日/周/月）。"""
    return any(p.name == "period" for p in manifest.params)


def _period_raw(vals: dict) -> Optional[dict]:
    """预设 → 触发器原始 dict；非法值返回 None（回落 manifest 触发）。

    daily→daily HH:MM；weekly→cron 分 时 * * 周几（1=周一…7=周日）；
    monthly→cron 分 时 几号 * *。
    """
    try:
        h, mi = (int(x) for x in str(vals.get("time") or "").split(":")[:2])
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            return None
        period = str(vals.get("period") or "daily").strip().lower()
        if period == "weekly":
            dow = max(1, min(7, int(str(vals.get("weekday") or "1"))))
            return {"type": "cron", "expr": f"{mi} {h} * * {dow}"}
        if period == "monthly":
            dom = max(1, min(31, int(str(vals.get("day_of_month") or "1"))))
            return {"type": "cron", "expr": f"{mi} {h} {dom} * *"}
        return {"type": "daily", "time": f"{h:02d}:{mi:02d}"}
    except (TypeError, ValueError):
        return None


def scheduled_triggers(plug: LoadedPlugin) -> list:
    """定时触发集。period 插件由参数预设实时推导（每轮轮询重算，改时间
    自然换 key 重触发）；其余走 trigger_overrides 覆盖层。"""
    m = plug.manifest
    if not _is_period_plugin(m):
        return effective_triggers(m.id, m.triggers)
    raw = _period_raw(_preset_params(m.id, m))
    if raw is None:
        return list(m.triggers)
    from zentray.plugins.manifest import _validate_triggers
    from zentray.plugins.models import PluginType

    errors: list = []
    out = _validate_triggers([raw], PluginType.SCRIPT, 2, errors)
    if errors or not out:
        logger.warning("插件 %s 周期参数非法，回落 manifest 触发: %s", m.id, errors)
        return list(m.triggers)
    return out


def _skip_today(plug: LoadedPlugin, now: _dt.datetime) -> bool:
    """period 插件公休日跳过（周末/法定节假日；与旧内置计划/复盘同语义：
    跳过即当日不跑）。"""
    m = plug.manifest
    if not _is_period_plugin(m):
        return False
    vals = _preset_params(m.id, m)
    skip_weekends = str(vals.get("skip_weekends") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    skip_holidays = str(vals.get("skip_holidays") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if not (skip_weekends or skip_holidays):
        return False
    from zentray.core.holidays import should_skip_auto_review

    return should_skip_auto_review(
        now.date(), skip_weekends=skip_weekends, skip_holidays=skip_holidays
    )


def migrate_legacy_jobs() -> None:
    """一次性迁移（幂等）：内置每日计划/复盘 → chaowen/musheng 插件。

    旧 ai.plan / ai.review 的触发时间、跳过与保存参数 → ops.param_presets；
    enabled → 插件自动运行授权；per-job 通知渠道 → 插件级通知渠道（若可用）。
    """
    state = load_state()
    if state.legacy_migrated:
        return
    try:
        from zentray.services.settings_manager import SettingsManager

        sm = SettingsManager()
        for pid, job in (("chaowen", sm.ai.plan), ("musheng", sm.ai.review)):
            if pid not in sm.ops.param_presets:
                sm.ops.param_presets[pid] = {
                    "period": "daily",
                    "time": f"{int(job.trigger_hour):02d}:{int(job.trigger_minute):02d}",
                    "weekday": "1",
                    "day_of_month": "1",
                    "skip_weekends": "true" if job.skip_weekends else "false",
                    "skip_holidays": "true" if job.skip_holidays else "false",
                    "save_local": "true" if job.save_local else "false",
                }
            if pid not in state.authorized:
                state.authorized[pid] = bool(job.enabled)
            channels = [c for c in (job.notify_channels or []) if c]
            if channels and hasattr(sm.ops, "plugin_notify_channels"):
                sm.ops.plugin_notify_channels.setdefault(pid, channels)
        sm.save()
        state.legacy_migrated = True
        save_state(state)
        logger.info("内置计划/复盘已迁移为插件（chaowen/musheng）")
    except Exception:
        logger.exception("计划/复盘插件迁移失败（下次启动重试）")


# ==========================================
# 布线（依赖注入 + 分发）
# ==========================================


class TriggerSignals(QObject):
    """跨线程授权请求：worker/HTTP 线程 emit，主线程弹窗。

    必须连接 QObject 绑定方法（AutoConnection 排队回主线程），禁 lambda。
    """

    authorize_requested = Signal(str, str)  # plugin_id, plugin_name


_signals = TriggerSignals()


def signals() -> TriggerSignals:
    return _signals


_deps: dict = {"loader": None, "runtime": None, "pomodoro": None}


def configure(loader, runtime, pomodoro_service) -> None:
    """main 启动时注入依赖（与 handlers.set_api_context 同模式）。"""
    with _deps_lock:
        _deps["loader"] = loader
        _deps["runtime"] = runtime
        _deps["pomodoro"] = pomodoro_service


def _ops_enabled() -> bool:
    try:
        from zentray.services.settings_manager import SettingsManager

        return bool(SettingsManager().ops.enabled)
    except Exception:
        return False


def _rescan() -> None:
    """重扫插件目录（新装插件无需重启）。与 reload_ops_plugins 同源逻辑。"""
    from zentray.resources import get_resource_path
    from zentray.services.settings_manager import SettingsManager

    loader = _deps.get("loader")
    if loader is None:
        return
    bundled = get_resource_path("bundled_plugins")
    user = SettingsManager().get_ops_user_plugins_dir()
    loader.scan(
        bundled_dir=bundled if bundled.is_dir() else None,
        user_dir=user,
    )


def authorize(plugin_id: str, allowed: bool) -> None:
    """记录授权结论；allowed=True 时补跑在等授权的那次触发。"""
    state = load_state()
    state.authorized[plugin_id] = bool(allowed)
    save_state(state)
    ctx = _auth_pending.pop(plugin_id, None)
    if allowed and ctx:
        _fire_now(plugin_id, trigger=ctx.get("trigger", "manual"), task=ctx.get("task"))


def is_authorized(plugin_id: str) -> Optional[bool]:
    """True/False=已授权/已拒绝；None=从未询问。"""
    return load_state().authorized.get(plugin_id)


def dispatch_event(event: str, task: Optional[Task] = None) -> None:
    """事件触发入口（task_done / pomodoro_end / startup）。

    从任意线程调用；run_script 自带单飞锁，弹窗经信号回主线程。
    """
    try:
        if not _ops_enabled():
            return
        loader = _deps.get("loader")
        runtime = _deps.get("runtime")
        if loader is None or runtime is None:
            return
        for plug in loader.plugins:
            if not event_triggers(plug, event):
                continue
            _try_fire(plug, trigger=event, task=task)
    except Exception:
        logger.exception("插件事件分发失败: %s", event)


def poll_timers() -> None:
    """分钟轮询入口（PluginTriggerWorker 调用）：daily / interval / cron。"""
    if not _ops_enabled():
        return
    loader = _deps.get("loader")
    if loader is None:
        return
    _rescan()
    now = _dt.datetime.now()
    for plug in loader.plugins:
        for trig in scheduled_triggers(plug):
            if trig.type == TriggerType.EVENT:
                continue
            key = trigger_key(plug.manifest.id, trig)
            state = load_state()
            fire, new_wm = should_fire(trig, now, state.watermarks.get(key))
            if not fire:
                continue
            if state.authorized.get(plug.manifest.id) is not True:
                _request_authorize(plug, trigger=trig.type.value, task=None)
                continue
            if _skip_today(plug, now):
                # 公休日跳过 = 记水位当日不再触发（与旧内置计划/复盘一致）
                state.watermarks[key] = new_wm
                save_state(state)
                logger.info("插件触发跳过（公休日）: %s", plug.manifest.id)
                continue
            if _fire_now(plug.manifest.id, trigger=trig.type.value, task=None):
                state = load_state()
                state.watermarks[key] = new_wm
                save_state(state)


def _try_fire(plug: LoadedPlugin, *, trigger: str, task: Optional[Task]) -> None:
    pid = plug.manifest.id
    state = load_state()
    auth = state.authorized.get(pid)
    if auth is None:
        _request_authorize(plug, trigger=trigger, task=task)
        return
    if auth is False:
        return  # 已拒绝，静默
    _fire_now(pid, trigger=trigger, task=task)


def _fire_now(plugin_id: str, *, trigger: str, task: Optional[Task]) -> bool:
    """启动脚本；busy/番茄中则记 last_skip 静默跳过。返回是否已启动。"""
    loader = _deps.get("loader")
    runtime = _deps.get("runtime")
    pomo = _deps.get("pomodoro")
    if loader is None or runtime is None:
        return False
    plug = loader.get(plugin_id)
    if plug is None:
        return False
    if bool(getattr(pomo, "is_active", False)):
        _record_skip(plugin_id, "pomodoro")
        return False
    if not runtime.run_script(
        plug, pomodoro_active=False, task=task, trigger=trigger
    ):
        _record_skip(plugin_id, "busy")
        return False
    logger.info("插件自动触发: %s (%s)", plugin_id, trigger)
    return True


def _record_skip(plugin_id: str, reason: str) -> None:
    state = load_state()
    state.last_skip[plugin_id] = {
        "reason": reason,
        "time": _dt.datetime.now().isoformat(timespec="seconds"),
    }
    save_state(state)
    logger.info("插件触发跳过: %s (%s)", plugin_id, reason)


def _request_authorize(plug: LoadedPlugin, *, trigger: str, task: Optional[Task]) -> None:
    pid = plug.manifest.id
    if pid in _auth_pending:
        return  # 弹窗在途，不重复打扰
    _auth_pending[pid] = {"trigger": trigger, "task": task}
    _signals.authorize_requested.emit(pid, plug.manifest.name)
