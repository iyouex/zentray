# zentray/ui/menu_builder.py
"""菜单构建器 —— 动态生成托盘右键菜单结构。"""
from typing import List, Optional


class MenuBuilder:
    """托盘右键菜单构建器"""

    def __init__(self):
        self._last_items = None

    def build_ops_entry(self, plugins: list = None) -> Optional[dict]:
        """「🧩 插件」面板入口（管理入口在 设置 → 🧩 插件）。

        GNOME 托盘（AppIndicator/DBusMenu）无向右弹出的子菜单，插件列表
        移入 Vue 面板。无插件时返回 None（保持极简菜单）。
        """
        if not plugins:
            return None
        # id 必须落在 ops.* 命名空间：dispatch() 以 startswith("ops.") 路由
        return {"id": "ops.panel", "label": "🧩 插件"}

    def build_main_menu(
        self,
        is_pomodoro: bool,
        pomodoro_minutes: Optional[int] = None,
        extend_minutes: Optional[int] = None,
        ops_enabled: bool = False,
        ops_plugins: Optional[list] = None,
        ops_busy: bool = False,
        pomodoro_phase: str = "idle",
        pomodoro_today: Optional[tuple] = None,
        focus_task_title: str = "",
    ) -> List[dict]:
        """
        构建主菜单。

        注意：菜单结构不依赖轮播当前标题/当前任务星标，避免轮播时整菜单重建闪动。
        插件面板入口为动态项：启用且装了插件才出现（列表/运行在面板，管理在设置页）。
        pomodoro_phase: idle | focus | short_break | long_break（休息段菜单分叉）
        pomodoro_today: (今日番茄数, 今日专注分钟) 统计信息行；None=不显示
        focus_task_title: 专注绑定任务标题（专注中显示信息行，可为空）
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

        items = [
            {
                "id": "task_list",
                "label": "📋 任务列表",
                "enabled": not is_pomodoro,
            },
        ]

        items.append("separator")

        if is_pomodoro and pomodoro_phase in ("short_break", "long_break"):
            # 休息段：可跳过休息，无中止/延长
            items.append({
                "id": "skip_break",
                "label": "⏭ 跳过休息",
                "enabled": True,
            })
        elif is_pomodoro:
            if focus_task_title:
                items.append({
                    "id": "pomodoro_task",
                    "label": f"🍅 专注中: {str(focus_task_title)[:24]}",
                    "enabled": False,
                })
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
                "enabled": not ops_busy,
            })

        if pomodoro_today is not None:
            count, minutes = pomodoro_today
            items.append({
                "id": "pomodoro_stats",
                "label": f"今日 🍅 {count} · {minutes} 分钟",
                "enabled": False,
            })

        items.append("separator")
        items.append({"id": "settings", "label": "⚙️ 设置"})
        items.append({"id": "quit", "label": "❌ 退出程序"})

        if ops_enabled:
            ops_entry = self.build_ops_entry(ops_plugins)
            if ops_entry:
                items.insert(0, ops_entry)
                items.insert(1, "separator")

        return items

    def should_update(self, items: List[dict]) -> bool:
        if items != self._last_items:
            self._last_items = items
            return True
        return False
