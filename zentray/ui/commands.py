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


# ==========================================
# 命令注册与路由
# ==========================================

# 静态命令映射
COMMAND_MAP = {
    "task_list": TaskListCommand(),
    "pomodoro": PomodoroStartCommand(),
    "stop_pomodoro": PomodoroStopCommand(),
    "extend_pomodoro": PomodoroExtendCommand(),
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

    # 2. 未识别的命令
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
