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


# ---- 番茄钟循环菜单（v0.6.5：休息段/统计行/绑定任务） ----

def test_break_phase_menu_has_skip_only():
    """休息段：跳过休息；无中止专注/延长；任务列表仍禁用。"""
    mb = MenuBuilder()
    items = mb.build_main_menu(
        is_pomodoro=True,
        pomodoro_minutes=25,
        extend_minutes=10,
        pomodoro_phase="short_break",
    )
    by_id = {it["id"]: it for it in items if isinstance(it, dict)}
    assert by_id["skip_break"]["enabled"] is True
    assert "stop_pomodoro" not in by_id
    assert "extend_pomodoro" not in by_id
    assert by_id["task_list"]["enabled"] is False


def test_focus_phase_menu_defaults_backward_compatible():
    """旧调用（只传 is_pomodoro=True）：专注菜单结构不变。"""
    mb = MenuBuilder()
    items = mb.build_main_menu(is_pomodoro=True)
    by_id = {it["id"]: it for it in items if isinstance(it, dict)}
    assert by_id["stop_pomodoro"]["enabled"] is True
    assert by_id["extend_pomodoro"]["enabled"] is True
    assert "skip_break" not in by_id
    assert "pomodoro_task" not in by_id


def test_focus_with_bound_task_shows_info_row():
    mb = MenuBuilder()
    items = mb.build_main_menu(
        is_pomodoro=True,
        pomodoro_phase="focus",
        focus_task_title="写周报",
    )
    by_id = {it["id"]: it for it in items if isinstance(it, dict)}
    assert by_id["pomodoro_task"]["label"] == "🍅 专注中: 写周报"
    assert by_id["pomodoro_task"]["enabled"] is False


def test_today_stats_merged_into_start_button():
    """空闲段：专注按钮融合今日统计；无独立统计行。"""
    mb = MenuBuilder()
    items = mb.build_main_menu(
        is_pomodoro=False,
        pomodoro_minutes=25,
        extend_minutes=10,
        pomodoro_today=(3, 75),
        pomodoro_label_format="🍅 专注{focus}mins -- 今日{today}mins",
    )
    by_id = {it["id"]: it for it in items if isinstance(it, dict)}
    assert by_id["pomodoro"]["label"] == "🍅 专注25mins"
    assert by_id["pomodoro"]["enabled"] is True
    assert by_id["pomodoro_info2"]["label"] == "今日75mins"
    assert by_id["pomodoro_info2"]["enabled"] is False
    assert "pomodoro_stats" not in by_id


def test_merged_label_format_placeholders_and_fallback():
    mb = MenuBuilder()
    items = mb.build_main_menu(
        is_pomodoro=False,
        pomodoro_today=(2, 50),
        pomodoro_label_format="今日已{count}🍅/{today}分，开专注{focus}分",
    )
    by_id = {it["id"]: it for it in items if isinstance(it, dict)}
    assert by_id["pomodoro"]["label"] == "今日已2🍅/50分，开专注25分"
    # 非法格式：回退兜底文案
    items2 = mb.build_main_menu(
        is_pomodoro=False,
        pomodoro_minutes=25,
        pomodoro_today=(1, 25),
        pomodoro_label_format="{oops",
    )
    by_id2 = {it["id"]: it for it in items2 if isinstance(it, dict)}
    assert by_id2["pomodoro"]["label"] == "🍅 专注 25分钟"
    assert by_id2["pomodoro_info2"]["label"] == "今日 25分钟"
    # 不传格式且不传统计（None）：保持旧版纯专注按钮
    items3 = mb.build_main_menu(is_pomodoro=False)
    by_id3 = {it["id"]: it for it in items3 if isinstance(it, dict)}
    assert by_id3["pomodoro"]["label"] == "🍅 专注 25 分钟"


def test_active_phase_keeps_stats_row():
    """专注/休息中：无开始按钮，今日统计单列一行。"""
    mb = MenuBuilder()
    items = mb.build_main_menu(
        is_pomodoro=True,
        pomodoro_phase="focus",
        pomodoro_today=(3, 75),
    )
    by_id = {it["id"]: it for it in items if isinstance(it, dict)}
    assert by_id["pomodoro_stats"]["label"] == "今日 🍅 3 · 75 分钟"
    assert by_id["pomodoro_stats"]["enabled"] is False
    assert "pomodoro" not in by_id


def test_break_icon_generation(tmp_path):
    """休息饼图进同一生成管线：break_{0..100}.png 与 tomato 同规格。"""
    from zentray.resources import _generate_pie_icons_into, tray_break_icon_name

    assert tray_break_icon_name(46) == "break_50"
    out = tmp_path / "icons"
    assert _generate_pie_icons_into(out) is True
    for pct in (0, 50, 100):
        assert (out / f"break_{pct}.png").exists()
        assert (out / f"tomato_{pct}.png").exists()
