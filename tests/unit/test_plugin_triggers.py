"""插件触发器测试：判定纯函数 + 授权门 + 分发布线（stub 依赖）。"""
import datetime as dt
from pathlib import Path

import pytest

from zentray.plugins import triggers
from zentray.plugins.loader import LoadedPlugin, PluginLoader
from zentray.plugins.manifest import validate_plugin_dir
from zentray.plugins.models import TriggerEvent, TriggerType

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "plugins"


@pytest.fixture(autouse=True)
def _state_file(tmp_data_dir, monkeypatch):
    monkeypatch.setattr(triggers, "STATE_FILE", tmp_data_dir / "plugin_triggers.json")
    # 隔离布线层：清依赖与授权在途表
    monkeypatch.setitem(triggers._deps, "loader", None)
    monkeypatch.setitem(triggers._deps, "runtime", None)
    monkeypatch.setitem(triggers._deps, "pomodoro", None)
    triggers._auth_pending.clear()
    yield


# ==========================================
# should_fire 纯函数
# ==========================================


def test_daily_fire_or_catch_up_and_dedup():
    from zentray.plugins.models import PluginTrigger

    t = PluginTrigger(TriggerType.DAILY, time="09:30")
    # 未到点不触发
    fire, wm = triggers.should_fire(t, dt.datetime(2026, 9, 28, 8, 0), None)
    assert not fire
    # 过点补跑
    fire, wm = triggers.should_fire(t, dt.datetime(2026, 9, 28, 10, 0), None)
    assert fire and wm == "2026-09-28"
    # 当日已触发不重复
    fire, _ = triggers.should_fire(t, dt.datetime(2026, 9, 28, 11, 0), "2026-09-28")
    assert not fire
    # 次日重新可触发（跨午夜）
    fire, _ = triggers.should_fire(t, dt.datetime(2026, 9, 29, 9, 30), "2026-09-28")
    assert fire


def test_interval_watermark():
    from zentray.plugins.models import PluginTrigger

    t = PluginTrigger(TriggerType.INTERVAL, minutes=30)
    now = dt.datetime(2026, 9, 28, 10, 0)
    # 无水位立即触发
    fire, wm = triggers.should_fire(t, now, None)
    assert fire and wm == now.isoformat(timespec="seconds")
    # 未满间隔
    fire, _ = triggers.should_fire(t, now.replace(minute=20), wm)
    assert not fire
    # 满 30 分钟
    fire, wm2 = triggers.should_fire(t, now.replace(minute=30), wm)
    assert fire
    # 损坏水位 → 触发并重置
    fire, _ = triggers.should_fire(t, now, "not-a-date")
    assert fire


def test_cron_minute_key_dedup():
    from zentray.plugins.models import PluginTrigger

    t = PluginTrigger(TriggerType.CRON, expr="*/15 * * * *")
    now = dt.datetime(2026, 9, 28, 9, 45)
    fire, wm = triggers.should_fire(t, now, None)
    assert fire and wm == "20260928_0945"
    # 同分钟不双发
    fire, _ = triggers.should_fire(t, now.replace(second=30), wm)
    assert not fire
    # 不匹配的分钟
    fire, _ = triggers.should_fire(t, now.replace(minute=50), wm)
    assert not fire
    # 下一个匹配点
    fire, wm2 = triggers.should_fire(t, dt.datetime(2026, 9, 28, 10, 0), wm)
    assert fire and wm2 == "20260928_1000"


# ==========================================
# 授权三态门 + 分发
# ==========================================


def _make_trig_plugin(tmp_path, event="task_done"):
    d = tmp_path / "trig-plug"
    d.mkdir(exist_ok=True)
    (d / "plugin.yaml").write_text(
        f"""\
id: trig-plug
name: 触发插件
version: 0.1.0
type: script
api_version: 2
entry: run.sh
triggers:
  - type: event
    event: {event}
""",
        encoding="utf-8",
    )
    sh = d / "run.sh"
    sh.write_text("#!/bin/sh\necho RESULT ok\n", encoding="utf-8")
    sh.chmod(0o755)
    r = validate_plugin_dir(d)
    assert r.ok, r.error_text()
    return r.manifest


class _StubRuntime:
    def __init__(self):
        self.calls = []

    def run_script(self, plug, *, pomodoro_active=False, task=None, trigger="manual"):
        self.calls.append((plug.manifest.id, trigger, task))
        return True


