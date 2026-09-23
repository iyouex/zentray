"""worker 线程信号必须经 bound method 排队回主线程执行。

回归背景：lambda/普通函数连接在 PySide6 中是 direct，弹窗会在 worker 线程上创建，
导致下拉点击失效与 QtWebEngine 线程断言崩溃。
"""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QEventLoop, QTimer, QThread, Signal

import zentray.main
from zentray.main import AppRuntime


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(["zentray-test"])
    return app


class _Worker(QThread):
    due = Signal(object, str)

    def run(self):
        self.due.emit(object(), "k")


def test_worker_signal_delivers_slot_on_main_thread(qapp):
    seen = {}

    class _Spy(AppRuntime):
        def on_reminder_due(self, task, fire_key):
            seen["slot_thread"] = QThread.currentThread()

    spy = _Spy()
    worker = _Worker()
    worker.due.connect(spy.on_reminder_due)

    worker.start()
    loop = QEventLoop()
    QTimer.singleShot(300, loop.quit)
    worker.wait(5000)
    loop.exec()

    assert seen.get("slot_thread") is not None
    assert seen["slot_thread"] == qapp.thread()


def test_main_wires_worker_signals_to_bound_methods():
    src = Path(zentray.main.__file__).read_text(encoding="utf-8")
    assert "reminder_due.connect(runtime.on_reminder_due)" in src
    assert "task_overdue.connect(runtime.on_task_overdue)" in src
    assert "hotkey.triggered.connect(runtime.on_quick_add)" in src
    assert "connect(\n        lambda" not in src
