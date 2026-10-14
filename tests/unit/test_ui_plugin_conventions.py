"""设置窗四页重设计·插件页约定回归：设置页回归纯管理。

插件行仅四动作（说明 / 参数预设 / 编辑 / 删除）；调度规则编辑器、运行按钮、
运行历史从设置页移除（运行与历史在托盘插件面板）；自动运行授权开关保留，
它是 manifest 触发器被拒绝后的唯一恢复入口。
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


def test_plugin_row_type_dot_and_trigger_hint():
    # 行首类型色点（脚本=绿/服务=橙）+ manifest 触发的一行式提示
    assert "plug-dot" in _SETTINGS and "is-script" in _SETTINGS and "is-service" in _SETTINGS
    assert "plug-auto" in _SETTINGS and "trigLabel" in _SETTINGS


def test_authorize_switch_survives():
    # 授权被拒后设置页展开面板是唯一恢复入口
    assert "onOpsAuthorize" in _SETTINGS
    assert "自动运行授权" in _SETTINGS


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