class _StubPomo:
    is_active = False


class _AuthCatcher:
    def __init__(self):
        self.requests = []

    def __call__(self, pid, name):
        self.requests.append((pid, name))


def _wire(monkeypatch, manifest, runtime, pomo=None):
    loader = PluginLoader()
    loader._plugins[manifest.id] = LoadedPlugin(
        manifest=manifest, source="user", validation=None
    )
    monkeypatch.setitem(triggers._deps, "loader", loader)
    monkeypatch.setitem(triggers._deps, "runtime", runtime)
    monkeypatch.setitem(triggers._deps, "pomodoro", pomo or _StubPomo())
    # 设置门：默认开启
    from zentray.services import settings_manager

    monkeypatch.setattr(triggers, "_ops_enabled", lambda: True)
    return loader


def test_dispatch_unauthorized_emits_and_waits(monkeypatch, tmp_path):
    manifest = _make_trig_plugin(tmp_path)
    rt = _StubRuntime()
    _wire(monkeypatch, manifest, rt)
    catcher = _AuthCatcher()
    monkeypatch.setattr(triggers._signals, "authorize_requested", _FakeSignal(catcher))

    triggers.dispatch_event("task_done")
    assert rt.calls == []  # 未授权不运行
    assert catcher.requests == [("trig-plug", "触发插件")]
    # 弹窗在途：再次事件不重复弹
    triggers.dispatch_event("task_done")
    assert len(catcher.requests) == 1


class _FakeSignal:
    """替身信号（避免测试里起 Qt 事件循环）。"""

    def __init__(self, cb):
        self._cb = cb

    def emit(self, *args):
        self._cb(*args)


def test_authorize_allow_fires_pending(monkeypatch, tmp_path):
    manifest = _make_trig_plugin(tmp_path)
    rt = _StubRuntime()
    _wire(monkeypatch, manifest, rt)
    catcher = _AuthCatcher()
    monkeypatch.setattr(triggers._signals, "authorize_requested", _FakeSignal(catcher))

    task = type("Task", (), {"id": "t1", "title": "T"})()
    triggers.dispatch_event("task_done", task)
    triggers.authorize("trig-plug", True)  # 用户点「允许」→ 补跑
    assert rt.calls == [("trig-plug", "task_done", task)]
    # 授权后静默直跑
    triggers.dispatch_event("task_done")
    assert len(rt.calls) == 2


def test_authorize_deny_persistent(monkeypatch, tmp_path):
    manifest = _make_trig_plugin(tmp_path)
    rt = _StubRuntime()
    _wire(monkeypatch, manifest, rt)
    catcher = _AuthCatcher()
    monkeypatch.setattr(triggers._signals, "authorize_requested", _FakeSignal(catcher))

    triggers.dispatch_event("task_done")
    triggers.authorize("trig-plug", False)  # 拒绝
    triggers.dispatch_event("task_done")
    triggers.dispatch_event("task_done")
    assert rt.calls == []
    assert len(catcher.requests) == 1  # 不再询问


def test_event_filter_mismatch(monkeypatch, tmp_path):
    manifest = _make_trig_plugin(tmp_path, event="startup")
    rt = _StubRuntime()
    _wire(monkeypatch, manifest, rt)
    catcher = _AuthCatcher()
    monkeypatch.setattr(triggers._signals, "authorize_requested", _FakeSignal(catcher))

    triggers.dispatch_event("task_done")  # 不匹配的事件
    assert rt.calls == [] and catcher.requests == []
    triggers.dispatch_event("startup")
    assert catcher.requests == [("trig-plug", "触发插件")]


def test_pomodoro_skip_recorded(monkeypatch, tmp_path):
    manifest = _make_trig_plugin(tmp_path)
    rt = _StubRuntime()
    pomo = _StubPomo()
    pomo.is_active = True
    _wire(monkeypatch, manifest, rt, pomo)
    triggers.authorize("trig-plug", True)
    catcher = _AuthCatcher()
    monkeypatch.setattr(triggers._signals, "authorize_requested", _FakeSignal(catcher))

    triggers.dispatch_event("task_done")
    assert rt.calls == []
    state = triggers.load_state()
    assert state.last_skip["trig-plug"]["reason"] == "pomodoro"


