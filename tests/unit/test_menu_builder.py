# tests/unit/test_menu_builder.py
"""测试 MenuBuilder 主菜单结构精简与逻辑断言。"""
from types import SimpleNamespace

import pytest
from zentray.ui.menu_builder import MenuBuilder


def test_build_main_menu_idle_structure():
    mb = MenuBuilder()
    items = mb.build_main_menu(
        is_pomodoro=False,
        pomodoro_minutes=25,
        extend_minutes=10,
    )

    item_ids = [item if isinstance(item, str) else item["id"] for item in items]
    expected_ids = [
        "task_list",
        "separator",
        "pomodoro",
        "separator",
        "settings",
        "quit",
    ]
    assert item_ids == expected_ids


def test_build_main_menu_enabled_matrix():
    mb = MenuBuilder()

    # 1. 有任务，非番茄
    items1 = mb.build_main_menu(is_pomodoro=False)
    dict_items1 = {item["id"]: item for item in items1 if isinstance(item, dict)}
    assert dict_items1["task_list"]["enabled"] is True

    # 2. 无任务，非番茄
    items2 = mb.build_main_menu(is_pomodoro=False)
    dict_items2 = {item["id"]: item for item in items2 if isinstance(item, dict)}
    assert dict_items2["task_list"]["enabled"] is True

    # 3. 番茄中
    items3 = mb.build_main_menu(is_pomodoro=True)
    dict_items3 = {item["id"]: item for item in items3 if isinstance(item, dict)}
    assert dict_items3["task_list"]["enabled"] is False
    assert dict_items3["stop_pomodoro"]["enabled"] is True
    assert dict_items3["extend_pomodoro"]["enabled"] is True


class _FakeManifest:
    def __init__(self, id, name, type_value):
        self.id = id
        self.name = name
        self.type = SimpleNamespace(value=type_value)


class _FakePlugin:
    def __init__(self, id, name, type_value):
        self.manifest = _FakeManifest(id, name, type_value)


def test_ops_menu_without_plugins():
    """启用但零插件：面板入口隐藏（管理入口在设置页，菜单保持简洁）。"""
    mb = MenuBuilder()
    base = mb.build_main_menu(is_pomodoro=False)
    enabled_empty = mb.build_main_menu(
        is_pomodoro=False, ops_enabled=True, ops_plugins=[]
    )
    assert base == enabled_empty


def test_ops_panel_entry_with_plugins():
    """≥1 插件且启用：单项 ops.panel（无子菜单，列表在 Vue 面板）。

    id 必须落在 ops.* 命名空间：commands.dispatch() 以 startswith("ops.") 路由，
    曾因下划线命名 ops_panel 静默失联（托盘点击无响应）。
    """
    mb = MenuBuilder()
    items = mb.build_main_menu(
        is_pomodoro=False,
        ops_enabled=True,
        ops_plugins=[
            _FakePlugin("demo", "示例脚本", "script"),
            _FakePlugin("svc", "示例服务", "service"),
        ],
    )
    item_ids = [item if isinstance(item, str) else item["id"] for item in items]
    assert item_ids[:3] == ["ops.panel", "separator", "task_list"]
    assert items[0] == {"id": "ops.panel", "label": "🧩 插件"}
    assert "submenu" not in items[0]


def test_dispatch_routes_ops_panel_entry(monkeypatch):
    """托盘 ops.panel 项 → dispatch → 面板打开（回归：id 命名空间断层）。"""
    import zentray.ui.commands as commands_mod
    import zentray.ui.vue_commands as vue_commands_mod

    opened = []
    monkeypatch.setattr(
        vue_commands_mod, "try_vue_plugin_panel", lambda controller: opened.append(True) or True
    )
    assert commands_mod.dispatch("ops.panel", None) is True
    assert opened == [True]


def test_ops_busy_keeps_panel_enabled_disables_pomodoro():
    """脚本运行中：专注入口禁用；面板项仍可打开（busy 态在面板内禁按钮）。"""
    mb = MenuBuilder()
    items = mb.build_main_menu(
        is_pomodoro=False,
        ops_enabled=True,
        ops_plugins=[_FakePlugin("demo", "示例脚本", "script")],
        ops_busy=True,
    )
    by_id = {it["id"]: it for it in items if isinstance(it, dict)}
    assert by_id["ops.panel"].get("enabled", True) is True
    assert by_id["pomodoro"]["enabled"] is False
