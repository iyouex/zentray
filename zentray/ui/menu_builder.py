# zentray/ui/menu_builder.py
"""菜单构建器 —— 动态生成托盘右键菜单结构。"""
from typing import List, Optional


class MenuBuilder:
    """托盘右键菜单构建器"""

    def __init__(self):
        self._last_items = None

    def build_extension_buttons(self, extensions: list) -> List[dict]:
        if not extensions:
            return []
        items = []
        for ext in extensions:
            config = ext.get_button_config()
            items.append({
                "id": f"extension_{ext.__class__.__name__}",
                "label": f"🔧 {config.get('tooltip', '脚本')}",
            })
        return items

    def build_main_menu(
        self,
        task_exists: bool,
        is_pomodoro: bool,
        tasks: list = None,
        current_task=None,
        extensions: list = None,
        pomodoro_minutes: Optional[int] = None,
        extend_minutes: Optional[int] = None,
    ) -> List[dict]:
        """
        构建主菜单。

        注意：菜单结构不依赖轮播当前标题/当前任务星标，避免轮播时整菜单重建闪动。
        tasks/current_task 参数保留兼容，不再用于生成子菜单。
        """
        if pomodoro_minutes is None or extend_minutes is None:
            try:
                from zentray.services.settings_manager import SettingsManager

                sm = SettingsManager()
                if pomodoro_minutes is None:
                    pomodoro_minutes = sm.pomodoro.duration_minutes
                if extend_minutes is None:
                    extend_minutes = sm.pomodoro.extend_minutes
            except Exception:
                pomodoro_minutes = pomodoro_minutes or 25
                extend_minutes = extend_minutes or 10

        extensions = extensions or []
        ext_buttons = self.build_extension_buttons(extensions)

        items = [
            {
                "id": "task_list",
                "label": "📋 任务列表",
                "enabled": not is_pomodoro,
            },
        ]

        items.append("separator")

        if is_pomodoro:
            items.append({
                "id": "stop_pomodoro",
                "label": "⏹ 中止专注",
                "enabled": True,
            })
            items.append({
                "id": "extend_pomodoro",
                "label": f"⏱ 延长 {extend_minutes} 分钟",
                "enabled": True,
            })
        else:
            items.append({
                "id": "pomodoro",
                "label": f"🍅 专注 {pomodoro_minutes} 分钟",
                "enabled": True,
            })

        if ext_buttons:
            items.append("separator")
            items.extend(ext_buttons)

        items.append("separator")
        items.append({
            "id": "history",
            "label": "📜 历史记录",
            "enabled": not is_pomodoro,
        })
        items.append({"id": "settings", "label": "⚙️ 设置"})
        items.append({"id": "quit", "label": "❌ 退出程序"})

        return items

    def should_update(self, items: List[dict]) -> bool:
        if items != self._last_items:
            self._last_items = items
            return True
        return False
