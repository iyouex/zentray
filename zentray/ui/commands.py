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
        if getattr(controller, "plugin_runtime", None) and (
            controller.plugin_runtime.is_busy or getattr(controller, "_ops_active", False)
        ):
            controller.renderer.show_notification(
                "番茄钟", "脚本运行中，请稍后再开始专注。"
            )
            return
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

    # 2. 插件菜单（ops.*）
    if action_id.startswith("ops."):
        return _dispatch_ops_action(action_id, controller)

    # 3. 未识别的命令
    return False


def _dispatch_ops_action(action_id: str, controller: "TrayController") -> bool:
    """插件菜单。"""
    from PySide6.QtWidgets import QMessageBox

    if action_id in ("ops._hdr_scripts", "ops._hdr_services", "ops_menu"):
        return True

    if action_id == "ops.open_last_log":
        import json
        import subprocess
        import sys
        from pathlib import Path

        from zentray.config import DATA_DIR

        last = DATA_DIR / "ops_runs" / "last.json"
        if not last.is_file():
            controller.renderer.show_notification("插件", "尚无运行记录")
            return True
        try:
            data = json.loads(last.read_text(encoding="utf-8"))
            log_path = Path(data.get("log") or "")
            if log_path.is_file():
                if sys.platform.startswith("linux"):
                    subprocess.Popen(["xdg-open", str(log_path)])
                else:
                    subprocess.Popen(["open", str(log_path)])
            else:
                controller.renderer.show_notification(
                    "插件", data.get("summary") or "无日志文件"
                )
        except Exception as e:
            controller.renderer.show_notification("打开日志失败", str(e)[:100])
        return True

    runtime = getattr(controller, "plugin_runtime", None)
    loader = getattr(controller, "plugin_loader", None)
    if runtime is None or loader is None:
        return False

    if action_id.startswith("ops.script."):
        pid = action_id[len("ops.script.") :]
        plug = loader.get(pid)
        if not plug:
            controller.renderer.show_notification("插件", f"插件不存在: {pid}")
            return True
        if runtime.is_busy:
            controller.renderer.show_notification("插件", "已有脚本在运行，请稍候。")
            return True
        if controller.pomodoro_service.is_active:
            controller.renderer.show_notification(
                "插件", "番茄钟进行中，请先结束专注。"
            )
            return True
        # 有参脚本：参数弹窗（预填 预设→default，可改后运行）
        if plug.manifest.params:
            values = _prompt_script_params(plug)
            if values is None:
                return True
            runtime.run_script(plug, pomodoro_active=False, param_values=values)
            return True
        # 无参脚本：恒弹「确定运行」确认（防误触——脚本会抢占任务轮播）
        ret = QMessageBox.question(
            None,
            "运行脚本",
            f"确定运行「{plug.manifest.name}」？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return True
        runtime.run_script(plug, pomodoro_active=False)
        return True

    if action_id.startswith("ops.service."):
        rest = action_id[len("ops.service.") :]
        # id.action
        if rest.endswith(".start"):
            pid, act = rest[: -len(".start")], "start"
        elif rest.endswith(".stop"):
            pid, act = rest[: -len(".stop")], "stop"
        elif rest.endswith(".status"):
            pid, act = rest[: -len(".status")], "status"
        else:
            return True
        plug = loader.get(pid)
        if not plug:
            controller.renderer.show_notification("插件", f"插件不存在: {pid}")
            return True
        if act in ("start", "stop") and controller.pomodoro_service.is_active:
            controller.renderer.show_notification(
                "插件", "番茄钟进行中，请先结束专注。"
            )
            return True
        if runtime.is_busy:
            controller.renderer.show_notification("插件", "脚本运行中，请稍候。")
            return True
        ok, detail = runtime.service_cmd(plug, act, pomodoro_active=False)
        controller.renderer.show_notification(plug.manifest.name, f"{act}: {detail}")
        return True

    return False


# ==========================================
# 内部辅助
# ==========================================

def _prompt_script_params(plug):
    """有参脚本运行前弹窗：每参一行（预填 预设→default），确定返回值列表，取消返回 None。"""
    from PySide6.QtWidgets import (
        QDialog,
        QDialogButtonBox,
        QFormLayout,
        QLineEdit,
        QVBoxLayout,
    )

    from zentray.plugins.models import resolve_param_values
    from zentray.plugins.runtime import _read_param_presets

    m = plug.manifest
    presets = _read_param_presets(m.id)
    dialog = QDialog()
    dialog.setWindowTitle(f"运行「{m.name}」")
    dialog.setModal(True)
    form = QFormLayout()
    edits = []
    for p in m.params:
        edit = QLineEdit(resolve_param_values([p], presets)[0])
        if p.description:
            edit.setPlaceholderText(p.description)
        form.addRow(f"{p.description or p.name}（{p.name}）:", edit)
        edits.append(edit)
    btns = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    btns.accepted.connect(dialog.accept)
    btns.rejected.connect(dialog.reject)
    lay = QVBoxLayout(dialog)
    lay.addLayout(form)
    lay.addWidget(btns)
    if not run_modal_loop(dialog):
        return None
    return [e.text() for e in edits]


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
