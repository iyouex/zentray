"""朝闻/暮省插件（原内置每日计划/复盘迁移）：清单校验 + 周期参数调度 + 迁移 + 脚本生成。"""
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from zentray.plugins import triggers
from zentray.plugins.manifest import validate_plugin_dir
from zentray.plugins.models import TriggerType

_BUNDLED = Path(__file__).resolve().parents[2] / "bundled_plugins"


def _load_script(pid: str):
    spec = importlib.util.spec_from_file_location(f"_plug_{pid}", _BUNDLED / pid / f"{pid}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _state_file(tmp_data_dir, monkeypatch):
    monkeypatch.setattr(triggers, "STATE_FILE", tmp_data_dir / "plugin_triggers.json")


def _manifest(pid: str):
    r = validate_plugin_dir(_BUNDLED / pid)
    assert r.ok, r.errors
    return r.manifest


# ==========================================
# 清单与脚本可执行
# ==========================================


@pytest.mark.parametrize("pid", ["chaowen", "musheng"])
def test_manifests_valid_and_period_params(pid):
    m = _manifest(pid)
    assert [p.name for p in m.params] == [
        "period", "time", "weekday", "day_of_month",
        "skip_weekends", "skip_holidays", "save_local",
    ]
    assert m.triggers and m.triggers[0].type == TriggerType.DAILY
    # Linux 下 entry 必须可执行（loader 校验规则）
    assert (Path(m.work_path) / m.entry).stat().st_mode & 0o111


# ==========================================
# 周期参数 → 触发器推导（纯函数）
# ==========================================


def test_period_raw_translation():
    base = {"period": "daily", "time": "08:05"}
    assert triggers._period_raw(base) == {"type": "daily", "time": "08:05"}
    assert triggers._period_raw({"time": "9:5"}) == {"type": "daily", "time": "09:05"}
    assert triggers._period_raw({"period": "weekly", "time": "23:30", "weekday": "7"}) == {
        "type": "cron", "expr": "30 23 * * 7",
    }
    assert triggers._period_raw({"period": "monthly", "time": "00:15", "day_of_month": "15"}) == {
        "type": "cron", "expr": "15 0 15 * *",
    }
    # 非法值 → None（回落 manifest）
    assert triggers._period_raw({"time": "abc"}) is None
    assert triggers._period_raw({"time": "25:00"}) is None
    assert triggers._period_raw({"period": "weekly", "weekday": "x"}) is None


def test_scheduled_triggers_derived_from_presets(tmp_data_dir):
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager.reload()
    sm.ops.param_presets["chaowen"] = {"period": "weekly", "time": "09:30", "weekday": "5"}
    plug = SimpleNamespace(manifest=_manifest("chaowen"))
    out = triggers.scheduled_triggers(plug)
    assert [t.type for t in out] == [TriggerType.CRON]
    assert out[0].expr == "30 9 * * 5"


def test_scheduled_triggers_invalid_falls_back_to_manifest(tmp_data_dir):
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager.reload()
    sm.ops.param_presets["chaowen"] = {"time": "99:99"}
    plug = SimpleNamespace(manifest=_manifest("chaowen"))
    out = triggers.scheduled_triggers(plug)
    assert out == plug.manifest.triggers


def test_scheduled_triggers_non_period_plugin_untouched(tmp_data_dir):
    m = _manifest("chaowen")
    object.__setattr__(m, "params", [p for p in m.params if p.name != "period"])
    out = triggers.scheduled_triggers(SimpleNamespace(manifest=m))
    assert out == m.triggers  # 走 effective_triggers 原路径（无覆盖层）


def test_skip_today_weekend_gate(tmp_data_dir):
    from zentray.services.settings_manager import SettingsManager

    plug = SimpleNamespace(manifest=_manifest("musheng"))
    sat = dt.datetime(2026, 10, 17, 23, 30)  # 周六
    sm = SettingsManager.reload()
    sm.ops.param_presets["musheng"] = {"skip_weekends": "true"}
    assert triggers._skip_today(plug, sat) is True
    sm.ops.param_presets["musheng"] = {"skip_weekends": "false", "skip_holidays": "false"}
    assert triggers._skip_today(plug, sat) is False
    # 无预设 → manifest 默认 false → 不跳
    sm.ops.param_presets.pop("musheng")
    assert triggers._skip_today(plug, sat) is False
    # 非 period 插件不受门控
    m = plug.manifest
    object.__setattr__(m, "params", [p for p in m.params if p.name != "period"])
    sm.ops.param_presets["musheng"] = {"skip_weekends": "true"}
    assert triggers._skip_today(plug, sat) is False


# ==========================================
# 一次性迁移
# ==========================================


def test_migrate_legacy_jobs(tmp_data_dir):
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager.reload()
    sm.ai.plan.enabled = False
    sm.ai.plan.trigger_hour = 9
    sm.ai.plan.trigger_minute = 30
    sm.ai.plan.skip_weekends = True
    sm.ai.review.enabled = True
    sm.ai.review.trigger_hour = 23
    sm.ai.review.trigger_minute = 45

    triggers.migrate_legacy_jobs()

    sm2 = SettingsManager.reload()
    assert sm2.ops.param_presets["chaowen"] == {
        "period": "daily", "time": "09:30", "weekday": "1", "day_of_month": "1",
        "skip_weekends": "true", "skip_holidays": "false", "save_local": "true",
    }
    assert sm2.ops.param_presets["musheng"]["time"] == "23:45"
    state = triggers.load_state()
    assert state.authorized == {"chaowen": False, "musheng": True}
    assert state.legacy_migrated is True

    # 幂等：再次迁移为 no-op（legacy_migrated 短路，已落盘值不变）
    sm2.ops.param_presets["chaowen"]["time"] = "10:15"
    triggers.migrate_legacy_jobs()
    assert SettingsManager.reload().ops.param_presets["chaowen"]["time"] == "09:30"

    # 标记丢失时预设守卫生效：用户预设不被旧值覆盖
    sm3 = SettingsManager.reload()
    sm3.ops.param_presets["chaowen"]["time"] = "10:15"
    sm3.save()
    st = triggers.load_state()
    st.legacy_migrated = False
    triggers.save_state(st)
    triggers.migrate_legacy_jobs()
    assert SettingsManager.reload().ops.param_presets["chaowen"]["time"] == "10:15"


# ==========================================
# 脚本生成（报告写入 reviews/，RESULT 协议）
# ==========================================


def _fake_post(reply="好的，这是计划。"):
    def post(url, body, headers, timeout):
        assert url.endswith("/chat/completions")
        assert headers["Authorization"].startswith("Bearer ")
        return 200, json.dumps(
            {"choices": [{"message": {"content": reply}}]}
        ).encode("utf-8")

    return post


def test_chaowen_run_writes_plan_report(tmp_data_dir, monkeypatch):
    for k in ("AI_API_KEY", "AI_API_BASE_URL", "AI_MODEL_NAME"):
        monkeypatch.delenv(k, raising=False)
    mod = _load_script("chaowen")
    (tmp_data_dir / "settings.json").write_text(
        json.dumps({
            "ai": {
                "api_profiles": [{"id": "p1", "api_key": "sk-t", "base_url": "http://x/v1", "model": "m"}],
                "active_api_id": "p1",
                "plan": {"active_style_id": "gentle",
                         "styles": [{"id": "gentle", "name": "温柔", "system_prompt": "温和规划"}]},
            },
            "ops": {"param_presets": {"chaowen": {"save_local": "true"}}},
        }),
        encoding="utf-8",
    )
    (tmp_data_dir / "active_tasks.json").write_text(
        json.dumps([{"title": "写周报", "priority": "high", "deadline": "2026-10-20",
                     "subtasks": [{"status": "done"}, {"status": "active"}]}]),
        encoding="utf-8",
    )
    lines = []
    now = dt.datetime(2026, 10, 19, 8, 0)
    assert mod.run(tmp_data_dir, post=_fake_post(), now=now, out=lines.append) == 0
    assert any(l.startswith("RESULT ok") for l in lines)
    rep = tmp_data_dir / "reviews" / "plan-2026-10-19.md"
    txt = rep.read_text(encoding="utf-8")
    assert "ZenTray 每日计划 (2026-10-19)" in txt
    assert "AI 计划（温柔）" in txt and "好的，这是计划。" in txt
    assert "写周报" in txt and "子任务 1/2" in txt
    # 同日第二次 → 自增序号
    assert mod.run(tmp_data_dir, post=_fake_post(), now=now, out=lines.append) == 0
    assert (tmp_data_dir / "reviews" / "plan-2026-10-19-2.md").exists()


def test_musheng_run_review_report_and_legacy_name(tmp_data_dir, monkeypatch):
    for k in ("AI_API_KEY", "AI_API_BASE_URL", "AI_MODEL_NAME"):
        monkeypatch.delenv(k, raising=False)
    mod = _load_script("musheng")
    (tmp_data_dir / "settings.json").write_text("{}", encoding="utf-8")
    (tmp_data_dir / "active_tasks.json").write_text(
        json.dumps([{"title": "救火", "priority": "high", "category": "工作", "deadline": "2026-10-20"}]),
        encoding="utf-8",
    )
    (tmp_data_dir / "archive" / "2026-10-19.log").write_text("- 10:00 完成A", encoding="utf-8")
    lines = []
    now = dt.datetime(2026, 10, 19, 23, 30)
    # 无 API key → AI 未生成但仍写报告（与旧行为一致）
    assert mod.run(tmp_data_dir, post=_fake_post(), now=now, out=lines.append) == 0
    txt = (tmp_data_dir / "reviews" / "review-2026-10-19.md").read_text(encoding="utf-8")
    assert "ZenTray 禅定复盘" in txt and "生成失败或未配置" in txt
    assert "救火" in txt  # 归档记录进 prompt，报告主体为锐评+高优先任务
    # 旧命名 YYYY-MM-DD.md 计为第 1 篇 → 下一篇为 -2
    (tmp_data_dir / "reviews" / "2026-10-19.md").write_text("legacy", encoding="utf-8")
    (tmp_data_dir / "reviews" / "review-2026-10-19.md").unlink()
    mod.run(tmp_data_dir, post=_fake_post(), now=now, out=lines.append)
    assert (tmp_data_dir / "reviews" / "review-2026-10-19-2.md").exists()


def test_chaowen_save_local_false_skips_file(tmp_data_dir, monkeypatch):
    for k in ("AI_API_KEY", "AI_API_BASE_URL", "AI_MODEL_NAME"):
        monkeypatch.delenv(k, raising=False)
    mod = _load_script("chaowen")
    (tmp_data_dir / "settings.json").write_text(
        json.dumps({"ops": {"param_presets": {"chaowen": {"save_local": "false"}}}}),
        encoding="utf-8",
    )
    (tmp_data_dir / "active_tasks.json").write_text("[]", encoding="utf-8")
    lines = []
    assert mod.run(tmp_data_dir, post=_fake_post(), now=dt.datetime(2026, 10, 19, 8, 0), out=lines.append) == 0
    assert not (tmp_data_dir / "reviews").exists() or not list((tmp_data_dir / "reviews").glob("plan-*.md"))
