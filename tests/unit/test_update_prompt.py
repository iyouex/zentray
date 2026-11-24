"""更新提示入口：托盘菜单项、命令分发、提示文案、控制器接线、通知按钮文案透传。"""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from zentray.services.updater import tray_hint
from zentray.ui import commands as commands_mod
from zentray.ui import vue_commands as vue_commands_mod
from zentray.ui.controller import TrayController
from zentray.ui.menu_builder import MenuBuilder
from zentray.ui.renderer import TrayRenderer

FOUND = {"has_update": True, "version": "9.9.9"}


def _ids(items):
    return [item if isinstance(item, str) else item["id"] for item in items]


def test_menu_shows_the_update_entry_only_when_there_is_something_to_say():
    mb = MenuBuilder()
    assert "update.open" not in _ids(mb.build_main_menu(is_pomodoro=False))

    items = mb.build_main_menu(is_pomodoro=False, update_hint="⬆️ 新版本 v9.9.9")
    by_id = {it["id"]: it for it in items if isinstance(it, dict)}

    assert by_id["update.open"] == {"id": "update.open", "label": "⬆️ 新版本 v9.9.9"}
    assert _ids(items)[-3:] == ["update.open", "settings", "quit"]  # 紧挨「设置」上方


@pytest.mark.parametrize("snapshot, expected", [
    ({"state": "idle"}, ""),
    ({"state": "checking", "result": None}, ""),
    ({"state": "uptodate", "result": {"has_update": False, "version": "9.9.9"}}, ""),
    ({"state": "available", "result": FOUND}, "⬆️ 新版本 v9.9.9"),
    ({"state": "downloading", "result": FOUND}, "⬆️ 新版本 v9.9.9"),
    ({"state": "ready", "result": FOUND}, "⬆️ 新版本 v9.9.9"),
    # 下载失败后入口还在，用户能回到更新页重试
    ({"state": "error", "error": "下载失败", "result": FOUND}, "⬆️ 新版本 v9.9.9"),
    # 纯检查失败：没有可点的内容，不显示
    ({"state": "error", "error": "检查更新失败", "result": None}, ""),
    ({"state": "installed", "version": "9.9.9", "result": FOUND},
     "⬆️ 重启以完成更新 v9.9.9"),
])
def test_tray_hint_follows_the_state_machine(snapshot, expected):
    assert tray_hint(snapshot) == expected


def test_tray_update_entry_opens_settings_on_the_system_tab(monkeypatch):
    opened = []
    monkeypatch.setattr(vue_commands_mod, "use_vue_ui", lambda: True)
    monkeypatch.setattr(vue_commands_mod, "open_vue_route",
                        lambda route, **kw: opened.append((route, kw)) or (True, {}))
    controller = SimpleNamespace(apply_settings=Mock(), update_display=Mock())

    assert commands_mod.dispatch("update.open", controller) is True

    assert opened == [("/settings", {"title": "设置", "width": 1080, "height": 680,
                                     "query": {"tab": "system"}})]
    controller.apply_settings.assert_called_once_with()
    controller.update_display.assert_called_once_with()


def test_tray_update_entry_falls_back_to_the_plain_settings_dialog(monkeypatch):
    monkeypatch.setattr(vue_commands_mod, "use_vue_ui", lambda: False)
    fallback = Mock()
    monkeypatch.setattr(commands_mod.SettingsCommand, "execute", fallback)
    controller = object()

    assert commands_mod.dispatch("update.open", controller) is True

    # 没有 Vue 界面时退回普通「设置」入口（原生对话框路径由 SettingsCommand 自己处理）；
    # 替身是普通 Mock，被当成未绑定方法调用，所以只收到 controller 一个参数。
    fallback.assert_called_once_with(controller)


# —— 控制器接线（薄层：用鸭子类型的替身验证调用了什么，不构造真实 TrayController）—————


def _controller_double():
    return SimpleNamespace(
        renderer=SimpleNamespace(show_notification=Mock(), show_event=Mock()),
        _refresh_menu=Mock(),
        open_update_page=Mock(),
        handle_action=Mock(),
    )


def test_found_notification_points_at_the_update_page_and_refreshes_the_menu():
    controller = _controller_double()

    TrayController.on_update_found(controller, "9.9.9")

    args, kwargs = controller.renderer.show_notification.call_args
    assert args == ("发现新版本", "ZenTray v9.9.9 可用")
    assert kwargs["on_click"] is controller.open_update_page
    assert kwargs["action_label"] == "查看更新"  # 不再沿用报告通知的「点击查看报告」
    controller.renderer.show_event.assert_called_once_with(
        "⬆ 发现新版本 v9.9.9", kind="info", on_click=controller.open_update_page)
    controller._refresh_menu.assert_called_once_with()
    controller.handle_action.assert_not_called()  # 只提示，不擅自开窗


def test_swap_failure_is_reported_without_opening_or_relaunching_anything():
    controller = _controller_double()

    TrayController.on_update_swap_failed(controller, "swap_failed")

    assert controller.renderer.show_notification.call_args.args[0] == "更新未完成"
    controller.renderer.show_event.assert_not_called()
    controller._refresh_menu.assert_not_called()
    controller.handle_action.assert_not_called()


def test_state_change_only_refreshes_the_menu():
    controller = _controller_double()
    TrayController.on_update_state_changed(controller)
    controller._refresh_menu.assert_called_once_with()
    controller.renderer.show_notification.assert_not_called()


def test_update_page_action_goes_through_the_command_table():
    controller = _controller_double()
    TrayController.open_update_page(controller)
    controller.handle_action.assert_called_once_with("update.open")


def test_notification_action_label_is_passed_only_when_given():
    backend = SimpleNamespace(show_notification=Mock())
    renderer = TrayRenderer(backend)
    on_click = lambda: None  # noqa: E731

    renderer.show_notification("标题", "内容")
    renderer.show_notification("标题", "内容", on_click)
    renderer.show_notification("标题", "内容", on_click, action_label="查看更新")

    assert [call.args for call in backend.show_notification.call_args_list] == [
        ("标题", "内容", None), ("标题", "内容", on_click),
        ("标题", "内容", on_click, "查看更新")]