def test_busy_skip_recorded(monkeypatch, tmp_path):
    manifest = _make_trig_plugin(tmp_path)
    rt = _StubRuntime()
    rt.run_script = lambda *a, **k: False  # busy
    _wire(monkeypatch, manifest, rt)
    triggers.authorize("trig-plug", True)

    triggers.dispatch_event("task_done")
    state = triggers.load_state()
    assert state.last_skip["trig-plug"]["reason"] == "busy"


def test_settings_gate(monkeypatch, tmp_path):
    manifest = _make_trig_plugin(tmp_path)
    rt = _StubRuntime()
    _wire(monkeypatch, manifest, rt)
    monkeypatch.setattr(triggers, "_ops_enabled", lambda: False)  # 总开关关
    triggers.authorize("trig-plug", True)
    triggers.dispatch_event("task_done")
    assert rt.calls == []


def test_poll_timers_fires_authorized_daily(monkeypatch, tmp_path):
    from zentray.plugins.models import PluginTrigger

    manifest = _make_trig_plugin(tmp_path)
    # 追加一个 daily 触发器
    object.__setattr__(
        manifest,
        "triggers",
        list(manifest.triggers)
        + [PluginTrigger(TriggerType.DAILY, time="00:00")],
    )
    rt = _StubRuntime()
    loader = _wire(monkeypatch, manifest, rt)
    monkeypatch.setattr(triggers, "_rescan", lambda: None)
    triggers.authorize("trig-plug", True)

    triggers.poll_timers()
    ids = [c[0] for c in rt.calls]
    assert ids == ["trig-plug"]  # task_done 事件不参与定时轮询
    state = triggers.load_state()
    assert state.watermarks["trig-plug:daily:00:00"]


# ==========================================
# v2.1：调度规则覆盖层 effective_triggers
# ==========================================


def _set_overrides(overrides):
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager.reload()
    sm.ops.trigger_overrides = overrides
    return sm


def test_effective_triggers_override_replaces(tmp_path, tmp_data_dir):
    manifest = _make_trig_plugin(tmp_path)
    _set_overrides({"trig-plug": [{"type": "daily", "time": "08:30"}]})
    eff = triggers.effective_triggers("trig-plug", manifest.triggers)
    assert [t.type for t in eff] == [TriggerType.DAILY]
    assert eff[0].time == "08:30"


def test_effective_triggers_missing_falls_back(tmp_path, tmp_data_dir):
    manifest = _make_trig_plugin(tmp_path)
    _set_overrides({"other-plug": [{"type": "daily", "time": "08:30"}]})
    eff = triggers.effective_triggers("trig-plug", manifest.triggers)
    assert eff == list(manifest.triggers)


def test_effective_triggers_non_list_falls_back(tmp_path, tmp_data_dir):
    manifest = _make_trig_plugin(tmp_path)
    _set_overrides({"trig-plug": "garbage"})
    eff = triggers.effective_triggers("trig-plug", manifest.triggers)
    assert eff == list(manifest.triggers)


def test_effective_triggers_invalid_entries_dropped(tmp_path, tmp_data_dir):
    manifest = _make_trig_plugin(tmp_path)
    _set_overrides(
        {
            "trig-plug": [
                {"type": "daily", "time": "9:3"},  # 非法 time
                {"type": "interval", "minutes": 15},
            ]
        }
    )
    eff = triggers.effective_triggers("trig-plug", manifest.triggers)
    assert [t.type for t in eff] == [TriggerType.INTERVAL]
    assert eff[0].minutes == 15


def test_effective_triggers_empty_list_disables(tmp_path, tmp_data_dir):
    manifest = _make_trig_plugin(tmp_path)
    _set_overrides({"trig-plug": []})
    assert triggers.effective_triggers("trig-plug", manifest.triggers) == []


def test_event_triggers_respects_override(tmp_path, tmp_data_dir, monkeypatch):
    """manifest 声明 pomodoro_end，覆盖层改成 task_done → 事件判定跟着变。"""
    manifest = _make_trig_plugin(tmp_path, event="pomodoro_end")
    _set_overrides(
        {"trig-plug": [{"type": "event", "event": "task_done"}]}
    )
    loader = PluginLoader()
    loader._plugins[manifest.id] = LoadedPlugin(
        manifest=manifest, source="user", validation=None
    )
    plug = loader.get(manifest.id)
    assert triggers.event_triggers(plug, "task_done")
    assert triggers.event_triggers(plug, "pomodoro_end") == []
