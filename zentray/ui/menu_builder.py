# zentray/ui/menu_builder.py
"""菜单构建器 —— 动态生成托盘右键菜单结构。"""
from typing import List, Optional


class MenuBuilder:
    """托盘右键菜单构建器"""

    def __init__(self):
        self._last_items = None

    def build_ops_submenu(self, plugins: list = None, ops_busy: bool = False) -> Optional[dict]:
        """构建「🧩 插件」子菜单（管理入口在 设置 → 🧩 插件）。

        无插件时返回 None（保持极简菜单）。
        """
        plugins = plugins or []
        scripts = []
        services = []
        for p in plugins:
            m = p.manifest
            if m.type.value == "script":
                scripts.append({
                    "id": f"ops.script.{m.id}",
                    "label": m.name,
                    "enabled": not ops_busy,
                })
            else:
                services.append({
                    "id": f"ops.service.{m.id}",
                    "label": m.name,
                    "submenu": [
                        {"id": f"ops.service.{m.id}.start", "label": "▶ 启动", "enabled": not ops_busy},
                        {"id": f"ops.service.{m.id}.stop", "label": "⏹ 停止", "enabled": not ops_busy},
                        {"id": f"ops.service.{m.id}.status", "label": "ℹ 状态"},
                    ],
                })

        if not scripts and not services:
            return None

        submenu: List[dict] = []
        if scripts:
            submenu.append({"id": "ops._hdr_scripts", "label": "📜 脚本", "enabled": False})
            submenu.extend(scripts)
        if services:
            if submenu:
                submenu.append("separator")
            submenu.append({"id": "ops._hdr_services", "label": "🔧 服务", "enabled": False})
            submenu.extend(services)
        if submenu:
            submenu.append("separator")
        submenu.append({"id": "ops.open_last_log", "label": "📄 上次运行日志"})
        return {"id": "ops_menu", "label": "🧩 插件", "submenu": submenu}

    def build_main_menu(
        self,
        is_pomodoro: bool,
        pomodoro_minutes: Optional[int] = None,
        extend_minutes: Optional[int] = None,
        ops_enabled: bool = False,
        ops_plugins: Optional[list] = None,
        ops_busy: bool = False,
    ) -> List[dict]:
        """
        构建主菜单。

        注意：菜单结构不依赖轮播当前标题/当前任务星标，避免轮播时整菜单重建闪动。
        插件子菜单为动态入口：启用且装了插件才出现（管理在 设置 → 🧩 插件）。
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
                "enabled": not ops_busy,
            })

        items.append("separator")
        items.append({"id": "settings", "label": "⚙️ 设置"})
        items.append({"id": "quit", "label": "❌ 退出程序"})

        if ops_enabled:
            ops_menu = self.build_ops_submenu(ops_plugins, ops_busy=ops_busy)
            if ops_menu:
                items.insert(0, ops_menu)
                items.insert(1, "separator")

        return items

    def should_update(self, items: List[dict]) -> bool:
        if items != self._last_items:
            self._last_items = items
            return True
        return False
