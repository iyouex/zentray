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


def test_ops_menu_hidden_without_plugins():
    """动态入口：无插件时菜单结构与未启用时逐项一致。"""
    mb = MenuBuilder()
    base = mb.build_main_menu(is_pomodoro=False)
    enabled_empty = mb.build_main_menu(
        is_pomodoro=False, ops_enabled=True, ops_plugins=[]
    )
    assert base == enabled_empty


def test_ops_menu_shown_with_plugins():
    """≥1 插件且启用：ops_menu 出现在菜单头部。"""
    mb = MenuBuilder()
    items = mb.build_main_menu(
        is_pomodoro=False,
        ops_enabled=True,
        ops_plugins=[_FakePlugin("demo", "示例脚本", "script")],
    )
    item_ids = [item if isinstance(item, str) else item["id"] for item in items]
    assert item_ids[:3] == ["ops_menu", "separator", "task_list"]
    ops_menu = items[0]
    sub_ids = [
        s if isinstance(s, str) else s["id"] for s in ops_menu["submenu"]
    ]
    assert "ops.script.demo" in sub_ids
    assert "ops.open_last_log" in sub_ids


def test_ops_menu_busy_disables_script_and_pomodoro():
    """脚本运行中：脚本项与专注入口双向禁用。"""
    mb = MenuBuilder()
    items = mb.build_main_menu(
        is_pomodoro=False,
        ops_enabled=True,
        ops_plugins=[_FakePlugin("demo", "示例脚本", "script")],
        ops_busy=True,
    )
    by_id = {}
    for it in items:
        if isinstance(it, dict):
            by_id[it["id"]] = it
            if "submenu" in it:
                for s in it["submenu"]:
                    if isinstance(s, dict):
                        by_id[s["id"]] = s
    assert by_id["ops.script.demo"]["enabled"] is False
    assert by_id["pomodoro"]["enabled"] is False
