"""运行报告 md 落盘 + 系统打开端点。"""
import json

from zentray.api import handlers
from zentray.api.handlers import _build_run_md, _plugin_run_open


def _write_run(data_dir, run_id="20260929_120000_demo-plug", ok=True):
    runs = data_dir / "ops_runs"
    runs.mkdir(parents=True, exist_ok=True)
    report = {
        "id": "demo-plug",
        "name": "演示插件",
        "run_id": run_id,
        "started_at": "2026-09-29T12:00:00",
        "ok": ok,
        "summary": "成功",
        "result_text": "处理 3 项",
        "trigger": "manual",
        "task_id": "t-1",
        "time": "2026-09-29T12:00:42",
    }
    (runs / f"{run_id}.json").write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8"
    )
    (runs / f"{run_id}.log").write_text("$ run.sh\nLOG line", encoding="utf-8")
    return runs, report


def test_open_writes_md_and_opens(tmp_data_dir, monkeypatch):
    runs, report = _write_run(tmp_data_dir)
    opened = []
    monkeypatch.setattr(handlers, "_open_with_system", lambda p: opened.append(p))
    code, body = _plugin_run_open({"run_id": report["run_id"]})
    assert code == 200 and body["ok"] is True
    md = runs / f"{report['run_id']}.md"
    assert opened == [md]
    text = md.read_text(encoding="utf-8")
    assert "# 执行报告 · 演示插件" in text
    assert "42 秒" in text  # started 12:00:00 → ended 12:00:42
    assert "处理 3 项" in text and "LOG line" in text
    assert "`t-1`" in text


def test_open_rejects_traversal(tmp_data_dir, monkeypatch):
    monkeypatch.setattr(handlers, "_open_with_system", lambda p: None)
    code, _ = _plugin_run_open({"run_id": "../ops_runs/x"})
    assert code == 400


def test_open_missing_run(tmp_data_dir, monkeypatch):
    monkeypatch.setattr(handlers, "_open_with_system", lambda p: None)
    code, _ = _plugin_run_open({"run_id": "nope.json"})
    assert code == 404


def test_build_md_minimal_fields():
    text = _build_run_md({"name": "x", "ok": False}, "")
    assert "❌ 失败" in text and "（无）" in text and "（空日志）" in text


def test_open_html_report_directly(tmp_data_dir, monkeypatch):
    """result_text 带 .html 路径且存在 → 浏览器直开，不生成 md。"""
    runs, report = _write_run(tmp_data_dir)
    html = tmp_data_dir / "plugin_data" / "x" / "r.html"
    html.parent.mkdir(parents=True)
    html.write_text("<html></html>", encoding="utf-8")
    report["result_text"] = f"日报已生成：{html}｜12 条"
    (runs / f"{report['run_id']}.json").write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8"
    )
    opened = []
    monkeypatch.setattr(handlers, "_open_with_system", lambda p: opened.append(p))
    code, body = _plugin_run_open({"run_id": report["run_id"]})
    assert code == 200 and body["file"] == str(html)
    assert opened == [html]
    assert not (runs / f"{report['run_id']}.md").exists()


def test_open_html_path_missing_falls_back_md(tmp_data_dir, monkeypatch):
    runs, report = _write_run(tmp_data_dir)
    report["result_text"] = "报告：/nonexistent/none.html 完成"
    (runs / f"{report['run_id']}.json").write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8"
    )
    opened = []
    monkeypatch.setattr(handlers, "_open_with_system", lambda p: opened.append(p))
    code, body = _plugin_run_open({"run_id": report["run_id"]})
    assert code == 200 and body["file"].endswith(".md")
