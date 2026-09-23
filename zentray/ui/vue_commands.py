# zentray/ui/vue_commands.py
"""
托盘菜单 / 系统入口 → Vue 页面（逻辑与 commands.py 一致，仅 UI 换成 Vue+Arco）。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from zentray.ui.web_host import open_vue_route, use_vue_ui

if TYPE_CHECKING:
    from zentray.ui.controller import TrayController

logger = logging.getLogger(__name__)


def try_vue_new_task(controller: "TrayController") -> bool:
    if not use_vue_ui():
        return False
    ok, _ = open_vue_route("/tasks/new", title="新建任务", width=880, height=540)
    if ok:
        controller.update_display()
    return True


def try_vue_edit_task(controller: "TrayController", task) -> bool:
    if not use_vue_ui() or not task:
        return False
    ok, _ = open_vue_route(
        f"/tasks/{task.id}/edit",
        title="修改任务",
        width=880,
        height=540,
    )
    if ok:
        controller.update_display()
    return True


def try_vue_task_list(controller: "TrayController", select_id: str = None) -> bool:
    """任务列表（任务中枢）。select_id 用于外部入口（如提醒）直达选中某任务。"""
    if not use_vue_ui():
        return False
    query = {"select": select_id} if select_id else None
    ok, _ = open_vue_route("/tasks", title="任务列表", width=960, height=600, query=query)
    if ok:
        controller.update_display()
    return True


def try_vue_settings(controller: "TrayController") -> bool:
    if not use_vue_ui():
        return False
    ok, payload = open_vue_route("/settings", title="设置", width=920, height=600)
    if ok and isinstance(payload, dict) and not payload.get("cancelled"):
        controller.apply_settings()
        controller.update_display()
    return True


def try_vue_history(controller: "TrayController") -> bool:
    if not use_vue_ui():
        return False
    open_vue_route("/history", title="历史记录", width=980, height=660)
    return True


def try_vue_reminders(batch) -> tuple[bool, Optional[dict]]:
    """
    打开聚合提醒窗（一窗多卡，卡片式）。
    batch: [(task, fire_key), ...]；逐卡动作由前端直调 POST /reminder-action，
    窗口关闭（payload=None，含 X 关闭）由 main 侧对未处理卡统一 dismiss。

    返回 (handled_by_vue, payload)。高度按卡数自适应：120 + n*170，上限 640。
    """
    if not use_vue_ui() or not batch:
        return False, None
    n = len(batch)
    height = max(240, min(120 + n * 170, 640))
    ok, payload = open_vue_route(
        "/reminder",
        query={
            "ids": ",".join(t.id for t, _ in batch),
            "keys": ",".join(k or "" for _, k in batch),
        },
        title="任务提醒",
        width=440,
        height=height,
        stay_on_top=True,
    )
    if not ok or not isinstance(payload, dict):
        return True, None
    return True, payload


def try_vue_quick_add(controller: "TrayController") -> bool:
    """闪电添加（无边框浮层）。"""
    if not use_vue_ui():
        return False
    ok, payload = open_vue_route(
        "/quick-add",
        title="闪电添加",
        width=640,
        height=96,
        frameless=True,
        stay_on_top=True,
        transparent=True,
        modal=True,
    )
    if ok and isinstance(payload, dict) and payload.get("action") == "added":
        controller.reload_data()
    return True


def try_vue_setup_wizard() -> bool:
    """首次配置向导。返回 True 表示已由 Vue 处理（无论完成或取消）。"""
    if not use_vue_ui():
        return False
    open_vue_route(
        "/setup",
        title="欢迎使用 ZenTray — 初始配置",
        width=680,
        height=480,
    )
    return True
