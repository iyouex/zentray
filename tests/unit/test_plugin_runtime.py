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


# ==========================================
# v2：RESULT 成败语义 / 元数据 / 上下文注入 / run_report
# ==========================================


def _make_runtime(tmp_data_dir, monkeypatch):
    monkeypatch.setattr("zentray.plugins.runtime.DATA_DIR", tmp_data_dir)
    loader = PluginLoader()
    loader.scan(user_dir=FIXTURES, load_bundled=False, load_user=True)
    return PluginRuntime(), loader


def _run_and_wait(qapp, rt, plugin, **kwargs):
    finished = []
    reports = []
    rt.script_finished.connect(lambda i, ok, s: finished.append((i, ok, s)))
    rt.run_report.connect(lambda r: reports.append(r))
    assert rt.run_script(plugin, **kwargs)
    deadline = time.time() + 10
    while not reports and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.05)
    assert reports, "run_report 未发出"
    return reports[0]


def test_result_fail_vetoes_exit0(qapp, tmp_data_dir, monkeypatch):
    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    report = _run_and_wait(qapp, rt, loader.get("result-fail"))
    assert report["ok"] is False
    assert "RESULT" in report["summary"]
    assert report["result_text"]


def test_exit1_vetoes_result_ok(qapp, tmp_data_dir, monkeypatch):
    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    report = _run_and_wait(qapp, rt, loader.get("result-ok-exit1"))
    assert report["ok"] is False
    assert "code=1" in report["summary"]


def test_result_text_becomes_summary(qapp, tmp_data_dir, monkeypatch):
    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    report = _run_and_wait(qapp, rt, loader.get("result-ok-text"))
    assert report["ok"] is True
    assert report["summary"] == "清理了 12 项"


def test_no_result_defaults_to_exit_code(qapp, tmp_data_dir, monkeypatch):
    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    report = _run_and_wait(qapp, rt, loader.get("sample-script"))
    assert report["ok"] is True
    assert report["summary"] == "成功"
    assert report["result_text"] == "成功"


def test_meta_json_written(qapp, tmp_data_dir, monkeypatch):
    import json

    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    report = _run_and_wait(qapp, rt, loader.get("result-ok-text"))
    runs_dir = tmp_data_dir / "ops_runs"
    metas = list(runs_dir.glob("*_result-ok-text.json"))
    assert len(metas) == 1
    meta = json.loads(metas[0].read_text(encoding="utf-8"))
    assert meta["ok"] is True
    assert meta["trigger"] == "manual"
    assert meta["log"].endswith(".log")
    # last.json 同步写（托盘「上次运行日志」仍可用）
    last = json.loads((runs_dir / "last.json").read_text(encoding="utf-8"))
    assert last["id"] == "result-ok-text"
    assert last["summary"] == "清理了 12 项"


def test_task_env_injection(qapp, tmp_data_dir, monkeypatch):
    from zentray.core.models import Task

    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    task = Task(
        title="写周报",
        category="工作",
        priority="high",
        details="覆盖 Q3 数据",
        deadline="2026-09-30",
    )
    report = _run_and_wait(
        qapp, rt, loader.get("env-echo"), task=task, trigger="task_done"
    )
    assert report["ok"] is True, report["summary"]
    assert report["task_id"] == task.id
    assert report["trigger"] == "task_done"
    log_text = Path(report["log"]).read_text(encoding="utf-8")
    assert f"TASK_ID={task.id}" in log_text
    assert "TASK_TITLE=写周报" in log_text
    assert "TASK_CATEGORY=工作" in log_text
    assert "TASK_DETAILS=覆盖 Q3 数据" in log_text
    assert "TASK_DEADLINE=2026-09-30" in log_text
    assert "TRIGGER=task_done" in log_text


def test_task_env_sparse_fields(qapp, tmp_data_dir, monkeypatch):
    from zentray.core.models import Task

    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    # category 空 post_init 会兜底为「工作」；details/deadline 可为空
    task = Task(title="极简任务", category="")
    report = _run_and_wait(qapp, rt, loader.get("env-echo"), task=task)
    log_text = Path(report["log"]).read_text(encoding="utf-8")
    assert f"TASK_ID={task.id}" in log_text
    assert "TASK_TITLE=极简任务" in log_text
    assert "TASK_CATEGORY=工作" in log_text  # 模型兜底值
    assert "TASK_DETAILS=none" in log_text  # 空字段不注入
    assert "TASK_DEADLINE=none" in log_text
    assert "TRIGGER=manual" in log_text
