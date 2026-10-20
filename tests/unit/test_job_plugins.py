"""朝闻/暮省插件：清单校验 + 参数预设 + 存量调度迁移 + 脚本生成。"""
import datetime as dt
import importlib.util
import json
from pathlib import Path

import pytest

from zentray.plugins.legacy_scheduling import MARKER, migrate_legacy_scheduling
from zentray.plugins.manifest import validate_plugin_dir

_BUNDLED = Path(__file__).resolve().parents[2] / "bundled_plugins"


def _load_script(pid: str):
    spec = importlib.util.spec_from_file_location(f"_plug_{pid}", _BUNDLED / pid / f"{pid}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _manifest(pid: str):
    r = validate_plugin_dir(_BUNDLED / pid)
    assert r.ok, r.errors
    return r.manifest


# ==========================================
# 清单与脚本可执行（调度参数已删，仅运行时参数）
# ==========================================


@pytest.mark.parametrize("pid", ["chaowen", "musheng"])
def test_manifests_valid_and_runtime_params_only(pid):
    m = _manifest(pid)
    assert [p.name for p in m.params] == ["save_local"]
    assert not hasattr(m, "triggers")
    assert not hasattr(m, "description")
    # Linux 下 entry 必须可执行（loader 校验规则）
    assert (Path(m.work_path) / m.entry).stat().st_mode & 0o111


# ==========================================
# 存量调度迁移：参数预设 → 关联周期任务（一次性，幂等）
# ==========================================


class _Repo(list):
    def find_all(self):
        return list(self)

    def save_all(self, templates):
        self[:] = templates


@pytest.fixture
def state_file(tmp_data_dir, monkeypatch):
    from zentray.plugins import legacy_scheduling

    f = tmp_data_dir / "plugin_triggers.json"
    monkeypatch.setattr(legacy_scheduling, "STATE_FILE", f)
    return f


def _write_state(path, authorized=None):
    path.write_text(
        json.dumps({"authorized": authorized or {}, "watermarks": {}, "legacy_migrated": True}),
        encoding="utf-8",
    )


def test_migrate_builds_templates_from_presets(tmp_data_dir, state_file):
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager.reload()
    sm.ops.param_presets["chaowen"] = {
        "period": "weekly", "time": "09:30", "weekday": "5",
        "skip_weekends": "false", "skip_holidays": "true",
    }
    sm.ops.param_presets["musheng"] = {"period": "daily", "time": "23:45"}
    sm.save()
    _write_state(state_file, authorized={"chaowen": True, "musheng": True})

    repo = _Repo()
    migrate_legacy_scheduling(repo)

    assert len(repo) == 2
    cw = next(t for t in repo if t.plugin_id == "chaowen")
    assert cw.base_title == "朝闻" and cw.periodicity == "weekly"
    assert cw.deadline_weekday == 4  # 周五（0=周一）
    assert cw.due_time == "09:30" and cw.popup_at_due is True
    assert cw.skip_holidays is True  # skip_holidays=true
    ms = next(t for t in repo if t.plugin_id == "musheng")
    assert ms.periodicity == "daily" and ms.due_time == "23:45"
    assert ms.skip_holidays is False and ms.deadline_weekday is None
    # 文件打标记停读
    assert json.loads(state_file.read_text())[MARKER] is True


def test_migrate_idempotent_and_marker_short_circuits(tmp_data_dir, state_file):
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager.reload()
    sm.ops.param_presets["chaowen"] = {"period": "daily", "time": "08:00"}
    sm.save()
    _write_state(state_file, authorized={"chaowen": True})

    repo = _Repo()
    migrate_legacy_scheduling(repo)
    assert len(repo) == 1
    migrate_legacy_scheduling(repo)  # 标记已打：短路
    assert len(repo) == 1

    # 标记丢失重跑：同名关联模板去重，不重复建
    raw = json.loads(state_file.read_text())
    raw[MARKER] = False
    state_file.write_text(json.dumps(raw), encoding="utf-8")
    migrate_legacy_scheduling(repo)
    assert len(repo) == 1


def test_migrate_skips_unauthorized_or_presetless(tmp_data_dir, state_file):
    from zentray.services.settings_manager import SettingsManager

    sm = SettingsManager.reload()
    sm.ops.param_presets["chaowen"] = {"period": "daily", "time": "08:00"}
    sm.ops.param_presets["musheng"] = {"period": "daily", "time": "abc"}  # 坏时刻
    sm.save()
    _write_state(state_file, authorized={"chaowen": False})  # 曾拒绝自动运行

    repo = _Repo()
    migrate_legacy_scheduling(repo)
    assert repo == []  # 拒绝/坏时刻/无预设（musheng 无效时刻）均不建
    assert json.loads(state_file.read_text())[MARKER] is True


def test_migrate_no_state_file_is_noop(tmp_data_dir, state_file):
    repo = _Repo()
    migrate_legacy_scheduling(repo)
    assert repo == [] and not state_file.exists()


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
