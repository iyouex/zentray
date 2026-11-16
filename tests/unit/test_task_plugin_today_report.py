# tests/unit/test_task_plugin_today_report.py
"""任务详情页「当天已运行→查看报告」：runs 过滤 API + TaskForm 按钮接线。"""
import json

from zentray.api.handlers import _plugin_runs


def _seed_runs(tmp_data_dir, runs):
    # 调用时取 config.DATA_DIR（fixture 已 patch）——模块级 from-import 会绑定
    # 原始路径把种子写进真实数据目录（2026-11-16 事故实录，同 D4 迟绑定教训）
    from zentray import config

    d = config.DATA_DIR / "ops_runs"
    d.mkdir(parents=True, exist_ok=True)
    (d / "last.json").write_text("{}", encoding="utf-8")
    for i, r in enumerate(runs):
        (d / f"20261116T09000{i}.json").write_text(
            json.dumps(r, ensure_ascii=False), encoding="utf-8"
        )


def _run(plugin, task, started, ok=True):
    return {
        "id": plugin,
        "name": plugin,
        "run_id": f"r-{plugin}-{started}",
        "started_at": started,
        "ok": ok,
        "summary": "s",
        "result_text": "RESULT ok",
        "trigger": "task_popup",
        "task_id": task,
        "time": started,
    }


def test_runs_filter_by_plugin_task_today(tmp_data_dir):
    _seed_runs(
        tmp_data_dir,
        [
            _run("chaowen", "t1", "2026-11-16T08:00:00"),
            _run("chaowen", "t1", "2026-11-15T08:00:00"),  # 昨天
            _run("chaowen", "t2", "2026-11-16T08:00:00"),  # 其他任务
            _run("musheng", "t1", "2026-11-16T08:00:00"),  # 其他插件
            _run("chaowen", "", "2026-11-16T09:00:00"),  # 无关联任务（面板手动跑）
        ],
    )
    # 任务详情页组合过滤：今天 + 本插件 + 本任务 → 恰 1 条且是今天的
    code, body = _plugin_runs(
        {"plugin_id": "chaowen", "task_id": "t1", "today": "2026-11-16", "limit": 5}
    )
    assert code == 200
    assert [i["run_id"] for i in body["items"]] == ["r-chaowen-2026-11-16T08:00:00"]
    # 无今天记录的任务 → 空（详情页只显示「运行」按钮）
    code, body = _plugin_runs(
        {"plugin_id": "chaowen", "task_id": "t9", "today": "2026-11-16", "limit": 5}
    )
    assert body["items"] == []
    # 单维过滤仍可用
    code, body = _plugin_runs({"plugin_id": "chaowen", "limit": 10})
    assert body["count"] == 4
    code, body = _plugin_runs({"today": "2026-11-15"})
    assert body["count"] == 1


def test_taskform_report_wiring():
    from pathlib import Path

    s = (Path(__file__).resolve().parents[2] / "web/src/views/TaskForm.vue").read_text(
        encoding="utf-8"
    )
    assert "listPluginRuns" in s, "详情页须引入 runs 查询"
    assert "refreshTodayRun" in s and "today: new Date().toISOString().slice(0, 10)" in s
    assert "v-if=\"todayRun\"" in s and "查看报告" in s, "当天有运行才显示查看报告"
    assert 'reportVisible = true' in s and "todayRun.result_text" in s, "报告弹窗展示正文"
    c = (Path(__file__).resolve().parents[2] / "web/src/api/client.js").read_text(
        encoding="utf-8"
    )
    assert "plugin_id" in c and "today" in c, "listPluginRuns 须支持过滤参数"
