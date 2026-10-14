"""UI 重构 P1 约定回归：字阶 token / 全局标题类落地、旧局部标题类清除、选中态统一。

P1（feature/ui-redesign）起标题/说明/选中态走全局范式（见 CLAUDE.md「UI 约定」段），
本文件防止旧范式回流：新代码不得再引入 sys-title/compact-head 等局部标题类，
a-card 标题必须走 #title 槽 + h3.zt-h3。
"""
from __future__ import annotations

import re
from pathlib import Path

_WEB = Path(__file__).resolve().parents[2] / "web" / "src"
_STYLES = (_WEB / "styles.css").read_text(encoding="utf-8")
_VIEWS = {p.name: p.read_text(encoding="utf-8") for p in (_WEB / "views").glob("*.vue")}

# P1 废除的局部标题/说明类（模板与样式都不得再出现）
_LEGACY = (
    "sys-title",
    "compact-head",
    "block-title",
    "ch-title",
    "api-name",
    "feat-name",
    "hint-sm",
)


def test_type_scale_tokens_and_global_classes():
    for token in ("--zt-t1", "--zt-t2", "--zt-t3", "--zt-note"):
        assert token in _STYLES, f"字阶 token {token} 缺失"
    for cls in (".zt-h3", ".zt-h4", ".hint"):
        assert cls + " {" in _STYLES, f"全局类 {cls} 缺失"
    # 页标题挂接 t1 token
    assert "font-size: var(--zt-t1)" in _STYLES


def test_legacy_title_classes_eradicated():
    for name, src in _VIEWS.items():
        for legacy in _LEGACY:
            assert legacy not in src, f"{name} 仍含已废除的局部类 {legacy}"


def test_cards_use_zt_h3_title_slot():
    for name, src in _VIEWS.items():
        offenders = re.findall(r"<a-card[^>]*\stitle=", src)
        assert not offenders, f"{name} 的 a-card 仍用 title= 属性：{offenders}"


def test_selection_state_convergence():
    # tabs：rounded 选中态全局指示条（主色文字 + 底部 2px）
    assert ".arco-tabs-nav-type-rounded .arco-tabs-tab-active::after" in _STYLES
    # 折叠行：展开左竖条
    assert ".arco-collapse-item-active > .arco-collapse-item-header::before" in _STYLES
    # 主导航：统一选中结构基础规则（Settings 独有组件）
    settings = _VIEWS["Settings.vue"]
    assert ".arco-menu-item.arco-menu-selected" in settings
    assert ".arco-menu-item.arco-menu-selected)::before" in settings
    # TaskList 筛选 chips：皮肤变体已清除，仅存统一主色 pill 基础规则
    tasklist = _VIEWS["TaskList.vue"]
    assert "zt-skin-neo .filter-row .fchip" not in tasklist
    assert "zt-skin-aurora .filter-row .fchip" not in tasklist
    assert "color-mix(in srgb, var(--color-primary) 10%, transparent)" in tasklist
