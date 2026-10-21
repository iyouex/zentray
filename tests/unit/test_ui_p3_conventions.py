"""UI 重构 P3 约定回归：a-card 全应用退场，容器唯一 zt-block。

P1/P2 收敛了 Settings，P3 把 TaskForm/TaskList 等其余窗口的 a-card
一并替换为 section.zt-block，并清除 styles/themes 中失效的 .arco-card
接线规则。本文件防止 a-card 与死选择器回流。
"""
from __future__ import annotations

from pathlib import Path

_WEB = Path(__file__).resolve().parents[2] / "web" / "src"


def _vue_sources():
    return {p.name: p.read_text(encoding="utf-8") for p in (_WEB / "views").glob("*.vue")}


def test_no_a_card_in_any_view():
    for name, text in _vue_sources().items():
        assert "<a-card" not in text, f"{name} 仍用 a-card（容器唯一 zt-block）"


def test_taskform_tasklist_use_zt_block():
    for name in ("TaskForm.vue", "TaskList.vue"):
        text = _vue_sources()[name]
        assert 'class="zt-block"' in text, f"{name} 缺 zt-block 容器"
        assert 'class="zt-h3"' in text, f"{name} 区块标题未用 zt-h3"


def test_no_dead_arco_card_selectors():
    # a-card 已全应用退场，styles.css 与皮肤里不应再留 .arco-card 接线
    css_files = [(_WEB / "styles.css")] + list((_WEB / "themes").glob("*.css"))
    for f in css_files:
        assert ".arco-card" not in f.read_text(encoding="utf-8"), f"{f.name} 仍含死选择器 .arco-card"


def test_taskform_calendar_rows_collapse_and_no_raw_uuid():
    # v0.7.16 两回归：日历行 minmax(0,1fr) 可收缩（否则溢出压住时间轴）；
    # 分类下拉 fallback-option=false + 回填清洗（坏 id 不再把裸 uuid 当 label）
    text = _vue_sources()["TaskForm.vue"]
    assert "minmax(0, 1fr)" in text, "日历行须可收缩到 0，杜绝溢出重叠"
    assert text.count(':fallback-option="false"') >= 2, "一级/二级分类下拉须关 fallback"
    assert "sanitizeCategoryIds" in text, "编辑回填须清洗失效分类 id"
