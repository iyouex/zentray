"""贴边托盘停靠状态机（纯几何，跨平台可跑）。"""
from __future__ import annotations

import pytest

from zentray.ui.edge_dock import (
    DETENT_ORDER,
    H_SIZE,
    V_SIZE,
    EdgeDock,
    event_rect,
    flyout_rect,
)


def test_defaults_bottom_right():
    d = EdgeDock(1920, 1040)  # 1080p 扣掉 40px 任务栏
    assert d.edge == "bottom"
    assert d.ratio == 0.75
    x, y, w, h = d.geometry()
    assert (w, h) == H_SIZE
    assert x == round((1920 - 392) * 0.75)
    assert y == 1040 - 54  # 贴任务栏上缘


def test_project_bottom_center_and_clamp():
    d = EdgeDock(1920, 1040)
    assert d.project(960, 1040) == ("bottom", 0.5)
    # 角落：胶囊端部贴角，ratio 夹到 0/1（角上平局优先下边）
    assert d.project(0, 1040) == ("bottom", 0.0)
    assert d.project(1920, 1040) == ("bottom", 1.0)


def test_project_vertical_edges():
    d = EdgeDock(1920, 1040)
    assert d.project(1, 520) == ("left", 0.5)
    assert d.project(1919, 520) == ("right", 0.5)
    assert d.project(1, 0) == ("top", 0.0)  # 角上平局优先上边
    assert d.project(1920, 520) == ("right", 0.5)


