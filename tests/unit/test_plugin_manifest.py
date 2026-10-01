"""plugin.yaml 校验测试。"""
from pathlib import Path

import pytest

from zentray.plugins.manifest import validate_plugin_dir
from zentray.plugins.models import PluginType, TriggerEvent, TriggerType

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "plugins"


def _write_plugin(tmp_path: Path, yaml_text: str) -> Path:
    d = tmp_path / "plug"
    d.mkdir()
    (d / "plugin.yaml").write_text(yaml_text, encoding="utf-8")
    sh = d / "run.sh"
    sh.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    sh.chmod(0o755)
    return d


def test_sample_script_valid():
    r = validate_plugin_dir(FIXTURES / "sample-script")
    assert r.ok, r.error_text()
    assert r.manifest is not None
    assert r.manifest.id == "sample-script"
    assert r.manifest.type == PluginType.SCRIPT
    assert r.manifest.entry_path.is_file()
    assert r.manifest.triggers == []
    assert r.manifest.write_back is False


def test_sample_service_valid():
    r = validate_plugin_dir(FIXTURES / "sample-service")
    assert r.ok, r.manifest.type == PluginType.SERVICE


def test_bad_escape_rejected():
    r = validate_plugin_dir(FIXTURES / "bad-escape")
    assert not r.ok
    assert any(".." in e or "相对" in e or "越出" in e for e in r.errors)


def test_missing_dir():
    r = validate_plugin_dir(FIXTURES / "no-such-plugin")
    assert not r.ok


_BASE_V2 = """\
id: trig-plug
name: 触发插件
version: 0.1.0
type: script
api_version: 2
entry: run.sh
"""


def test_triggers_all_forms_valid(tmp_path):
    d = _write_plugin(
        tmp_path,
        _BASE_V2
        + """\
triggers:
  - type: daily
    time: "09:30"
  - type: interval
    minutes: 30
  - type: cron
    expr: "*/15 9-17 * * 1-5"
  - type: event
    event: task_done
""",
    )
    r = validate_plugin_dir(d)
    assert r.ok, r.error_text()
    ts = r.manifest.triggers
    assert [t.type for t in ts] == [
        TriggerType.DAILY,
        TriggerType.INTERVAL,
        TriggerType.CRON,
        TriggerType.EVENT,
    ]
    assert ts[0].time == "09:30"
    assert ts[1].minutes == 30
    assert ts[2].expr == "*/15 9-17 * * 1-5"
    assert ts[3].event == TriggerEvent.TASK_DONE


def test_write_back_valid(tmp_path):
    d = _write_plugin(tmp_path, _BASE_V2 + "write_back: true\n")
    r = validate_plugin_dir(d)
    assert r.ok, r.error_text()
    assert r.manifest.write_back is True


@pytest.mark.parametrize(
    "yaml_extra,expect_error",
    [
        # 触发器各形态非法
        ("triggers:\n  - type: daily\n    time: 9:3\n", "HH:MM"),
        ("triggers:\n  - type: daily\n", "HH:MM"),
        ("triggers:\n  - type: interval\n    minutes: 0\n", "1-1440"),
        ("triggers:\n  - type: interval\n    minutes: 2000\n", "1-1440"),
        ("triggers:\n  - type: interval\n", "1-1440"),
        ("triggers:\n  - type: cron\n    expr: '* * * *'\n", "expr 非法"),
        ("triggers:\n  - type: event\n    event: nonsense\n", "event 必须"),
        ("triggers:\n  - type: event\n", "event 必须"),
        ("triggers:\n  - type: mysterious\n", "type 必须"),
        ("triggers: not-a-list\n", "列表"),
    ],
)
def test_triggers_invalid(tmp_path, yaml_extra, expect_error):
    d = _write_plugin(tmp_path, _BASE_V2 + yaml_extra)
    r = validate_plugin_dir(d)
    assert not r.ok
    assert any(expect_error in e for e in r.errors), r.errors


