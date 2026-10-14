"""UI 重构 P2 约定回归：容器收敛 zt-block / 导航三组 / 页内分组 / 即时 pill。

P2（Settings 页重构）起容器唯一化（见 CLAUDE.md「UI 约定」段）：
设置类区块一律 section.zt-block，不再用 a-card；主导航 a-menu-item-group 三组；
性质分组 zt-group + 裸 zt-h3 组头；即时生效项行尾 zt-instant pill。
本文件防止 a-card 与旧容器类在设置页回流。
"""
from __future__ import annotations

import re
from pathlib import Path

_WEB = Path(__file__).resolve().parents[2] / "web" / "src"
_STYLES = (_WEB / "styles.css").read_text(encoding="utf-8")
_SETTINGS = (_WEB / "views" / "Settings.vue").read_text(encoding="utf-8")

# P2 废除的设置页容器/布局类
_LEGACY_CONTAINERS = (
    "compact-page",
    "compact-block",
    "compact-sep",
    "poll-block",
    "cat-page",
    "plugin-card",
    "sys-card",
)

# 主导航三组（组名 → 组内页面 key）
_NAV_GROUPS = {
    "日常工作": ("polling", "pomodoro"),
    "集成与通知": ("ai", "notify", "ops"),
    "应用与数据": ("system", "backup", "history"),
}


def test_container_classes_defined():
    for cls in (".zt-block", ".zt-block-head", ".zt-stack", ".zt-group", ".zt-instant"):
        assert cls + " {" in _STYLES, f"全局容器类 {cls} 缺失"


def test_settings_uses_zt_block_not_a_card():
    assert "<a-card" not in _SETTINGS, "Settings.vue 仍残留 a-card（P2 起容器唯一 zt-block）"
    assert 'class="zt-block' in _SETTINGS


def test_nav_grouped_into_three():
    groups = re.findall(
        r'<a-menu-item-group title="([^"]+)">(.*?)</a-menu-item-group>', _SETTINGS, re.S
    )
    assert len(groups) == 3, f"主导航应为 3 组，实际 {len(groups)}"
    by_title = dict(groups)
    for title, keys in _NAV_GROUPS.items():
        assert title in by_title, f"主导航缺分组「{title}」"
        for key in keys:
            assert f'<a-menu-item key="{key}"' in by_title[title], f"分组「{title}」缺页面 {key}"


def test_in_page_groups_and_instant_pill():
    # 组头 div/h3 两种写法并存，按 zt-h3 标签内容断言
    h3_texts = re.findall(r'<(?:div|h3)[^>]*class="zt-h3"[^>]*>([^<]+)</', _SETTINGS)
    for title in ("录入", "集成", "托盘与分类", "外观", "系统行为", "软件更新"):
        assert title in h3_texts, f"缺组头「{title}」"
    assert '<span class="zt-instant">即时</span>' in _SETTINGS, "缺「即时」pill 标记"
    # 保存条说明只管未标记项
    assert "带「即时」标记的项改动立即生效" in _SETTINGS


def test_legacy_container_classes_eradicated():
    for legacy in _LEGACY_CONTAINERS:
        assert legacy not in _SETTINGS, f"Settings.vue 仍含已废除的容器类 {legacy}"


def test_skins_style_zt_block():
    # 四皮肤把 .zt-block 纳入既有表面规则（结构同 a-card）
    themes = (_WEB / "themes").glob("*.css")
    hits = [t.name for t in themes if ".zt-block" in t.read_text(encoding="utf-8")]
    assert len(hits) >= 3, f"皮肤未覆盖 .zt-block：{hits}"
