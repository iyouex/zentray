# zentray/api/handlers.py
"""
API 处理函数 —— 仅转调既有服务，不重写业务规则。
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
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
    ):
        self.task_service = task_service
        self.on_changed = on_changed or (lambda: None)
        self.apply_settings = apply_settings or (lambda: None)


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

        if method == "GET" and path == "/api/tasks":
            return 200, {"items": [_task_dict(t) for t in _ctx.task_service.get_all_tasks()]}

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

        if method == "POST" and path.startswith("/api/tasks/") and path.endswith("/progress"):
            tid = path[len("/api/tasks/") : -len("/progress")]
            percent = body.get("percent", 0)
            note = body.get("note", "")
            task = _ctx.task_service.update_progress(tid, percent, note)
            _ctx.on_changed()
            return 200, {"item": _task_dict(task)}

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

        if method == "GET" and path == "/api/current-task":
            t = _ctx.task_service.get_current_task()
            return 200, {"item": _task_dict(t) if t else None}

        if method == "GET" and path == "/api/theme":
            return 200, _theme_payload()

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

        # —— 系统：自启 + 数据迁移 ——
        if method == "GET" and path == "/api/system/status":
            return _system_status()
        if method == "POST" and path == "/api/system/autostart":
            return _system_set_autostart(body or {})
        if method == "POST" and path == "/api/system/export":
            return _system_export(body or {})
        if method == "POST" and path == "/api/system/import":
            return _system_import(body or {})
        if method == "POST" and path == "/api/system/archive/pack":
            return _system_archive_pack()

        return 404, {"error": f"not found: {method} {path}"}
    except Exception as e:
        logger.exception("API error %s %s", method, path)
        return 500, {"error": str(e)}


def _task_sub(method: str, rest: str, body: dict) -> tuple[int, dict]:
    # rest like "id/progress"
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
    }


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


def _theme_payload() -> dict:
    from zentray.services.settings_manager import SettingsManager
    from zentray.ui.theme import resolve_effective_theme

    mode = SettingsManager().appearance.theme
    return {
        "mode": mode,
        "effective": resolve_effective_theme(mode),
    }


def _system_status() -> tuple[int, dict]:
    from zentray.config import DATA_DIR, VERSION
    from zentray.services import autostart as autostart_svc
    from zentray.services import data_migration as mig
    from zentray.services.settings_manager import SettingsManager

    st = autostart_svc.status()
    pref = bool(SettingsManager().appearance.autostart)
    return 200, {
        "version": VERSION,
        "data_dir": str(DATA_DIR),
        "autostart": {
            **st,
            "preference": pref,
        },
        "include_options": mig.list_include_options(),
        "exports_dir": str(mig.exports_dir()),
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


def _system_export(body: dict) -> tuple[int, dict]:
    from zentray.services import data_migration as mig

    include = body.get("include")
    result = mig.create_export_zip(include)
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


def _system_archive_pack() -> tuple[int, dict]:
    from zentray.services import data_migration as mig

    result = mig.pack_archive()
    code = 200 if result.ok else 500
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
            "wxpusher_uid": (form.get("wx_uid") or "").strip()
            or sm.notification.wxpusher_uid,
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