def test_geometry_all_edges():
    d = EdgeDock(1920, 1040)
    assert d.geometry("top", 0.5) == ((1920 - 392) // 2, 0, 392, 54)
    assert d.geometry("bottom", 0.5) == ((1920 - 392) // 2, 1040 - 54, 392, 54)
    assert d.geometry("left", 0.5) == (0, (1040 - 348) // 2, 54, 348)
    assert d.geometry("right", 0.5) == (1920 - 54, (1040 - 348) // 2, 54, 348)
    for edge in ("top", "bottom", "left", "right"):
        _, _, w, h = d.geometry(edge, 0.0)
        x, y, _, _ = d.geometry(edge, 0.0)
        assert x >= 0 and y >= 0
        assert x + w <= 1920 and y + h <= 1040


def test_magnetize_soft_pause():
    d = EdgeDock(1920, 1040)  # span = 1528
    span = d.span("bottom")
    # 距 1.0 不足 34px -> 吸到 1.0
    near_end = 1.0 - 30 / span
    assert d.magnetize("bottom", near_end) == 1.0
    # 距 0.5 超过 34px -> 保持不变
    far_mid = 0.5 + 100 / span
    assert d.magnetize("bottom", far_mid) == pytest.approx(far_mid)
    # 中点附近 -> 0.5
    assert d.magnetize("bottom", 0.5 + 20 / span) == 0.5


def test_release_snap_uses_wider_threshold():
    d = EdgeDock(1920, 1040)
    span = d.span("bottom")
    # 60px 在 release(68) 内、但不在 magnet(34) 内 -> 松手吸附
    r = 1.0 - 60 / span
    assert d.magnetize("bottom", r) == pytest.approx(r)
    assert d.release_snap("bottom", r) == 1.0
    # 100px 之外保持
    r2 = 1.0 - 100 / span
    assert d.release_snap("bottom", r2) == pytest.approx(r2)


def test_eight_unique_detents():
    names = {name for edge in ("top", "bottom", "left", "right") for _, name in EdgeDock(1920, 1040).detents(edge)}
    assert len(names) == 8
    assert names == set(DETENT_ORDER)


def test_detent_name_and_shared_corners():
    d = EdgeDock(1920, 1040)
    assert d.detent_name("bottom", 0.0) == "bottom-left"
    assert d.detent_name("bottom", 0.5) == "bottom-center"
    assert d.detent_name("bottom", 1.0) == "bottom-right"
    assert d.detent_name("right", 0.0) == "top-right"
    assert d.detent_name("left", 1.0) == "bottom-left"
    # 距离太远 -> None
    assert d.detent_name("bottom", 0.2) is None


def test_tiny_area_does_not_divide_by_zero():
    d = EdgeDock(10, 10)
    assert d.span("bottom") == 1
    assert d.project(5, 5) == ("top", 0.5)
    assert 0 <= d.magnetize("bottom", 0.5) <= 1


def test_invalid_edge_rejected():
    d = EdgeDock(100, 100)
    with pytest.raises(ValueError):
        d.set("middle", 0.5)


def test_flyout_rect_bottom_content_and_system():
    area = (0, 0, 1920, 1040)
    cap = (1128, 1040 - 54, 392, 54)  # 底部右侧 75%
    # content 在胶囊左侧、底边对齐
    x, y, w, h = flyout_rect(cap, area, "bottom", "content", (360, 430))
    assert (x + w, y + h) == (cap[0], cap[1] + cap[3])
    assert x >= 0 and y >= 0 and y + h <= 1040
    # system 在胶囊右侧，若出界则翻到左侧
    x2, y2, w2, h2 = flyout_rect(cap, area, "bottom", "system", (236, 240))
    assert 0 <= x2 and x2 + w2 <= 1920
    assert y2 + h2 == cap[1] + cap[3]


def test_flyout_rect_flips_at_screen_edges():
    area = (0, 0, 1920, 1040)
    left_cap = (0, 1040 - 54, 392, 54)
    x, y, w, h = flyout_rect(left_cap, area, "bottom", "content", (360, 430))
    assert x >= 0 and x + w <= 1920
    right_cap = (1920 - 392, 1040 - 54, 392, 54)
    x2, y2, w2, h2 = flyout_rect(right_cap, area, "bottom", "system", (236, 240))
    assert x2 >= 0 and x2 + w2 <= 1920


def test_flyout_rect_top_and_vertical():
    area = (0, 0, 1920, 1040)
    top_cap = (760, 0, 392, 54)
    x, y, w, h = flyout_rect(top_cap, area, "top", "content", (360, 430))
    assert y == 0 and x + w == top_cap[0]
    left_cap = (0, 346, 54, 348)
    x2, y2, w2, h2 = flyout_rect(left_cap, area, "left", "content", (360, 430))
    assert x2 == 0 and 0 <= y2 and y2 + h2 <= 1040
    right_cap = (1920 - 54, 346, 54, 348)
    x3, y3, w3, h3 = flyout_rect(right_cap, area, "right", "system", (236, 240))
    assert x3 + w3 == 1920 and 0 <= y3 and y3 + h3 <= 1040


def test_bottom_moves_with_work_area():
    # 任务栏自动隐藏：工作区高度变化 → 胶囊跟随底边上移/下移
    shown = EdgeDock(1920, 1040, "bottom", 0.5)
    hidden = EdgeDock(1920, 1080, "bottom", 0.5)
    assert shown.geometry()[1] == 1040 - 54
    assert hidden.geometry()[1] == 1080 - 54


def test_flyout_rect_secondary_screen_offset():
    # 第二块屏：area 带 x 偏移，flyout 必须落在该屏内
    area = (1920, 0, 1920, 1040)
    cap = (1920 + 1128, 1040 - 54, 392, 54)
    x, y, w, h = flyout_rect(cap, area, "bottom", "content", (360, 430))
    assert 1920 <= x and x + w <= 3840
    assert y + h == 1040


def test_compact_ear_geometry():
    d = EdgeDock(1920, 1040, "bottom", 0.75)
    d.compact = True
    assert d.size() == (168, 44)
    x, y, w, h = d.geometry()
    assert (w, h) == (168, 44)
    assert y == 1040 - 44
    assert x == round((1920 - 168) * 0.75)
    d.set("left", 0.5)
    assert d.size() == (44, 168)


def test_event_rect_four_edges():
    area = (0, 0, 1920, 1040)
    bottom = (1000, 986, 392, 54)
    x, y, w, h = event_rect(bottom, area, "bottom", (300, 38))
    assert y + h <= bottom[1] - 44  # 清出箭头带
    assert 0 <= x and x + w <= 1920
    top = (760, 0, 392, 54)
    x2, y2, w2, h2 = event_rect(top, area, "top", (300, 38))
    assert y2 >= top[1] + top[3] + 44
    left = (0, 346, 54, 348)
    x3, y3, w3, h3 = event_rect(left, area, "left", (300, 38))
    assert x3 >= left[0] + left[2] + 44
    right = (1866, 346, 54, 348)
    x4, y4, w4, h4 = event_rect(right, area, "right", (300, 38))
    assert x4 + w4 <= right[0] - 44
