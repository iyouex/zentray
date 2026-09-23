# zentray/ui/commands.py
"""
命令模式 —— 将托盘菜单事件路由从 if-elif 链替换为独立命令对象。

每个菜单项对应一个 ActionCommand 子类，在 TrayController 中
通过命令映射字典进行路由，支持后续动态注册扩展命令。
"""
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from zentray.ui.dialog_utils import run_modal_loop

if TYPE_CHECKING:
    from .controller import TrayController


class ActionCommand(ABC):
    """命令基类"""

    @abstractmethod
    def execute(self, controller: "TrayController") -> None:
        """执行命令"""
        pass


# ==========================================
# 核心命令
# ==========================================

class NewTaskCommand(ActionCommand):
    """新建任务"""

    def execute(self, controller: "TrayController") -> None:
        from zentray.ui.vue_commands import try_vue_new_task

        if try_vue_new_task(controller):
            return
        from zentray.ui.dialogs import TaskDialog

        dialog = TaskDialog()
        if run_modal_loop(dialog):
            data = dialog.get_data()
            controller.task_service.create_task(data)
            controller.update_display()


class DoneCommand(ActionCommand):
    """完成当前任务"""

    def execute(self, controller: "TrayController") -> None:
        task = controller.task_service.get_current_task()
        if task:
            controller.task_service.mark_done(task.id)
            controller.update_display()


class AbandonCommand(ActionCommand):
    """废弃当前任务"""

    def execute(self, controller: "TrayController") -> None:
        task = controller.task_service.get_current_task()
        if task:
            controller.task_service.abandon(task.id)
            controller.update_display()


class TaskListCommand(ActionCommand):
    """打开任务列表面板（左列表 + 右操作）"""

    def execute(self, controller: "TrayController") -> None:
        from zentray.ui.vue_commands import try_vue_task_list

        if try_vue_task_list(controller):
            return
        from zentray.ui.task_list_dialog import TaskListDialog

        dialog = TaskListDialog(controller.task_service)
        if not run_modal_loop(dialog):
            return
        result = dialog.get_selected_action()
        if not result:
            return
        action, task_id = result
        task = controller.task_service.find_task(task_id)
        if not task:
            controller.update_display()
            return
        _dispatch_task_action(action, task, controller)


class EditCommand(ActionCommand):
    """编辑当前任务（一次性或周期实例，均可完整编辑）"""

    def execute(self, controller: "TrayController") -> None:
        task = controller.task_service.get_current_task()
        if not task:
            return
        fresh = controller.task_service.find_task(task.id) or task
        from zentray.ui.vue_commands import try_vue_edit_task

        if try_vue_edit_task(controller, fresh):
            return
        from zentray.ui.dialogs import TaskDialog

        dialog = TaskDialog(task=fresh)
        if run_modal_loop(dialog):
            data = dialog.get_data()
            # 保留实例类型，勿被表单误改成 one-time 丢 template_id
            if getattr(fresh, "task_type", None) == "periodic_instance":
                data["task_type"] = "periodic_instance"
                data["template_id"] = fresh.template_id
            controller.task_service.update_task(task.id, data)
            controller.update_display()


class PomodoroStartCommand(ActionCommand):
    """开始番茄钟"""

    def execute(self, controller: "TrayController") -> None:
        controller.pomodoro_service.start()
        controller.update_display()


class PomodoroStopCommand(ActionCommand):
    """中止番茄钟"""

    def execute(self, controller: "TrayController") -> None:
        controller.pomodoro_service.stop()
        controller.update_display()


class PomodoroExtendCommand(ActionCommand):
    """延长番茄钟"""

    def execute(self, controller: "TrayController") -> None:
        controller.pomodoro_service.extend()
        controller.update_display()


class QuitCommand(ActionCommand):
    """退出程序"""

    def execute(self, controller: "TrayController") -> None:
        controller.app.quit()


class SettingsCommand(ActionCommand):
    """打开设置对话框"""

    def execute(self, controller: "TrayController") -> None:
        from zentray.ui.vue_commands import try_vue_settings

        if try_vue_settings(controller):
            return
        from zentray.ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog()
        if run_modal_loop(dialog):
            # 设置已保存，刷新控制器以应用新设置
            controller.apply_settings()
            controller.update_display()


