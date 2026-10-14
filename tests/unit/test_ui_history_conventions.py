"""设置-历史页重设计约定（源码级断言）。

对应 spec docs/superpowers/specs/2026-10-14-settings-4pages-redesign-design.md 第 4 节：
筛选 chips 三组主色 pill、日期栏相对标签+左竖条选中态、时间轴行 4 元素去边框 tag、
AI 报告 renderMd 渲染（md-body）。
"""
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "web" / "src" / "components" / "HistoryPanel.vue"


def _read() -> str:
    return SRC.read_text(encoding="utf-8")


def test_ai_report_rendered_as_markdown_body():
    s = _read()
    assert "md-body" in s, "AI 报告应使用 md-body prose 容器"
    assert "renderMd" in s, "AI 报告应经 renderMd 渲染"
    assert "md-pre" not in s, "旧的 md-pre 裸排应清除（元数据 JSON 用 meta-pre）"


def test_filter_chips_groups_paradigm():
    s = _read()
    assert "<a-checkbox" not in s, "筛选应从 checkbox 改为 button chips"
    assert "FILTER_GROUPS" in s, "筛选项应按 任务/番茄/AI 三组呈现"
    for label in ("'任务'", "'番茄'", "'AI'"):
        assert label in s, f"缺少筛选分组 {label}"
    assert 'class="hchip"' in s and "aria-pressed" in s, "chips 应为主色 pill 范式（aria-pressed）"
    assert "toggleGroup" in s, "组头应支持整组开关"


def test_date_column_relative_labels_and_selection():
    s = _read()
    assert "今天" in s and "昨天" in s and "周" in s, "日期栏应使用相对标签（今天/昨天/MM-DD 周X）"
    assert ".date-item.active::before" in s, "日期选中态应有左竖条（全局选中范式）"


def test_timeline_row_four_elements_no_arco_tag():
    s = _read()
    assert "a-tag" not in s, "时间轴行应去 a-tag 边框，动作改纯文字着色"
    assert "tl-dot" in s, "时间轴行应有类别色点"
    assert "actionColorVar" in s, "动作着色应走 Arco 调色板 token"


def test_detail_keeps_data_and_empty_states():
    s = _read()
    # 与头部重复的 k-v 块删除；详情/元数据保留
    assert ">操作<" not in s and ">时间<" not in s, "详情栏不应再渲染与头部重复的 操作/时间 块"
    assert ">详情<" in s and ">元数据<" in s
    for text in ("暂无记录", "该日无匹配记录", "选择时间轴上的记录查看详情", "暂无报告正文"):
        assert text in s, f"空态文案应保留：{text}"
