# -*- coding: utf-8 -*-
"""通知点击打开运行报告：探测缓存 + 回调接线"""
from unittest import mock

import zentray.ui.tray as tray_mod
from zentray.ui.controller import TrayController


def test_notify_send_action_probe():
    tray_mod._notify_action_cache = None
    with mock.patch("subprocess.run") as run:
        run.return_value = mock.Mock(stdout="  --action=ACTION  --wait", stderr="")
        assert tray_mod._notify_send_supports_actions() is True
    tray_mod._notify_action_cache = None
    with mock.patch("subprocess.run") as run:
        run.return_value = mock.Mock(stdout="  -t TIMEOUT", stderr="")
        assert tray_mod._notify_send_supports_actions() is False
    # 探测失败（无 notify-send）→ False 且不再重复探测
    tray_mod._notify_action_cache = None
    with mock.patch("subprocess.run", side_effect=FileNotFoundError):
        assert tray_mod._notify_send_supports_actions() is False
        assert tray_mod._notify_action_cache is False


def test_report_opener_invokes_run_open(monkeypatch):
    calls = []

    def fake_open(body):
        calls.append(body)
        return 200, {"ok": True}

    monkeypatch.setattr("zentray.api.handlers._plugin_run_open", fake_open)
    cb = TrayController._make_report_opener("20260930_120000_ai-news-digest")
    assert cb is not None
    cb()
    assert calls == [{"run_id": "20260930_120000_ai-news-digest"}]


def test_report_opener_none_without_run_id():
    assert TrayController._make_report_opener("") is None
