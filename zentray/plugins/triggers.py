"""插件触发器：状态、判定与事件分发。

纯逻辑部分（should_fire / trigger_key）无 Qt 依赖可直接单测；
dispatch_event / poll_timers 为薄布线层，依赖经 configure() 注入。

状态文件 DATA_DIR/plugin_triggers.json：
  authorized: {pid: bool}   三态——缺失=从未询问；false=已拒绝（持久不再问）
  watermarks: {key: str}    daily=日期 / interval=ISO 时间 / cron=分钟键
  last_skip:  {pid: {reason,time}}  busy/番茄跳过记录（排查用，不通知）
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


def load_state() -> TriggerState:
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return TriggerState(
            authorized=dict(raw.get("authorized") or {}),
            watermarks=dict(raw.get("watermarks") or {}),
            last_skip=dict(raw.get("last_skip") or {}),
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
        for trig in effective_triggers(plug.manifest.id, plug.manifest.triggers):
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
