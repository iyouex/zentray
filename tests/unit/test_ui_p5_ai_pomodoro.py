"""UI 四页重设计（P5）约定回归：AI 能力页线性三段 / 番茄钟满宽网格。

四页重设计 spec（2026-10-14）：AI 页拆 a-tabs 改「模型接入→场景能力→每日计划与复盘」
线性三段，模型接入为前置首块；番茄钟页去 420px 窄列改满宽多栏。
本文件防止 a-tabs 结构与窄列钳制在两页回流。
"""
from __future__ import annotations

import re
from pathlib import Path

_WEB = Path(__file__).resolve().parents[2] / "web" / "src"
_SETTINGS = (_WEB / "views" / "Settings.vue").read_text(encoding="utf-8")
_JOB = (_WEB / "components" / "JobEditor.vue").read_text(encoding="utf-8")


def _ai_section() -> str:
    """模板中 AI 页 <template v-if="mainKey === 'ai'"> 段。"""
    m = re.search(
        r'<template v-if="mainKey === \'ai\'">.*?</template>\s*\n\s*<!-- 通知', _SETTINGS, re.S
    )
    assert m, "AI 页模板段未找到"
    return m.group(0)


def test_ai_page_no_tabs_linear_sections():
    ai = _ai_section()
    assert "a-tabs" not in ai, "AI 页不应再有 a-tabs（改为线性三段）"
    assert "aiTab" not in _SETTINGS, "aiTab 状态应随 a-tabs 一并删除"
    assert "is-ai" not in _SETTINGS, "AI 页特殊滚动 is-ai 应删除（回归普通滚动）"
    # 线性三段顺序：模型接入（前置首块）→ 场景能力 → 每日计划与复盘
    i_api = ai.index("模型接入")
    i_feat = ai.index("场景能力")
    i_jobs = ai.index("每日计划与复盘")
    assert i_api < i_feat < i_jobs, "AI 页三段顺序应为 模型接入→场景能力→计划与复盘"
    assert 'class="ai-jobs"' in ai, "计划与复盘应为双栏容器 ai-jobs"
    assert "api-dot" in ai, "模型接入行首应有状态点 api-dot（替换文字 tag）"


def test_job_editor_headless_prop():
    assert "headless" in _JOB, "JobEditor 应支持 headless prop"
    assert "v-if=\"!headless\"" in _JOB, "headless 时不应渲染启用行"
    assert "field-line" in _JOB, "JobEditor 应为 field-line 行式"


def _pomo_section() -> str:
    """模板中番茄钟页 <template v-else-if="mainKey === 'pomodoro'"> 段。"""
    m = re.search(
        r'<template v-else-if="mainKey === \'pomodoro\'">.*?</template>', _SETTINGS, re.S
    )
    assert m, "番茄钟页模板段未找到"
    return m.group(0)


def test_pomodoro_full_width_grid():
    pomo = _pomo_section()
    assert "max-width" not in pomo, "番茄钟页 420px 窄列钳制应移除（满宽网格）"
    assert ".pomo-grid" in _SETTINGS, "番茄钟页应为满宽网格 pomo-grid"
    assert "minmax(380px, 1fr)" in _SETTINGS, "pomo-grid 应为 auto-fit 自适应列"
    assert "activePreset" in _SETTINGS, "节奏预设应有选中态反馈 activePreset"
    assert ".pomo-preset.on" in _SETTINGS, "预设选中态样式应存在（chips 范式）"
