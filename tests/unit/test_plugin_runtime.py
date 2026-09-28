import time
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

from zentray.plugins.loader import PluginLoader
from zentray.plugins.runtime import PluginRuntime

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "plugins"


@pytest.fixture
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    return app


def test_run_sample_script(qapp, tmp_data_dir, monkeypatch):
    monkeypatch.setattr("zentray.plugins.runtime.DATA_DIR", tmp_data_dir)
    loader = PluginLoader()
    loader.scan(user_dir=FIXTURES, load_bundled=False, load_user=True)
    plugin = loader.get("sample-script")
    assert plugin is not None

    rt = PluginRuntime()
    finished = []
    logs = []
    rt.script_finished.connect(lambda i, ok, s: finished.append((i, ok, s)))
    rt.log_line.connect(lambda t: logs.append(t))

    assert rt.run_script(plugin, pomodoro_active=False)
    # 等待线程
    deadline = time.time() + 10
    while not finished and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.05)
    assert finished, f"logs={logs}"
    assert finished[0][0] == "sample-script"
    assert finished[0][1] is True
    assert any("⚡" in x for x in logs)


def test_reject_when_pomodoro(qapp, tmp_data_dir, monkeypatch):
    monkeypatch.setattr("zentray.plugins.runtime.DATA_DIR", tmp_data_dir)
    loader = PluginLoader()
    loader.scan(user_dir=FIXTURES, load_bundled=False, load_user=True)
    plugin = loader.get("sample-script")
    rt = PluginRuntime()
    assert rt.run_script(plugin, pomodoro_active=True) is False


def test_service_status(qapp, tmp_data_dir, monkeypatch):
    monkeypatch.setattr("zentray.plugins.runtime.DATA_DIR", tmp_data_dir)
    loader = PluginLoader()
    loader.scan(user_dir=FIXTURES, load_bundled=False, load_user=True)
    plugin = loader.get("sample-service")
    rt = PluginRuntime()
    logs = []
    rt.log_line.connect(lambda t: logs.append(t))
    ok, detail = rt.service_cmd(plugin, "start")
    assert ok, detail
    ok, detail = rt.service_cmd(plugin, "status")
    assert ok, detail
    assert detail == "running"
    ok, detail = rt.service_cmd(plugin, "stop")
    assert ok, detail
    # 服务命令不得触发托盘抢占文案（否则 _ops_active 无复位路径，轮播卡死）
    assert logs == []
