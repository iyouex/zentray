"""窄边 flyout：任务/插件列表与设置/退出（离屏实际点击）。"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QPushButton

from zentray.ui.win_flyout import SystemFlyout, TaskPluginFlyout


class _Provider:
    def __init__(self):
        self.selected = None
        self.opened_tasks = 0
        self.opened_plugins = 0
        self.actions = []

    def flyout_snapshot(self):
        return {
            "tasks": [
                {"id": "t1", "title": "写文档", "priority": "high", "deadline": "2026-11-22", "current": True},
                {"id": "t2", "title": "整理清单", "priority": "low", "deadline": None, "current": False},
            ],
            "plugins": [{"id": "p1", "name": "文本工具箱", "busy": False}],
        }

    def flyout_select_task(self, task_id):
        self.selected = task_id

    def flyout_open_tasks(self):
        self.opened_tasks += 1

    def flyout_open_plugins(self):
        self.opened_plugins += 1

    def flyout_action(self, action_id):
        self.actions.append(action_id)


def _ensure_qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["zentray-test"])
    if not isinstance(app, QApplication):
        pytest.skip("进程已有 QGuiApplication，无法创建 QWidget")
    return app


def _button(flyout, needle):
    for b in flyout.findChildren(QPushButton):
        if needle in b.text():
            return b
    raise AssertionError(f"button not found: {needle}; {[b.text() for b in flyout.findChildren(QPushButton)]}")


def test_task_flyout_rows_and_select():
    _ensure_qapp()
    p = _Provider()
    f = TaskPluginFlyout(p)
    try:
        f.open_at((100, 100, 360, 430))
        _button(f, "写文档").click()
        assert p.selected == "t1"
        assert not f.isVisible()
    finally:
        f.close()


def test_task_flyout_plugin_and_footer():
    _ensure_qapp()
    p = _Provider()
    f = TaskPluginFlyout(p)
    try:
        f.open_at((100, 100, 360, 430))
        _button(f, "文本工具箱").click()
        assert p.opened_plugins == 1
        f2 = TaskPluginFlyout(p)
        f2.open_at((100, 100, 360, 430))
        _button(f2, "打开完整列表").click()
        assert p.opened_tasks == 1
        f2.close()
    finally:
        f.close()


def test_system_flyout_actions():
    _ensure_qapp()
    p = _Provider()
    f = SystemFlyout(p)
    try:
        f.open_at((100, 100, 236, 236))
        _button(f, "设置").click()
        _button(f, "插件管理").click()
        _button(f, "退出").click()
        assert p.actions == ["settings", "ops.panel", "quit"]
    finally:
        f.close()
