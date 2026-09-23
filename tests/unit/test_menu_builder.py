# tests/unit/test_menu_builder.py
"""测试 MenuBuilder 主菜单结构精简与逻辑断言。"""
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
    assert dict_items3["extend_pomodoro"]["enabled"] is True)
