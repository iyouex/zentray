# zentray/api/handlers.py
"""
API 处理函数 —— 仅转调既有服务，不重写业务规则。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _task_dict(task) -> dict:
    if task is None:
        return {}
    d = task.to_dict() if hasattr(task, "to_dict") else asdict(task)
    return d


def _template_dict(tmpl) -> dict:
    if tmpl is None:
        return {}
    d = tmpl.to_dict() if hasattr(tmpl, "to_dict") else asdict(tmpl)
    import datetime as _dt

    from zentray.core.periodic import next_spawn_date

    ns = next_spawn_date(tmpl, _dt.date.today())
    d["next_spawn_date"] = ns.isoformat() if ns else None
    return d


class ApiContext:
    """运行时注入：task_service + 刷新托盘回调。"""

    def __init__(
        self,
        task_service=None,
        on_changed: Optional[Callable[[], None]] = None,
        apply_settings: Optional[Callable[[], None]] = None,
        plugin_runtime=None,
        plugin_loader=None,
        pomodoro_service=None,
        start_pomodoro: Optional[Callable[[str], None]] = None,
        mark_report_viewed: Optional[Callable[[str], None]] = None,
        pomodoro_control: Optional[Callable[[str], None]] = None,
        report_rotation=None,
    ):
        self.task_service = task_service
        self.on_changed = on_changed or (lambda: None)
        self.apply_settings = apply_settings or (lambda: None)
        self.plugin_runtime = plugin_runtime
        self.plugin_loader = plugin_loader
        self.pomodoro_service = pomodoro_service
        # 主线程启动番茄钟（HTTP 线程直接 start 会跨线程启 QTimer）
        self.start_pomodoro = start_pomodoro or (lambda task_id: None)
        # 报告被打开（经 UI 中继回主线程，移出顶栏轮播）
        self.mark_report_viewed = mark_report_viewed or (lambda key: None)
        # 番茄控制（stop/extend/skip_break，同样经 UI 中继回主线程）
        self.pomodoro_control = pomodoro_control
        # 报告轮播槽（速览面板读取待看报告）
        self.report_rotation = report_rotation


_ctx = ApiContext()


def set_api_context(ctx: ApiContext) -> None:
    global _ctx
    _ctx = ctx


def get_api_context() -> ApiContext:
    return _ctx


def handle_request(
    method: str,
    path: str,
    body: Any = None,
    query: Optional[dict] = None,
) -> tuple[int, dict]:
    """
    路由分发。返回 (status_code, json_body)。
    path 不含 query，已 strip。
    """
    method = method.upper()
    path = path.split("?", 1)[0].rstrip("/") or "/"
    body = body if isinstance(body, dict) else {}
    query = query or {}

    try:
        if method == "GET" and path == "/api/health":
            from zentray.config import VERSION

            return 200, {"ok": True, "version": VERSION, "ui": "vue"}

        if method == "GET" and path == "/api/meta":
            return 200, _meta()

        if method == "POST" and path == "/api/attachments/open":
            return _attachment_open(body)

        if method == "GET" and path == "/api/tasks":
            return 200, {"items": [_task_dict(t) for t in _ctx.task_service.get_all_tasks()]}

        if method == "GET" and path == "/api/tasks/archived":
            return _archived_list(query)

        if method == "GET" and path.startswith("/api/tasks/"):
            tid = path[len("/api/tasks/") :]
            if "/" in tid:
                return _task_sub(method, tid, body)
            task = _ctx.task_service.find_task(tid)
            if not task:
                return 404, {"error": "task not found"}
            return 200, {"item": _task_dict(task)}

        if method == "POST" and path == "/api/tasks":
            task = _ctx.task_service.create_task(body)
            _ctx.on_changed()
            return 200, {"item": _task_dict(task)}

        if method == "PUT" and path.startswith("/api/tasks/"):
            tid = path[len("/api/tasks/") :]
            if "/" in tid:
                return _task_sub(method, tid, body)
            # 保留周期实例类型
            fresh = _ctx.task_service.find_task(tid)
            if not fresh:
                return 404, {"error": "task not found"}
            data = dict(body)
            if getattr(fresh, "task_type", None) == "periodic_instance":
                data["task_type"] = "periodic_instance"
                data["template_id"] = fresh.template_id
            task = _ctx.task_service.update_task(tid, data)
            _ctx.on_changed()
            return 200, {"item": _task_dict(task)}

        # 子任务/提醒等复合子路径：须在 /done /abandon /select 后缀分支之前
        # （"/subtasks/{sid}/done" 同样 endswith "/done"），以 parts[1] 白名单门控放行普通后缀
        if method == "POST" and path.startswith("/api/tasks/"):
            rest = path[len("/api/tasks/") :]
            parts = rest.split("/")
            if len(parts) >= 2 and parts[1] in ("subtasks", "reminder-action"):
                return _task_sub(method, rest, body)

        if method == "POST" and path.startswith("/api/tasks/") and path.endswith("/done"):
            tid = path[len("/api/tasks/") : -len("/done")]
            _ctx.task_service.mark_done(tid)
            _ctx.on_changed()
            return 200, {"ok": True}

        if method == "POST" and path.startswith("/api/tasks/") and path.endswith("/abandon"):
            tid = path[len("/api/tasks/") : -len("/abandon")]
            _ctx.task_service.abandon(tid)
            _ctx.on_changed()
            return 200, {"ok": True}

        if method == "POST" and path.startswith("/api/tasks/") and path.endswith("/select"):
            tid = path[len("/api/tasks/") : -len("/select")]
            _ctx.task_service.select_task(tid)
            _ctx.on_changed()
            return 200, {"ok": True}

        if method == "GET" and path == "/api/templates":
            items = [_template_dict(t) for t in _ctx.task_service.get_all_templates()]
            return 200, {"items": items}

        if method == "GET" and path.startswith("/api/templates/"):
            tid = path[len("/api/templates/") :]
            tmpl = _ctx.task_service.find_template(tid)
            if not tmpl:
                return 404, {"error": "template not found"}
            return 200, {"item": _template_dict(tmpl)}

        if method == "POST" and path == "/api/templates":
            data = dict(body)
            data["task_type"] = "periodic"
            tmpl = _ctx.task_service.create_task(data)
            _ctx.on_changed()
            return 200, {"item": _template_dict(tmpl)}

        if method == "PUT" and path.startswith("/api/templates/"):
            tid = path[len("/api/templates/") :]
            tmpl = _ctx.task_service.update_template(tid, body)
            _ctx.on_changed()
            return 200, {"item": _template_dict(tmpl)}

        if method == "DELETE" and path.startswith("/api/templates/"):
            tid = path[len("/api/templates/") :]
            ok = _ctx.task_service.delete_template(tid)
            _ctx.on_changed()
            return 200, {"ok": bool(ok)}

        if method == "POST" and path.startswith("/api/templates/") and path.endswith("/skip"):
            tid = path[len("/api/templates/") : -len("/skip")]
            try:
                count = int(body.get("count", 1))
            except (TypeError, ValueError):
                count = 1
            tmpl = _ctx.task_service.skip_template(tid, max(1, min(52, count)))
            if not tmpl:
                return 404, {"error": "template not found"}
            _ctx.on_changed()
            return 200, {"item": _template_dict(tmpl)}

        if method == "GET" and path == "/api/settings":
            return 200, {"settings": _settings_dict()}

        if method == "PUT" and path == "/api/settings":
            _save_settings(body.get("settings") or body)
            _ctx.apply_settings()
            _ctx.on_changed()
            return 200, {"settings": _settings_dict()}

        if method == "POST" and path == "/api/reminders/check-conflicts":
            return _check_reminder_conflicts(body)

        if method == "POST" and path == "/api/pomodoro/start":
            return _pomodoro_start(body)

        # —— Windows 速览面板（/glance）：复合状态 + 报告打开 + 番茄控制 ——
        if method == "GET" and path == "/api/glance":
            return _glance_state()
        if method == "POST" and path == "/api/glance/report-open":
            return _glance_report_open(body)
        if method == "POST" and path == "/api/pomodoro/control":
            return _pomodoro_control(body)

        # —— 插件：列表 / 校验 / 安装 / 运行 / 运行历史 / 授权 ——
        # 精确路由必须置于下方 /api/plugins/ 前缀匹配之前，避免被吞
        if method == "GET" and path == "/api/plugins/runs":
            return _plugin_runs(query or {})
        if method == "GET" and path == "/api/plugins/runs/log":
            return _plugin_run_log(query or {})
        if method == "POST" and path == "/api/plugins/runs/open":
            return _plugin_run_open(body or {})
        if method == "POST" and path == "/api/plugins/install-zip":
            return _install_plugin_zip(body or {})
        if method == "POST" and path == "/api/plugins/preview-zip":
            return _preview_plugin_zip(body or {})
        if method == "POST" and path.startswith("/api/plugins/") and path.endswith("/authorize"):
            return _authorize_plugin(path[len("/api/plugins/") : -len("/authorize")], body or {})
        if method == "GET" and path == "/api/plugins":
            return 200, _plugins_list()
        if method == "POST" and path == "/api/plugins/validate":
            return _validate_plugin_path(body or {})
        if method == "POST" and path == "/api/plugins/install":
            return _install_plugin_path(body or {})
        if method == "POST" and path.startswith("/api/plugins/") and path.endswith("/run"):
            return _run_plugin(path[len("/api/plugins/") : -len("/run")], body or {})
        if method == "PUT" and path.startswith("/api/plugins/"):
            return _update_plugin(path[len("/api/plugins/") :], body or {})
        if method == "DELETE" and path.startswith("/api/plugins/"):
            return _delete_plugin(path[len("/api/plugins/") :])

        if method == "GET" and path == "/api/current-task":
            t = _ctx.task_service.get_current_task()
            return 200, {"item": _task_dict(t) if t else None}

        if method == "POST" and path == "/api/setup/complete":
            _complete_setup(body or {})
            return 200, {"ok": True}

        if method == "POST" and path == "/api/categories/secondary":
            # 任务页添加二级：primary_id + name
            return _add_secondary_category(body or {})

        if method == "GET" and path == "/api/history":
            return _history_list(query)

        if method == "GET" and path.startswith("/api/history/ai/"):
            from urllib.parse import unquote

            name = unquote(path[len("/api/history/ai/") :])
            return _history_ai_content(name)

        # —— AI 场景能力：文本解析 / 图片识别 / 任务建议（docs/AI-FEATURES.md）——
        if method == "POST" and path == "/api/ai/parse":
            return _ai_parse(body)
        if method == "POST" and path == "/api/ai/ocr":
            return _ai_ocr(body)
        if method == "POST" and path == "/api/ai/suggest":
            return _ai_suggest(body)

        # —— 系统：自启 + 数据迁移 + 备份管理 ——
        if method == "GET" and path == "/api/system/status":
            return _system_status()
        if method == "POST" and path == "/api/system/autostart":
            return _system_set_autostart(body or {})
        if method == "POST" and path == "/api/system/open-taskbar-settings":
            return _open_taskbar_settings()
        if method == "POST" and path == "/api/system/export":
            return _system_export(body or {})
        if method == "POST" and path == "/api/system/import":
            return _system_import(body or {})
        if method == "POST" and path == "/api/system/import-preview":
            return _system_import_preview(body or {})
        if method == "POST" and path == "/api/system/archive/pack":
            return _system_archive_pack()
        if method == "POST" and path == "/api/system/calendar-export":
            return _system_calendar_export()
        if method == "GET" and path == "/api/system/backups":
            return _system_backups()
        if method == "POST" and path == "/api/system/backups/delete":
            return _system_backup_delete(body or {})

        return 404, {"error": f"not found: {method} {path}"}
    except Exception as e:
        logger.exception("API error %s %s", method, path)
        return 500, {"error": str(e)}


def _task_sub(method: str, rest: str, body: dict) -> tuple[int, dict]:
    """任务复合子路径：子任务操作。rest like "id/subtasks" 或 "id/subtasks/sid/done"。"""
    ts = _ctx.task_service
    parts = rest.split("/")
    if method == "POST" and len(parts) == 2 and parts[1] == "reminder-action":
        action = str(body.get("action") or "")
        if action not in ("done", "snooze", "dismiss"):
            return 400, {"error": "action 必须是 done|snooze|dismiss"}
        try:
            snooze = int(body.get("snooze_minutes") or 10)
        except (TypeError, ValueError):
            snooze = 10
        task = ts.handle_reminder_action(parts[0], action, str(body.get("fire_key") or ""), snooze)
        if task is None:
            return 404, {"error": "task not found"}
        _ctx.on_changed()
        return 200, {"item": _task_dict(task)}
    if method == "POST" and len(parts) == 2 and parts[1] == "subtasks":
        title = str(body.get("title") or "").strip()
        if not title:
            return 400, {"error": "title 必填"}
        task = ts.add_subtask(parts[0], title)
        if not task:
            return 404, {"error": "task not found"}
        _ctx.on_changed()
        return 200, {"item": _task_dict(task)}
    if (
        method == "POST"
        and len(parts) == 4
        and parts[1] == "subtasks"
        and parts[3] in ("done", "abandon")
    ):
        status = "done" if parts[3] == "done" else "abandoned"
        r = ts.set_subtask_status(parts[0], parts[2], status)
        if r is None:
            return 404, {"error": "task or subtask not found"}
        task, auto = r
        _ctx.on_changed()
        return 200, {"item": _task_dict(task), "auto_completed": auto}
    return 404, {"error": f"bad path {rest}"}


def _meta() -> dict:
    from zentray.config import VERSION
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager()
    cats = sm.categories.to_dict()
    return {
        "version": VERSION,
        "categories": cats,
        "quick_add": asdict(sm.quick_add),
        "pomodoro": asdict(sm.pomodoro),
        "ai_features": sm.ai.features.to_dict(),
    }


def _ai_gate(feature: str) -> tuple[int, dict] | None:
    """功能开关门控：未开启返回 403 响应，通过返回 None。"""
    from zentray.services.settings_manager import SettingsManager

    on = bool(getattr(SettingsManager().ai.features, feature, False))
    if not on:
        return 403, {"error": "AI 功能未开启，请在 设置 → AI 能力 中开启", "feature": feature}
    return None


def _category_names() -> list:
    from zentray.services.settings_manager import SettingsManager

    cats = SettingsManager().categories
    names = []
    for p in cats.primary_list or []:
        names.append(p.name)
        for s in p.secondaries or []:
            names.append(
                f"{p.name}{cats.level_separator}{s.name}"
                if cats.level_separator
                else f"{p.name}-{s.name}"
            )
    return names


def _ai_parse(body: dict) -> tuple[int, dict]:
    from zentray.services.ai_assist import AIAssistError, AIAssistService

    denied = _ai_gate("smart_parse")
    if denied:
        return denied
    text = str(body.get("text") or "").strip()
    if not text:
        return 400, {"error": "text 必填"}
    import datetime

    try:
        draft = AIAssistService.parse_text(
            text, _category_names(), datetime.date.today().isoformat()
        )
        return 200, {"draft": draft}
    except AIAssistError as e:
        return 502, {"error": str(e), "feature": e.feature}


def _ai_ocr(body: dict) -> tuple[int, dict]:
    from zentray.services.ai_assist import AIAssistError, AIAssistService

    denied = _ai_gate("image_ocr")
    if denied:
        return denied
    image = str(body.get("image") or "")
    if not image:
        return 400, {"error": "image 必填（data:image/*;base64,...）"}
    import datetime

    try:
        drafts = AIAssistService.parse_image(
            image, _category_names(), datetime.date.today().isoformat()
        )
        return 200, {"drafts": drafts}
    except AIAssistError as e:
        return 502, {"error": str(e), "feature": e.feature}


def _ai_suggest(body: dict) -> tuple[int, dict]:
    from zentray.services.ai_assist import AIAssistError, AIAssistService

    denied = _ai_gate("task_suggest")
    if denied:
        return denied
    ts = _ctx.task_service
    if not ts:
        return 500, {"error": "task service unavailable"}
    import datetime

    focus_id = str(body.get("focus_id") or "")
    focus_title = ""
    summary = []
    for t in ts.get_all_tasks():
        if getattr(t, "task_type", "one-time") == "periodic_instance":
            continue  # 周期实例与一次性任务一起看会重复计数，聚焦手动任务
        subs = t.subtasks or []
        summary.append(
            {
                "title": t.title,
                "category": t.category or "",
                "priority": t.priority or "medium",
                "deadline": t.deadline or "",
                "subtask_done": sum(1 for s in subs if s.get("status") == "done"),
                "subtask_total": len(subs),
            }
        )
        if focus_id and t.id == focus_id:
            focus_title = t.title
    try:
        suggestions = AIAssistService.suggest(
            summary, datetime.date.today().isoformat(), focus_title
        )
        return 200, {"suggestions": suggestions}
    except AIAssistError as e:
        return 502, {"error": str(e), "feature": e.feature}


def _settings_dict() -> dict:
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager()
    s = sm.get_all()
    n = s.notification
    return {
        "polling": asdict(s.polling),
        "pomodoro": asdict(s.pomodoro),
        "nightly": asdict(s.nightly),
        "notification": {
            "channels": [c.to_dict() for c in n.channels],
            "enabled": n.enabled,
            "wxpusher_app_token": n.wxpusher_app_token,
            "wxpusher_uid": n.wxpusher_uid,
        },
        "ai": s.ai.to_dict(),
        "categories": s.categories.to_dict(),
        "quick_add": asdict(s.quick_add),
        "appearance": asdict(s.appearance),
        "backup": asdict(s.backup),
        "ops": asdict(s.ops),
    }


def _check_reminder_conflicts(body: dict) -> tuple[int, dict]:
    """检查候选弹窗提醒是否与已有任务/模板/AI 调度冲突。"""
    from zentray.services.reminder_conflict import find_reminder_conflicts
    from zentray.services.settings_manager import SettingsManager

    reminder = body.get("reminder")
    if not reminder or not isinstance(reminder, dict):
        return 400, {"error": "reminder 必填"}
    if not reminder.get("enabled"):
        return 200, {"conflicts": [], "has_conflict": False}

    sm = SettingsManager()
    ai = sm.ai
    ts = _ctx.task_service
    conflicts = find_reminder_conflicts(
        reminder,
        tasks=ts.get_all_tasks() if ts else [],
        templates=ts.get_all_templates() if ts else [],
        exclude_task_id=body.get("exclude_task_id") or None,
        exclude_template_id=body.get("exclude_template_id") or None,
        plan_enabled=bool(ai.plan.enabled),
        plan_hour=int(ai.plan.trigger_hour),
        plan_minute=int(ai.plan.trigger_minute),
        review_enabled=bool(ai.review.enabled),
        review_hour=int(ai.review.trigger_hour),
        review_minute=int(ai.review.trigger_minute),
    )
    return 200, {
        "has_conflict": bool(conflicts),
        "conflicts": conflicts,
    }


def _scanned_loader():
    """扫描内置+用户目录，返回刷新后的 loader（列表 / 编辑 / 删除共用）。"""
    from zentray.resources import get_resource_path
    from zentray.services.settings_manager import SettingsManager

    loader = _ctx.plugin_loader
    if loader is None:
        from zentray.plugins.loader import PluginLoader

        loader = PluginLoader()

    bundled = get_resource_path("bundled_plugins")
    loader.scan(
        bundled_dir=bundled if bundled.is_dir() else None,
        user_dir=SettingsManager().get_ops_user_plugins_dir(),
    )
    return loader


def _update_plugin(plugin_id: str, body: dict) -> tuple[int, dict]:
    """编辑插件名称/描述：就地改写 plugin.yaml；内置（示例）插件先复制到用户目录。"""
    import shutil

    import yaml

    from zentray.services.settings_manager import SettingsManager

    loader = _scanned_loader()
    p = loader.get(plugin_id)
    if p is None:
        return 404, {"ok": False, "error": "插件不存在或校验未通过"}
    if p.source == "bundled":
        # 包目录不可写（重装会还原）：复制到用户目录形成覆盖副本后再编辑
        dest = SettingsManager().get_ops_user_plugins_dir() / plugin_id
        if dest.exists():
            return 400, {
                "ok": False,
                "error": f"用户插件目录已存在 {dest.name}，请先处理后再编辑示例插件",
            }
        try:
            shutil.copytree(p.manifest.root, dest)
        except OSError as e:
            return 500, {"ok": False, "error": f"复制示例插件到用户目录失败: {e}"}
        p = _scanned_loader().get(plugin_id)
        if p is None or p.source != "user":
            return 500, {"ok": False, "error": "复制后重扫失败，副本未生效"}
    name = str(body.get("name") or "").strip()
    description = str(body.get("description") or "").strip()
    if not name:
        return 400, {"ok": False, "error": "名称不能为空"}
    yaml_path = p.manifest.root / "plugin.yaml"
    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        raw["name"] = name
        raw["description"] = description
        yaml_path.write_text(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    except Exception as e:
        return 500, {"ok": False, "error": f"plugin.yaml 改写失败: {e}"}
    return 200, {"ok": True, "plugins": _plugins_list(scan_always=True)}


def _delete_plugin(plugin_id: str) -> tuple[int, dict]:
    """删除插件：用户目录 rmtree；内置（示例）加入隐藏清单（包文件不动）。"""
    import shutil

    from zentray.services.settings_manager import SettingsManager

    p = _scanned_loader().get(plugin_id)
    if p is None:
        return 404, {"ok": False, "error": "插件不存在或校验未通过"}
    m = p.manifest
    sm = SettingsManager()
    # service 先尽力停掉，避免删除/隐藏后守护进程仍占端口
    if _ctx.plugin_runtime is not None and m.type.value == "service":
        try:
            _ctx.plugin_runtime.service_cmd(p, "stop")
        except Exception:
            logger.exception("删除前停止服务失败: %s", m.id)
    if p.source == "bundled":
        # 包目录不可写且重装/升级会还原文件：删除=记录隐藏（loader 扫描期过滤）
        if plugin_id not in sm.ops.hidden_bundled:
            sm.ops.hidden_bundled.append(plugin_id)
        sm.ops.trigger_overrides.pop(plugin_id, None)
        sm.ops.param_presets.pop(plugin_id, None)
        sm.ops.installed_at.pop(plugin_id, None)
        sm.save()
        return 200, {"ok": True, "plugins": _plugins_list(scan_always=True)}
    root = m.root.resolve()
    try:
        root.relative_to(sm.get_ops_user_plugins_dir().resolve())
    except ValueError:
        return 400, {"ok": False, "error": "插件目录不在用户插件目录内"}
    try:
        shutil.rmtree(root)
    except OSError as e:
        return 500, {"ok": False, "error": f"删除失败: {e}"}
    sm.ops.trigger_overrides.pop(plugin_id, None)
    sm.ops.param_presets.pop(plugin_id, None)
    sm.ops.installed_at.pop(plugin_id, None)
    sm.save()
    return 200, {"ok": True, "plugins": _plugins_list(scan_always=True)}


def _read_plugin_readme(root: Path) -> str:
    """插件 README.md 原文（截断 64KB），无则空串。"""
    try:
        return (Path(root) / "README.md").read_text(encoding="utf-8")[:65536]
    except OSError:
        return ""


def _plugins_list(*, scan_always: bool = False) -> dict:
    """插件列表（含校验失败项）。scan_always 供设置页在未启用时也扫描展示。"""
    from zentray.resources import get_resource_path
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager()
    user_dir = sm.get_ops_user_plugins_dir()
    bundled = get_resource_path("bundled_plugins")
    base = {
        "enabled": bool(sm.ops.enabled),
        "user_dir": str(user_dir),
        "bundled_dir": str(bundled) if bundled.is_dir() else "",
        "items": [],
        "failures": [],
        "busy": False,
    }
    if not sm.ops.enabled and not scan_always:
        return base

    loader = _scanned_loader()
    runtime = _ctx.plugin_runtime
    from zentray.plugins import triggers as _triggers

    import datetime as _dt

    items = []
    for p in loader.plugins:
        m = p.manifest
        # v2.1：列表元数据——分类 / 命名入参 / 更新时间（installed_at 兜底目录
        # mtime）/ 调度规则展示走覆盖层 effective
        try:
            updated_at = sm.ops.installed_at.get(m.id) or _dt.datetime.fromtimestamp(
                m.root.stat().st_mtime
            ).isoformat(timespec="seconds")
        except OSError:
            updated_at = ""
        eff = _triggers.effective_triggers(m.id, m.triggers)
        items.append(
            {
                "id": m.id,
                "name": m.name,
                "type": m.type.value,
                "version": m.version,
                "description": m.description or "",
                "category": m.category or "",
                "source": p.source,
                "entry": m.entry,
                "root": str(m.root),
                "status": "ok",
                "triggers": [t.describe() for t in eff],
                "manifest_triggers": [
                    {
                        "type": t.type.value,
                        "time": t.time,
                        "minutes": t.minutes,
                        "expr": t.expr,
                        "event": t.event.value if t.event else None,
                    }
                    for t in m.triggers
                ],
                "trigger_override": m.id in sm.ops.trigger_overrides,
                "params": [
                    {
                        "name": x.name,
                        "default": x.default,
                        "description": x.description,
                        "variadic": x.variadic,
                    }
                    for x in m.params
                ],
                "updated_at": updated_at,
                "write_back": bool(m.write_back),
                "authorized": _triggers.is_authorized(m.id),
                # 使用说明原文（README.md，无则空），供前端「说明」抽屉展示
                "readme": _read_plugin_readme(m.root),
            }
        )
    failures = []
    for path, result in loader.failures:
        failures.append(
            {
                "path": str(path),
                "errors": list(result.errors),
                "status": "invalid",
            }
        )
    base["items"] = items
    base["failures"] = failures
    base["busy"] = bool(runtime and runtime.is_busy)
    return base


def _allowed_roots() -> list:
    """插件相关路径的允许根（用户家目录 / 数据目录 / 用户插件目录 / 内置目录 / 项目根）。"""
    from zentray.config import DATA_DIR
    from zentray.resources import get_resource_path
    from zentray.services.settings_manager import SettingsManager

    allowed = [
        Path.home().resolve(),
        Path(DATA_DIR).resolve(),
        SettingsManager().get_ops_user_plugins_dir().resolve(),
    ]
    bundled = get_resource_path("bundled_plugins")
    if bundled.is_dir():
        allowed.append(bundled.resolve())
    # 项目开发根
    try:
        from zentray.config import _PROJECT_ROOT

        allowed.append(Path(_PROJECT_ROOT).resolve())
    except Exception:
        pass
    return allowed


def _path_in_allowed_roots(path: Path) -> bool:
    for root in _allowed_roots():
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _safe_plugin_path(raw: str) -> tuple[Optional[Path], Optional[str]]:
    """解析并限制插件路径范围（用户家目录 / 数据目录 / 内置目录）。"""
    if not raw or not str(raw).strip():
        return None, "path 必填"
    path = Path(str(raw).strip()).expanduser().resolve()
    if not path.exists():
        return None, f"路径不存在: {path}"
    if not path.is_dir():
        return None, "path 必须是插件目录"
    if not _path_in_allowed_roots(path):
        return None, "路径不在允许范围内（用户主目录 / 数据目录 / 项目或内置插件目录）"
    return path, None


def _manifest_preview(m) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "type": m.type.value,
        "version": m.version,
        "entry": m.entry,
        "description": m.description or "",
        "timeout_sec": m.timeout_sec,
        "root": str(m.root),
    }


def _validate_plugin_path(body: dict) -> tuple[int, dict]:
    """预览校验：不安装，仅返回 manifest 预览与错误。"""
    from zentray.plugins.manifest import validate_plugin_dir

    path, err = _safe_plugin_path(body.get("path") or "")
    if err:
        return 400, {"ok": False, "errors": [err], "preview": None}
    result = validate_plugin_dir(path)
    preview = None
    if result.manifest is not None:
        preview = _manifest_preview(result.manifest)
    return 200, {
        "ok": result.ok,
        "errors": list(result.errors),
        "preview": preview,
        "path": str(path),
    }


def _install_validated_dir(src: Path, manifest, overwrite: bool) -> tuple[int, dict]:
    """安装尾巴：复制已校验的插件目录到用户插件目录（目录/zip 安装共用）。"""
    import shutil

    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager()
    user_dir = sm.get_ops_user_plugins_dir()
    user_dir.mkdir(parents=True, exist_ok=True)
    dest = (user_dir / manifest.id).resolve()
    # 禁止安装到自身
    if dest == src.resolve():
        return 200, {
            "ok": True,
            "message": "插件已在用户目录中",
            "dest": str(dest),
            "plugins": _plugins_list(scan_always=True),
        }
    try:
        dest.relative_to(user_dir.resolve())
    except ValueError:
        return 400, {"ok": False, "error": "目标目录非法"}
    if dest.exists():
        if not overwrite:
            return 409, {
                "ok": False,
                "error": f"目标已存在: {dest.name}，可传 overwrite=true 覆盖",
                "dest": str(dest),
            }
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    # 确保 sh 可执行
    for sh in dest.rglob("*.sh"):
        try:
            sh.chmod(sh.stat().st_mode | 0o111)
        except OSError:
            pass
    # v2.1：记录安装/更新时间（列表排序用）
    import datetime as _dt

    sm.ops.installed_at[manifest.id] = _dt.datetime.now().isoformat(timespec="seconds")
    sm.save()
    return 200, {
        "ok": True,
        "message": f"已安装到 {dest}",
        "dest": str(dest),
        "plugins": _plugins_list(scan_always=True),
    }


def _install_plugin_path(body: dict) -> tuple[int, dict]:
    """校验通过后复制到用户插件目录。"""
    from zentray.plugins.manifest import validate_plugin_dir

    path, err = _safe_plugin_path(body.get("path") or "")
    if err:
        return 400, {"ok": False, "error": err}
    result = validate_plugin_dir(path)
    if not result.ok or result.manifest is None:
        return 400, {
            "ok": False,
            "error": "校验未通过",
            "errors": list(result.errors),
        }
    return _install_validated_dir(path, result.manifest, bool(body.get("overwrite")))


def _extract_plugin_zip(body: dict) -> tuple[Optional[Path], Optional[Path], Optional[dict]]:
    """安全解压 zip 到临时目录并定位 plugin.yaml 根。

    返回 (tmp_base, root_dir, err)：成功 err=None（调用方须 finally 清理
    tmp_base）；失败 err 为 400 语义错误体（root_dir=None）。
    zip-slip 防护：拒绝对路径/..，resolve 后必须在解压目录内。
    """
    import shutil
    import time
    import zipfile

    from zentray.config import DATA_DIR

    raw = body.get("path") or ""
    if not str(raw).strip():
        return None, None, {"ok": False, "error": "path 必填"}
    zp = Path(str(raw).strip()).expanduser().resolve()
    if not zp.is_file():
        return None, None, {"ok": False, "error": f"文件不存在: {zp}"}
    if zp.suffix.lower() != ".zip":
        return None, None, {"ok": False, "error": "仅支持 .zip 包"}
    if not _path_in_allowed_roots(zp):
        return (
            None,
            None,
            {
                "ok": False,
                "error": "路径不在允许范围内（用户主目录 / 数据目录 / 项目或内置插件目录）",
            },
        )

    tmp_base = (DATA_DIR / "tmp" / f"plugin_install_{zp.stem}_{int(time.time() * 1000)}").resolve()
    tmp_base.mkdir(parents=True, exist_ok=True)
    # 逐成员解压 + zip-slip 防护
    with zipfile.ZipFile(zp) as zf:
        for member in zf.infolist():
            if member.filename.startswith(("/", "\\")) or ".." in Path(member.filename).parts:
                return None, None, {"ok": False, "error": f"非法 zip 成员: {member.filename}"}
            dest = (tmp_base / member.filename).resolve()
            try:
                dest.relative_to(tmp_base)
            except ValueError:
                return None, None, {"ok": False, "error": f"非法 zip 成员: {member.filename}"}
            if member.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                # 恢复可执行位（open("wb") 按默认 umask 落盘，丢了 +x）
                if (member.external_attr >> 16) & 0o111:
                    try:
                        dest.chmod(dest.stat().st_mode | 0o111)
                    except OSError:
                        pass

    # 定位 plugin.yaml：根目录或唯一一级子目录
    root_dir = tmp_base
    if not (root_dir / "plugin.yaml").is_file():
        subs = [d for d in tmp_base.iterdir() if d.is_dir() and (d / "plugin.yaml").is_file()]
        if len(subs) == 1:
            root_dir = subs[0]
        else:
            return (
                None,
                None,
                {
                    "ok": False,
                    "error": "zip 中未找到 plugin.yaml（根目录或唯一一级子目录）",
                },
            )
    return tmp_base, root_dir, None


def _preview_plugin_zip(body: dict) -> tuple[int, dict]:
    """zip 预览校验：解压临时目录 → manifest 校验 → 清理，不安装。"""
    import shutil

    from zentray.plugins.manifest import validate_plugin_dir

    tmp_base, root_dir, err = _extract_plugin_zip(body)
    if err is not None:
        return 400, {"ok": False, "errors": [err.get("error", "")], "preview": None}
    try:
        result = validate_plugin_dir(root_dir)
        preview = None
        if result.manifest is not None:
            preview = _manifest_preview(result.manifest)
        return 200, {
            "ok": result.ok,
            "errors": list(result.errors),
            "preview": preview,
            "path": str(body.get("path") or ""),
        }
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


def _install_plugin_zip(body: dict) -> tuple[int, dict]:
    """zip 包安装：解压临时目录（防 zip-slip）→ manifest 校验 → 落用户插件目录。"""
    import shutil

    from zentray.plugins.manifest import validate_plugin_dir

    tmp_base, root_dir, err = _extract_plugin_zip(body)
    if err is not None:
        return 400, err
    try:
        result = validate_plugin_dir(root_dir)
        if not result.ok or result.manifest is None:
            return 400, {
                "ok": False,
                "error": "校验未通过",
                "errors": list(result.errors),
            }
        return _install_validated_dir(root_dir, result.manifest, bool(body.get("overwrite")))
    finally:
        shutil.rmtree(tmp_base, ignore_errors=True)


def _plugin_runs(query: dict) -> tuple[int, dict]:
    """运行历史：ops_runs/*.json 时间戳倒序（无索引，目录扫描够用）。"""
    from zentray.config import DATA_DIR

    try:
        limit = max(1, min(200, int(query.get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    runs_dir = DATA_DIR / "ops_runs"
    items = []
    if runs_dir.is_dir():
        for p in sorted(runs_dir.glob("*.json"), reverse=True):
            if p.name == "last.json":
                continue
            if len(items) >= limit:
                break
            try:
                items.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                continue
    return 200, {"items": items, "count": len(items)}


def _plugin_run_log(query: dict) -> tuple[int, dict]:
    """读取单次运行日志（文件名白名单：无路径分隔符 + 必须在 ops_runs 内）。"""
    from zentray.config import DATA_DIR

    name = str(query.get("file") or "").strip()
    if not name or "/" in name or "\\" in name or Path(name).name != name:
        return 400, {"error": "非法文件名"}
    runs_dir = (DATA_DIR / "ops_runs").resolve()
    path = (runs_dir / name).resolve()
    if path.parent != runs_dir or not path.is_file():
        return 404, {"error": "日志不存在"}
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return 500, {"error": f"读取失败: {e}"}
    return 200, {
        "file": name,
        "content": content[:200_000],
        "truncated": len(content) > 200_000,
    }


def _build_run_md(report: dict, log_text: str) -> str:
    """单次运行报告 markdown（报告按钮落盘、系统阅读器打开的文件）。"""
    r = report or {}
    dur = ""
    try:
        import datetime as _dt

        sec = (
            _dt.datetime.fromisoformat(r["time"]) - _dt.datetime.fromisoformat(r["started_at"])
        ).total_seconds()
        if sec >= 0:
            dur = f"{sec:.0f} 秒" if sec < 60 else f"{int(sec // 60)} 分 {sec % 60:.0f} 秒"
    except Exception:
        pass
    lines = [
        f"# 执行报告 · {r.get('name') or r.get('id') or ''}",
        "",
        f"- 运行ID: `{r.get('run_id', '')}`",
        f"- 状态: {'✅ 成功' if r.get('ok') else '❌ 失败'}",
        f"- 触发: {r.get('trigger') or '—'}",
        f"- 开始: {r.get('started_at') or '—'}",
        f"- 结束: {r.get('time') or '—'}",
    ]
    if dur:
        lines.append(f"- 耗时: {dur}")
    if r.get("task_id"):
        lines.append(f"- 关联任务: `{r['task_id']}`")
    lines += ["", "## 摘要", "", str(r.get("summary") or "（无）")]
    if r.get("result_text"):
        lines += ["", "## 结果正文", "", str(r["result_text"])]
    lines += ["", "## 完整日志", "", "```log", log_text or "（空日志）", "```", ""]
    return "\n".join(lines)


def _open_with_system(path: Path) -> None:
    """系统默认应用打开文件（win shell / mac open / linux xdg-open）。"""
    import os
    import subprocess
    import sys

    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        logger.exception("系统打开失败: %s", path)


def _attachment_open(body: dict) -> tuple[int, dict]:
    """任务附件/链接打开：URL 走系统浏览器，本地路径走系统默认应用。"""
    import webbrowser

    value = str(body.get("value") or "").strip()
    if not value:
        return 400, {"error": "value 必填"}
    if "://" in value:
        if not webbrowser.open(value):
            return 500, {"error": "打开链接失败"}
        return 200, {"ok": True}
    path = Path(value).expanduser()
    if not path.is_file():
        return 404, {"error": "文件不存在"}
    _open_with_system(path)
    return 200, {"ok": True}


_THUMB_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico"}


def serve_attachment_thumb(query: dict) -> tuple[int, str, bytes]:
    """本地图片字节（任务详情缩略图直用）。仅放行图片后缀，防变任意文件读取。"""
    import mimetypes

    p = Path(str(query.get("path") or "")).expanduser()
    if p.suffix.lower() not in _THUMB_EXTS or not p.is_file():
        return 404, "text/plain; charset=utf-8", b"not found"
    ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
    return 200, ctype, p.read_bytes()


def _plugin_run_open(body: dict) -> tuple[int, dict]:
    """生成运行报告 md 并用系统默认应用打开（run_id 白名单同日志端点）。"""
    from zentray.config import DATA_DIR

    run_id = str(body.get("run_id") or "").strip()
    if not run_id or "/" in run_id or "\\" in run_id or Path(run_id).name != run_id:
        return 400, {"error": "非法运行ID"}
    runs_dir = (DATA_DIR / "ops_runs").resolve()
    meta = (runs_dir / f"{run_id}.json").resolve()
    if meta.parent != runs_dir or not meta.is_file():
        return 404, {"error": "运行记录不存在"}
    try:
        report = json.loads(meta.read_text(encoding="utf-8"))
    except Exception:
        return 500, {"error": "运行记录读取失败"}
    # 结果正文带 .html 报告路径（如 AI 资讯日报）→ 直接用系统浏览器打开
    import re

    m = re.search(r"[\w./\\~-]+\.html\b", str(report.get("result_text") or ""))
    if m:
        html_path = Path(m.group(0))
        if html_path.is_file():
            _open_with_system(html_path)
            _ctx.mark_report_viewed(f"run:{run_id}")
            return 200, {"ok": True, "file": str(html_path)}
    log_text = ""
    log_path = runs_dir / f"{run_id}.log"
    if log_path.is_file():
        log_text = log_path.read_text(encoding="utf-8", errors="replace")[:200_000]
    md_path = runs_dir / f"{run_id}.md"
    try:
        md_path.write_text(_build_run_md(report, log_text), encoding="utf-8")
    except OSError as e:
        return 500, {"error": f"报告写入失败: {e}"}
    _open_with_system(md_path)
    _ctx.mark_report_viewed(f"run:{run_id}")
    return 200, {"ok": True, "file": str(md_path)}


def _authorize_plugin(plugin_id: str, body: dict) -> tuple[int, dict]:
    """设置插件自动运行授权（插件级一次性授权的 UI 开关）。"""
    from zentray.plugins import triggers

    allow = bool(body.get("allow"))
    triggers.authorize(plugin_id, allow)
    return 200, {"ok": True, "id": plugin_id, "authorized": allow}


def _run_plugin(plugin_id: str, body: dict) -> tuple[int, dict]:
    """运行 script 插件（异步）；service 可传 action=start|stop|status。"""
    from zentray.plugins.models import PluginType
    from zentray.services.settings_manager import SettingsManager

    if not SettingsManager().ops.enabled:
        return 400, {"error": "插件功能未启用"}
    loader = _ctx.plugin_loader
    runtime = _ctx.plugin_runtime
    if not loader or not runtime:
        return 503, {"error": "插件运行时未就绪"}
    plug = loader.get(plugin_id)
    if not plug:
        return 404, {"error": f"插件不存在或未加载: {plugin_id}"}

    pomo = _ctx.pomodoro_service
    pomo_active = bool(pomo and getattr(pomo, "is_active", False))

    action = (body.get("action") or "run").strip().lower()
    if plug.manifest.type == PluginType.SERVICE:
        if action not in ("start", "stop", "status"):
            action = "status"
        ok, detail = runtime.service_cmd(plug, action, pomodoro_active=pomo_active)
        return 200, {"ok": ok, "id": plugin_id, "action": action, "detail": detail}

    # script
    if runtime.is_busy:
        return 409, {"error": "已有脚本在运行"}
    if pomo_active:
        return 409, {"error": "番茄钟进行中，无法运行脚本"}
    task = None
    task_id = str(body.get("task_id") or "").strip()
    if task_id:
        task = _ctx.task_service.find_task(task_id)
        if task is None:
            return 404, {"error": f"任务不存在: {task_id}"}
    # 命名入参：显式传入 > 预设 > default（body.params {name: value| [values]}）
    param_values = None
    m_params = plug.manifest.params
    if m_params:
        raw_params = body.get("params")
        if raw_params is not None and not isinstance(raw_params, dict):
            return 400, {"error": "params 必须是对象"}
        # 多值（列表）仅允许出现在 variadic 参数上，且元素必须全为字符串
        variadic_names = {x.name for x in m_params if x.variadic}
        for k, v in (raw_params or {}).items():
            if isinstance(v, list) and (
                k not in variadic_names or not all(isinstance(x, str) for x in v)
            ):
                return 400, {"error": f"参数 {k} 不支持该多值"}
        from zentray.plugins.models import resolve_param_values

        try:
            presets = SettingsManager().ops.param_presets.get(plug.manifest.id)
        except Exception:
            presets = None
        param_values = resolve_param_values(m_params, presets, raw_params)
    started = runtime.run_script(plug, pomodoro_active=False, task=task, param_values=param_values)
    if not started:
        return 409, {"error": "无法启动脚本"}
    return 200, {"ok": True, "id": plugin_id, "started": True}


def _pomodoro_start(body: dict) -> tuple[int, dict]:
    """任务列表 🍅 按钮：以任务为对象开始专注（经信号回主线程启动）。"""
    svc = _ctx.pomodoro_service
    if svc is None:
        return 500, {"error": "pomodoro service unavailable"}
    if bool(getattr(svc, "is_active", False)):
        return 409, {"error": "番茄钟循环进行中"}
    runtime = _ctx.plugin_runtime
    if runtime is not None and bool(getattr(runtime, "is_busy", False)):
        return 409, {"error": "脚本运行中，请稍后再开始专注"}
    task_id = str(body.get("task_id") or "")
    if task_id:
        task = _ctx.task_service.find_task(task_id) if _ctx.task_service else None
        if task is None:
            return 404, {"error": "任务不存在"}
    _ctx.start_pomodoro(task_id)
    return 200, {"ok": True, "task_id": task_id}


def _glance_state() -> tuple[int, dict]:
    """速览面板复合状态：轮播槽任务 + 活跃序 + 番茄态 + 待看报告 + 脚本占用。"""
    ts = _ctx.task_service
    item = None
    if ts is not None:
        task = ts.get_current_task()
        if task is not None:
            d = _task_dict(task)
            subs = d.get("subtasks") or []
            item = {
                "id": d.get("id"),
                "title": d.get("title") or "",
                "display_title": ts.get_task_display_title(task) or d.get("title") or "",
                "category": d.get("category") or "",
                "priority": d.get("priority") or "medium",
                "deadline": d.get("deadline"),
                "subs_done": sum(1 for s in subs if s.get("status") == "done"),
                "subs_total": len(subs),
            }
    active_ids = [t.id for t in ts.get_all_tasks()] if ts is not None else []

    svc = _ctx.pomodoro_service
    pomo: dict = {"phase": "idle", "task_title": ""}
    if svc is not None and bool(getattr(svc, "is_active", False)):
        pomo = {
            "phase": getattr(svc, "phase", "focus"),
            "remaining": int(svc.get_remaining() or 0),
            "task_title": getattr(svc, "task_title", "") or "",
        }
    try:
        from zentray.services.activity_log import pomodoro_today_stats

        pomo["today_count"], pomo["today_minutes"] = pomodoro_today_stats()
    except Exception:
        pomo["today_count"], pomo["today_minutes"] = 0, 0

    reports = []
    rot = _ctx.report_rotation
    if rot is not None:
        try:
            reports = [
                {"key": r.get("key") or "", "text": r.get("text") or ""} for r in rot.active()
            ]
        except Exception:
            logger.exception("速览面板读取报告轮播失败")
    runtime = _ctx.plugin_runtime
    return 200, {
        "item": item,
        "active_ids": active_ids,
        "pomodoro": pomo,
        "reports": reports,
        "ops_busy": bool(runtime is not None and getattr(runtime, "is_busy", False)),
    }


def _glance_report_open(body: dict) -> tuple[int, dict]:
    """速览面板报告 chip：点开即消（run:→运行报告，ai:→本地报告文件）。"""
    key = str(body.get("key") or "")
    if not key:
        return 400, {"error": "key 必填"}
    _ctx.mark_report_viewed(key)
    if key.startswith("run:"):
        run_id = key[4:]
        if not run_id or "/" in run_id or "\\" in run_id or Path(run_id).name != run_id:
            return 400, {"error": "非法运行ID"}
        return _plugin_run_open({"run_id": run_id})
    if key.startswith("ai:"):
        from zentray.config import DATA_DIR

        try:
            path = Path(key[3:]).resolve()
            path.relative_to(Path(DATA_DIR).resolve())
        except (ValueError, OSError):
            return 400, {"error": "非法报告路径"}
        if not path.is_file():
            return 404, {"error": "报告文件不存在"}
        _open_with_system(path)
        return 200, {"ok": True, "file": str(path)}
    return 400, {"error": "无法识别的报告 key"}


def _pomodoro_control(body: dict) -> tuple[int, dict]:
    """速览面板番茄控制：stop / extend / skip_break（经信号回主线程执行）。"""
    action = str(body.get("action") or "").strip()
    if action not in ("stop", "extend", "skip_break"):
        return 400, {"error": "action 必须是 stop|extend|skip_break"}
    svc = _ctx.pomodoro_service
    if svc is None or not bool(getattr(svc, "is_active", False)):
        return 409, {"error": "番茄钟未在运行"}
    if action == "skip_break" and not bool(getattr(svc, "is_break", False)):
        return 409, {"error": "当前不在休息段"}
    if action == "extend" and bool(getattr(svc, "is_break", False)):
        return 409, {"error": "休息段不能延长"}
    if _ctx.pomodoro_control is None:
        return 500, {"error": "pomodoro control unavailable"}
    _ctx.pomodoro_control(action)
    return 200, {"ok": True, "action": action}


def _save_settings(data: dict) -> None:
    """写回 settings.json，复用 SettingsManager 的字段结构。"""
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager()
    # 用内部 _apply_dict + save，与设置对话框保存路径一致
    sm._apply_dict(data)
    sm.save()
    # 同步 Qt 应用主题（宿主窗口）
    try:
        from zentray.ui.theme import apply_app_theme

        apply_app_theme()
    except Exception:
        pass


def _archived_list(query: dict) -> tuple[int, dict]:
    """归档任务列表（历史视图）：解析 archive/*.log，支持状态/分类/天数筛选。"""
    try:
        days = int(query.get("days") or 90)
    except (TypeError, ValueError):
        days = 90
    status = (query.get("status") or "all").strip() or "all"
    category = (query.get("category") or "").strip()
    items = _ctx.task_service.list_archived(
        status=None if status == "all" else status,
        category=category or None,
        days=days,
    )
    return 200, {"items": items}


def _history_list(query: dict) -> tuple[int, dict]:
    from zentray.services.activity_log import list_ai_reports, query_events

    try:
        days = int(query.get("days") or 30)
    except (TypeError, ValueError):
        days = 30
    category = (query.get("category") or "all").strip() or "all"
    events = query_events(category=None if category == "all" else category, days=days)
    reports = list_ai_reports(days=max(days, 90))
    return 200, {
        "events": events,
        "ai_reports": reports,
        "days": days,
        "category": category,
    }


def _history_ai_content(name: str) -> tuple[int, dict]:
    from zentray.services.activity_log import read_ai_report

    content = read_ai_report(name)
    if content is None:
        return 404, {"error": "report not found"}
    return 200, {"name": name, "content": content}


def _add_secondary_category(body: dict) -> tuple[int, dict]:
    """在指定一级下添加二级分类（名称去重）。"""
    from zentray.services.settings_manager import SettingsManager

    primary_id = body.get("primary_id")
    name = (body.get("name") or "").strip()
    if not primary_id or not name:
        return 400, {"error": "primary_id 与 name 必填"}

    sm = SettingsManager()
    cats = sm.categories
    primary = cats.find_primary(primary_id) if hasattr(cats, "find_primary") else None
    if primary is None:
        for p in cats.primary_list:
            if p.id == primary_id:
                primary = p
                break
    if primary is None:
        return 404, {"error": "一级分类不存在"}

    sec = primary.add_secondary(name)
    sm.save()
    return 200, {
        "secondary": sec.to_dict(),
        "categories": sm.categories.to_dict(),
    }


def _system_status() -> tuple[int, dict]:
    from zentray.config import DATA_DIR, VERSION
    from zentray.services import autostart as autostart_svc
    from zentray.services import data_migration as mig
    from zentray.services.settings_manager import SettingsManager
    from zentray.workers.ai_schedule import load_state

    st = autostart_svc.status()
    sm = SettingsManager()
    pref = bool(sm.appearance.autostart)
    backup_dir = mig.backup_dir_from_settings()
    # Windows 任务栏标签可见性（§3.0 合并模式检测）；非 Windows 为 None
    label_visible = None
    try:
        from zentray.ui.win_tray import taskbar_label_visible

        label_visible = taskbar_label_visible()
    except Exception:
        pass
    return 200, {
        "version": VERSION,
        "data_dir": str(DATA_DIR),
        "autostart": {
            **st,
            "preference": pref,
        },
        "windows": {
            "taskbar_label_visible": label_visible,
        },
        "include_options": mig.list_include_options(),
        "exports_dir": str(mig.exports_dir()),
        "backup": {
            **asdict(sm.backup),
            "default_dir": str(mig.exports_dir()),
            "dir": str(backup_dir),
            "custom": bool((sm.backup.dir or "").strip()),
            "last_backup_at": load_state().last_backup_at,
        },
    }


def _system_set_autostart(body: dict) -> tuple[int, dict]:
    from zentray.services import autostart as autostart_svc
    from zentray.services.settings_manager import SettingsManager

    if "enabled" not in body:
        return 400, {"error": "enabled 必填"}
    enabled = bool(body.get("enabled"))
    ok, message = autostart_svc.set_enabled(enabled)
    if not ok:
        return 500, {"ok": False, "error": message, "enabled": autostart_svc.is_enabled()}

    sm = SettingsManager()
    sm.appearance.autostart = enabled
    sm.save()
    return 200, {
        "ok": True,
        "message": message,
        "enabled": autostart_svc.is_enabled(),
        "preference": enabled,
    }


def _open_taskbar_settings() -> tuple[int, dict]:
    """打开 Windows 任务栏设置页（合并模式引导，设计 §3.0）。"""
    import sys

    if not sys.platform.startswith("win32"):
        return 400, {"ok": False, "error": "仅 Windows 支持"}
    try:
        import os

        os.startfile("ms-settings:taskbar")  # noqa: S606 固定白名单 URI
        return 200, {"ok": True}
    except Exception as e:
        return 500, {"ok": False, "error": f"打开失败: {e}"}


def _system_export(body: dict) -> tuple[int, dict]:
    from zentray.services import data_migration as mig

    include = body.get("include")
    password = (body.get("password") or "").strip() or None
    dest_path = (body.get("dest_path") or "").strip() or None
    out_path = None
    if dest_path:
        if not dest_path.lower().endswith(".zip"):
            return 400, {"error": "另存为文件必须以 .zip 结尾"}
        out_path = dest_path
    result = mig.create_export_zip(
        include,
        out_path=out_path,
        password=password,
        out_dir=None if out_path else mig.backup_dir_from_settings(),
    )
    code = 200 if result.ok else 500
    return code, result.to_dict()


def _system_import(body: dict) -> tuple[int, dict]:
    from zentray.services import data_migration as mig
    from zentray.services.settings_manager import SettingsManager

    path = (body.get("path") or "").strip()
    if not path:
        return 400, {"error": "path 必填（本机 zip 绝对路径）"}
    include = body.get("include")
    make_safety = body.get("safety_backup", True)
    if isinstance(make_safety, str):
        make_safety = make_safety.lower() not in ("0", "false", "no")
    result = mig.import_replace(
        path,
        include,
        make_safety_backup=bool(make_safety),
        password=(body.get("password") or "").strip() or None,
    )
    if result.ok:
        try:
            SettingsManager().reload()
        except Exception:
            logger.exception("导入后 reload settings 失败")
        try:
            _ctx.apply_settings()
            _ctx.on_changed()
        except Exception:
            logger.exception("导入后 apply_settings 失败")
        return 200, result.to_dict()
    return 400, result.to_dict()


def _system_import_preview(body: dict) -> tuple[int, dict]:
    """选择性恢复预览：包内各类/子类计数（只读）。"""
    from zentray.services import data_migration as mig

    path = (body.get("path") or "").strip()
    if not path:
        return 400, {"error": "path 必填（本机 zip 绝对路径）"}
    result = mig.preview_import(path, password=(body.get("password") or "").strip() or None)
    code = 200 if result.get("ok") else 400
    return code, result


def _system_archive_pack() -> tuple[int, dict]:
    from zentray.services import data_migration as mig

    result = mig.pack_archive()
    code = 200 if result.ok else 500
    return code, result.to_dict()


def _system_backups() -> tuple[int, dict]:
    from zentray.services import data_migration as mig

    return 200, {"items": mig.list_backups(), "dir": str(mig.backup_dir_from_settings())}


def _ics_escape(text: str) -> str:
    """RFC 5545 TEXT 转义：反斜杠/分号/逗号，换行拼为 \\n。"""
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\n")
        .replace("\n", "\\n")
    )


def _build_tasks_ics(tasks) -> str:
    """活跃任务 → VCALENDAR 文本（截止日=全天事件；提醒开启时以提醒时间起 30 分钟）。

    纯函数便于单测；CRLF 为 ics 规范行尾。
    """
    import datetime as _dt

    priority_tag = {"high": "🔴", "medium": "", "low": "⬇"}
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//ZenTray//Task Export//CN",
        "CALSCALE:GREGORIAN",
    ]
    now = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    for t in tasks:
        deadline = getattr(t, "deadline", None)
        rem = getattr(t, "reminder", None)
        rem_time = None
        if rem is not None and getattr(rem, "enabled", False):
            rem_time = getattr(rem, "time_of_day", None) or "17:00"
        if not deadline and not rem_time:
            continue
        title = f"{priority_tag.get(getattr(t, 'priority', ''), '')}{t.title}".strip()
        desc = _ics_escape(f"分类: {t.category or '未分类'}\n{getattr(t, 'details', '') or ''}")
        if deadline:
            try:
                _dt.date.fromisoformat(str(deadline))
            except ValueError:
                deadline = None
        if deadline and rem_time:
            start = f"{str(deadline).replace('-', '')}T{rem_time.replace(':', '')}00"
            end_t = (
                _dt.datetime.combine(
                    _dt.date.fromisoformat(str(deadline)),
                    _dt.time.fromisoformat(rem_time),
                )
                + _dt.timedelta(minutes=30)
            ).strftime("%Y%m%dT%H%M%S")
        elif deadline:
            start = str(deadline).replace("-", "")
            end_t = None
        elif rem_time:
            # 无截止日但开了提醒：今天起 30 分钟事件
            today = _dt.date.today()
            start = (_dt.datetime.combine(today, _dt.time.fromisoformat(rem_time))).strftime(
                "%Y%m%dT%H%M%S"
            )
            end_t = (
                _dt.datetime.combine(today, _dt.time.fromisoformat(rem_time))
                + _dt.timedelta(minutes=30)
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
            f"SUMMARY:{_ics_escape(title)}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def _system_calendar_export() -> tuple[int, dict]:
    """活跃任务导出 .ics 并用系统默认日历应用打开（导入后落系统日历）。"""
    import tempfile
    from pathlib import Path

    tasks = _ctx.task_service.get_all_tasks()
    ics = _build_tasks_ics(tasks)
    count = ics.count("BEGIN:VEVENT")
    if count == 0:
        return 400, {"error": "没有带截止日期或提醒的任务可导出"}
    out = Path(tempfile.gettempdir()) / "zentray-tasks.ics"
    out.write_text(ics, encoding="utf-8")
    _open_with_system(out)
    return 200, {"ok": True, "count": count, "file": str(out)}


def _system_backup_delete(body: dict) -> tuple[int, dict]:
    from zentray.services import data_migration as mig

    path = (body.get("path") or "").strip()
    if not path:
        return 400, {"error": "path 必填"}
    result = mig.delete_backup(path)
    code = 200 if result.ok else 400
    return code, result.to_dict()


def _complete_setup(form: dict) -> None:
    """对应 setup_wizard：写 .env 片段 + .setup_done，并合并进 settings。"""
    from zentray.config import DATA_DIR
    from zentray.services.settings_manager import SettingsManager

    lines = []
    if form.get("wx_token"):
        lines.append(f"WXPUSHER_APP_TOKEN={form['wx_token'].strip()}")
    if form.get("wx_uid"):
        lines.append(f"WXPUSHER_UID={form['wx_uid'].strip()}")
    if form.get("ai_key"):
        lines.append(f"AI_API_KEY={form['ai_key'].strip()}")
    if form.get("ai_base"):
        lines.append(f"AI_API_BASE_URL={form['ai_base'].strip()}")
    if form.get("ai_model"):
        lines.append(f"AI_MODEL_NAME={form['ai_model'].strip()}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if lines:
        env_path = DATA_DIR / ".env"
        existing = ""
        if env_path.exists():
            existing = env_path.read_text(encoding="utf-8")
        # 追加写入（简单合并）
        block = "\n".join(lines) + "\n"
        with open(env_path, "a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write(block)

    # 同步到 settings.json 结构
    sm = SettingsManager()
    patch = {}
    if form.get("wx_token") or form.get("wx_uid"):
        patch["notification"] = {
            "enabled": True,
            "wxpusher_app_token": (form.get("wx_token") or "").strip()
            or sm.notification.wxpusher_app_token,
            "wxpusher_uid": (form.get("wx_uid") or "").strip() or sm.notification.wxpusher_uid,
        }
    if form.get("ai_key") or form.get("ai_base") or form.get("ai_model"):
        patch["ai"] = {
            "enabled": True,
            "api_key": (form.get("ai_key") or "").strip() or sm.ai.api_key,
            "base_url": (form.get("ai_base") or "").strip() or sm.ai.base_url,
            "model": (form.get("ai_model") or "").strip() or sm.ai.model,
            "active_style_id": sm.ai.active_style_id,
            "styles": [s.to_dict() for s in sm.ai.styles],
        }
    if patch:
        sm._apply_dict(patch)
        sm.save()

    marker = DATA_DIR / ".setup_done"
    marker.write_text("ok\n", encoding="utf-8")