def test_triggers_need_v2(tmp_path):
    d = _write_plugin(
        tmp_path,
        _BASE_V2.replace("api_version: 2", "api_version: 1")
        + 'triggers:\n  - type: daily\n    time: "09:00"\n',
    )
    r = validate_plugin_dir(d)
    assert not r.ok
    assert any("api_version: 2" in e for e in r.errors)


def test_write_back_needs_v2(tmp_path):
    d = _write_plugin(
        tmp_path, _BASE_V2.replace("api_version: 2", "api_version: 1") + "write_back: true\n"
    )
    r = validate_plugin_dir(d)
    assert not r.ok
    assert any("api_version: 2" in e for e in r.errors)


def test_service_with_triggers_rejected(tmp_path):
    d = _write_plugin(
        tmp_path,
        _BASE_V2.replace("type: script", "type: service")
        + "triggers:\n  - type: event\n    event: startup\n",
    )
    r = validate_plugin_dir(d)
    assert not r.ok
    assert any("仅支持 script" in e for e in r.errors)


# ==========================================
# v2.1：命名入参 params
# ==========================================


def test_params_valid(tmp_path):
    d = _write_plugin(
        tmp_path,
        _BASE_V2
        + """\
params:
  - name: target
    default: "all"
    description: 作用目标
  - name: level
""",
    )
    r = validate_plugin_dir(d)
    assert r.ok, r.error_text()
    ps = r.manifest.params
    assert [p.name for p in ps] == ["target", "level"]
    assert ps[0].default == "all"
    assert ps[0].description == "作用目标"
    assert ps[1].default == ""
    assert ps[1].description == ""


def test_fixture_param_echo_valid():
    r = validate_plugin_dir(FIXTURES / "param-echo")
    assert r.ok, r.error_text()
    assert [p.name for p in r.manifest.params] == ["target", "level"]
    assert r.manifest.params[0].default == "all"
    assert r.manifest.args == ["--mode=echo"]


@pytest.mark.parametrize(
    "yaml_extra,expect_error",
    [
        ("params:\n  - name: a\n  - name: a\n", "重复"),
        ("params:\n  - default: x\n", "name 必填"),
        ("params:\n  - target\n", "mapping"),
        ("params: not-a-list\n", "列表"),
        # variadic 只允许最后一个参数
        ("params:\n  - name: a\n    variadic: true\n  - name: b\n", "variadic"),
    ],
)
def test_params_invalid(tmp_path, yaml_extra, expect_error):
    d = _write_plugin(tmp_path, _BASE_V2 + yaml_extra)
    r = validate_plugin_dir(d)
    assert not r.ok
    assert any(expect_error in e for e in r.errors), r.errors


def test_params_variadic_last_ok(tmp_path):
    d = _write_plugin(
        tmp_path,
        _BASE_V2 + "params:\n  - name: a\n  - name: b\n    variadic: true\n",
    )
    r = validate_plugin_dir(d)
    assert r.ok, r.error_text()
    assert r.manifest.params[0].variadic is False
    assert r.manifest.params[1].variadic is True


def test_params_need_v2(tmp_path):
    d = _write_plugin(
        tmp_path,
        _BASE_V2.replace("api_version: 2", "api_version: 1")
        + 'params:\n  - name: target\n',
    )
    r = validate_plugin_dir(d)
    assert not r.ok
    assert any("api_version: 2" in e for e in r.errors)


def test_service_with_params_rejected(tmp_path):
    d = _write_plugin(
        tmp_path,
        _BASE_V2.replace("type: script", "type: service")
        + "params:\n  - name: target\n",
    )
    r = validate_plugin_dir(d)
    assert not r.ok
    assert any("仅支持 script" in e for e in r.errors)


def test_trigger_describe():
    from zentray.plugins.models import PluginTrigger

    assert PluginTrigger(TriggerType.DAILY, time="09:30").describe() == "每日 09:30"
    assert PluginTrigger(TriggerType.INTERVAL, minutes=30).describe() == "每 30 分钟"
    assert (
        PluginTrigger(TriggerType.EVENT, event=TriggerEvent.TASK_DONE).describe()
        == "事件: 任务完成"
    )
