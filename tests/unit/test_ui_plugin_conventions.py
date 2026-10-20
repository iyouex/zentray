"""设置窗四页重设计·插件页约定回归：设置页回归纯管理。

插件行仅四动作（说明 / 参数预设 / 编辑 / 删除）；调度规则编辑器、运行按钮、
运行历史、自动运行授权、简介已随「插件随任务调度」重设计（2026-10-20）移除——
插件唯一自动触发源是所关联任务的弹窗时刻。
"""
from __future__ import annotations

from pathlib import Path

_SETTINGS = (Path(__file__).resolve().parents[2] / "web" / "src" / "views" / "Settings.vue").read_text(
    encoding="utf-8"
)


def test_plugin_page_no_schedule_editor():
    # 触发规则属于插件 manifest，设置页不再提供覆盖层编辑器
    for token in ("triggerDrafts", "saveTriggerRules", "resetTriggerRules", "opsRuleSaving"):
        assert token not in _SETTINGS, f"设置页不应再有调度规则编辑器残留：{token}"


def test_plugin_page_no_run_or_history():
    # 运行与服务启停在托盘插件面板；历史/报告/日志同在面板「记录」标签
    for token in ("onOpsRun", "opsRuns", "opsRunBusy", "listPluginRuns", "getPluginRunLog", "openPluginReport"):
        assert token not in _SETTINGS, f"设置页不应再运行插件/看历史：{token}"


def test_plugin_page_no_sort_radios():
    # 个位数插件规模，固定名称排序
    for token in ("opsSortKey", "opsSortDir", "sortedOpsItems"):
        assert token not in _SETTINGS, "插件列表不应有排序控件残留"


def test_plugin_row_four_actions():
    assert "已安装插件" in _SETTINGS
    assert "plug-actions" in _SETTINGS
    assert "toggleOpsEdit" in _SETTINGS  # 编辑与参数预设共用展开面板
    for label in (">说明<", ">参数预设<", ">编辑<", ">删除<"):
        assert label in _SETTINGS, f"插件行动作缺失：{label}"


def test_plugin_row_name_and_tags():
    # 行=名称+标签组（类型/分类/写回），无简介行/触发标签/授权入口
    assert ":color=\"p.type === 'service' ? 'orangered' : 'green'\"" in _SETTINGS
    assert 'v-if="p.category" size="small" color="cyan"' in _SETTINGS
    assert 'v-if="p.write_back" size="small" color="purple"' in _SETTINGS
    for dead in ("plug-desc", "plug-auto", "plug-dot", "trigLabel", "manifest_triggers"):
        assert dead not in _SETTINGS, f"插件行残留已删展示元素：{dead}"


def test_authorize_and_description_ui_removed():
    # 授权随调度删除：关联任务即授权；简介一并删除
    for dead in ("onOpsAuthorize", "authorizePlugin", "自动运行授权", "p.description"):
        assert dead not in _SETTINGS, f"插件授权/简介残留：{dead}"


def test_plugin_import_and_failbox_kept():
    assert "plug-import-actions" in _SETTINGS  # 导入收敛两行
    assert "plug-fail-box" in _SETTINGS  # 校验失败提示保留


def test_plugin_page_no_dead_css():
    for token in (
        ".ops-collapse",
        ".ops-pane-title",
        ".plug-toolbar",
        ".plug-scroll",
        ".plug-auth",
        ".plug-meta-edit",
        ".trig-row",
        ".plug-manifest",
        ".pc-runs",
        ".pc-log",
        ".pc-hint",
        ".plugin-field-label",
    ):
        assert token not in _SETTINGS, f"插件页死样式残留：{token}"
