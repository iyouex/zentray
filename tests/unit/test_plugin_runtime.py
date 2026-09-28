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
    loader.scan(user_dir=FIXTURES)
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
    loader.scan(user_dir=FIXTURES)
    plugin = loader.get("sample-script")
    rt = PluginRuntime()
    assert rt.run_script(plugin, pomodoro_active=True) is False


def test_service_status(qapp, tmp_data_dir, monkeypatch):
    monkeypatch.setattr("zentray.plugins.runtime.DATA_DIR", tmp_data_dir)
    loader = PluginLoader()
    loader.scan(user_dir=FIXTURES)
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
    loader.scan(user_dir=FIXTURES)
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


# ==========================================
# 插件数据目录：ZENTRAY_PLUGIN_DATA_DIR 注入（_base_env，script/service 共用）
# ==========================================


def test_plugin_data_dir_env(qapp, tmp_data_dir, monkeypatch):
    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    report = _run_and_wait(qapp, rt, loader.get("env-echo"))
    assert report["ok"] is True, report["summary"]
    data_dir = tmp_data_dir / "plugin_data" / "env-echo"
    assert f"DATA_DIR={data_dir}" in _read_log(report)
    assert data_dir.is_dir()  # 运行前自动创建


# ==========================================
# v2.1：命名入参（argv = entry + args + 参数值）
# ==========================================


def _read_log(report) -> str:
    return Path(report["log"]).read_text(encoding="utf-8")


def test_param_values_appended_after_args(qapp, tmp_data_dir, monkeypatch):
    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    report = _run_and_wait(
        qapp, rt, loader.get("param-echo"), param_values=["web", "2"]
    )
    assert report["ok"] is True, report["summary"]
    assert "--mode=echo web 2" in _read_log(report)


def test_param_defaults_when_omitted(qapp, tmp_data_dir, monkeypatch):
    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    report = _run_and_wait(qapp, rt, loader.get("param-echo"))
    assert report["ok"] is True, report["summary"]
    assert "--mode=echo all 1" in _read_log(report)


def test_run_plugin_api_passes_params(qapp, tmp_data_dir, monkeypatch):
    """POST /api/plugins/{id}/run body.params → 按声明顺序展开；缺省回落 default。"""
    from zentray.api import handlers
    from zentray.api.handlers import ApiContext
    from zentray.services.settings_manager import SettingsManager

    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    sm = SettingsManager.reload()
    sm.ops.enabled = True
    sm.save()
    monkeypatch.setattr(
        handlers,
        "_ctx",
        ApiContext(plugin_runtime=rt, plugin_loader=loader),
    )

    reports = []
    rt.run_report.connect(lambda r: reports.append(r))
    code, body = handlers._run_plugin(
        "param-echo", {"params": {"target": "web"}}
    )
    assert code == 200, body
    assert body["ok"] is True
    deadline = time.time() + 10
    while not reports and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.05)
    assert reports, "run_report 未发出"
    # target 显式传入；level 未传回落 default "1"
    assert "--mode=echo web 1" in _read_log(reports[0])


def test_param_preset_beats_default_when_omitted(qapp, tmp_data_dir, monkeypatch):
    """run_script 未传 param_values → 预设 > manifest default（触发器路径同此）。"""
    from zentray.services.settings_manager import SettingsManager

    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    sm = SettingsManager.reload()
    sm.ops.param_presets = {"param-echo": {"target": "dns"}}
    report = _run_and_wait(qapp, rt, loader.get("param-echo"))
    assert report["ok"] is True, report["summary"]
    # target 用预设 dns；level 无预设回落 default 1
    assert "--mode=echo dns 1" in _read_log(report)


def test_explicit_values_beat_preset(qapp, tmp_data_dir, monkeypatch):
    from zentray.services.settings_manager import SettingsManager

    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    sm = SettingsManager.reload()
    sm.ops.param_presets = {"param-echo": {"target": "dns"}}
    report = _run_and_wait(
        qapp, rt, loader.get("param-echo"), param_values=["web", "2"]
    )
    assert "--mode=echo web 2" in _read_log(report)


def test_report_has_run_id_and_times(qapp, tmp_data_dir, monkeypatch):
    rt, loader = _make_runtime(tmp_data_dir, monkeypatch)
    report = _run_and_wait(qapp, rt, loader.get("param-echo"))
    assert report["run_id"].startswith("20")
    assert report["run_id"].endswith("_param-echo")
    assert report["started_at"]  # ISO 起点
    assert report["time"] >= report["started_at"]  # time=结束时刻


def test_resolve_param_values_priority():
    """显式传入 > 预设 > manifest default（托盘弹窗/API/触发共用）。"""
    from zentray.plugins.models import PluginParam, resolve_param_values

    params = [
        PluginParam(name="a", default="da"),
        PluginParam(name="b", default="db"),
        PluginParam(name="c", default="dc"),
    ]
    presets = {"a": "pa", "b": "pb"}
    # 全缺省：预设优先，无预设回落 default
    assert resolve_param_values(params, presets) == ["pa", "pb", "dc"]
    # 显式覆盖（含空串显式值也算显式）
    assert resolve_param_values(params, presets, {"a": "x", "b": ""}) == ["x", "", "dc"]
    # 无预设
    assert resolve_param_values(params, None) == ["da", "db", "dc"]