class HistoryCommand(ActionCommand):
    """历史记录：任务操作日志 + AI 报告"""

    def execute(self, controller: "TrayController") -> None:
        from zentray.ui.vue_commands import try_vue_history

        if try_vue_history(controller):
            return
        from zentray.ui.web_host import use_vue_ui

        if not use_vue_ui():
            controller.renderer.show_notification(
                "历史记录",
                "请构建 Vue 前端（web/dist）后使用历史记录功能。",
            )


class AiReviewNowCommand(ActionCommand):
    """立即执行 AI 复盘（不受「每天一次 / 周末节假日跳过」限制）。"""

    def execute(self, controller: "TrayController") -> None:
        import datetime
        import logging

        from zentray.services.settings_manager import SettingsManager
        from zentray.workers.nightly_job import execute_nightly_review

        log = logging.getLogger(__name__)
        sm = SettingsManager()
        if not sm.is_ai_configured() and not sm.is_notification_configured():
            controller.renderer.show_notification(
                "AI 复盘",
                "请先在设置中配置 AI API Key（建议同时配置 WxPusher 推送）。",
            )
            return

        controller.renderer.show_notification("AI 复盘", "正在生成复盘，请稍候…")
        today = datetime.date.today().isoformat()
        try:
            ok = execute_nightly_review(today, controller.task_service.task_repo)
            if ok:
                controller.renderer.show_notification(
                    "AI 复盘",
                    "复盘已完成。本地 reviews/ 或微信推送请查看结果。",
                )
            else:
                controller.renderer.show_notification(
                    "AI 复盘",
                    "复盘已执行，但推送可能失败；请查看本地 reviews/ 目录。",
                )
        except Exception as e:
            log.exception("立即 AI 复盘失败")
            controller.renderer.show_notification("AI 复盘失败", str(e)[:120])


# ==========================================
# 任务列表命令
# ==========================================

class SelectTaskCommand(ActionCommand):
    """切换到指定任务"""

    def __init__(self, task_id: str):
        self.task_id = task_id

    def execute(self, controller: "TrayController") -> None:
        controller.task_service.select_task(self.task_id)
        controller.update_display()


# ==========================================
# 扩展命令
# ==========================================

class ExtensionCommand(ActionCommand):
    """执行扩展按钮"""

    def __init__(self, ext_class_name: str):
        self.ext_class_name = ext_class_name

    def execute(self, controller: "TrayController") -> None:
        for ext in controller.extensions:
            if ext.__class__.__name__ == self.ext_class_name:
                ext.handle_click()
                break


# ==========================================
# 命令注册与路由
# ==========================================

# 静态命令映射
COMMAND_MAP = {
    "done": DoneCommand(),
    "abandon": AbandonCommand(),
    "task_list": TaskListCommand(),
    "pomodoro": PomodoroStartCommand(),
    "stop_pomodoro": PomodoroStopCommand(),
    "extend_pomodoro": PomodoroExtendCommand(),
    "ai_review_now": AiReviewNowCommand(),
    "history": HistoryCommand(),
    "quit": QuitCommand(),
    "settings": SettingsCommand(),
}


def dispatch(action_id: str, controller: "TrayController") -> bool:
    """
    根据 action_id 分发命令。

    Returns:
        bool: 是否成功分发
    """
    # 1. 检查静态命令
    if action_id in COMMAND_MAP:
        COMMAND_MAP[action_id].execute(controller)
        return True

    # 2. 解析带参数的动态命令
    if action_id.startswith("select_task_"):
        task_id = action_id[len("select_task_"):]
        SelectTaskCommand(task_id).execute(controller)
        return True

    if action_id.startswith("extension_"):
        ext_name = action_id[len("extension_"):]
        ExtensionCommand(ext_name).execute(controller)
        return True

    # 3. 未识别的命令
    return False


# ==========================================
# 内部辅助
# ==========================================

def _dispatch_task_action(action: str, task, controller: "TrayController") -> None:
    """任务操作对话框的结果分发"""
    if action == "done":
        controller.task_service.mark_done(task.id)
    elif action == "abandon":
        controller.task_service.abandon(task.id)
    elif action == "edit":
        from zentray.ui.vue_commands import try_vue_edit_task

        if try_vue_edit_task(controller, task):
            return
        from zentray.ui.dialogs import TaskDialog

        dialog = TaskDialog(task=task)
        if run_modal_loop(dialog):
            data = dialog.get_data()
            if getattr(task, "task_type", None) == "periodic_instance":
                data["task_type"] = "periodic_instance"
                data["template_id"] = task.template_id
            controller.task_service.update_task(task.id, data)
    elif action == "select":
        controller.task_service.select_task(task.id)

    controller.update_display()
