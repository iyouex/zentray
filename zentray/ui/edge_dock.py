"""贴边托盘的几何 / 停靠状态机（平台无关，便于单测）。

坐标系：可用桌面区域左上角为 ``(0, 0)``，x 向右、y 向下；调用方传入的
``area_w/area_h`` 已排除任务栏（Windows 上即 ``availableGeometry`` 的尺寸）。

几何约定
--------
- 横向胶囊 ``H_SIZE=(392, 54)``，竖向胶囊 ``V_SIZE=(54, 348)``。
- ``ratio`` 0..1 表示沿边位置：0 = 左/上端，1 = 右/下端；0/1 时胶囊端部贴角。
- 单条边有 3 个停顿点 ``{0, .5, 1}``；四条边合起来是 4 个角 + 4 个边中点 = 8 个。
- 所有数值都是逻辑像素；DPR 换算由调用方（Qt）负责。
"""
from __future__ import annotations

from dataclasses import dataclass

EDGES = ("top", "bottom", "left", "right")
H_SIZE = (392, 54)
V_SIZE = (54, 348)
H_COMPACT = (168, 44)
V_COMPACT = (44, 168)

# 单条边的 3 个停顿点及全局名称（角点在相邻边共享）
_DETENTS = {
    "top": ((0.0, "top-left"), (0.5, "top-center"), (1.0, "top-right")),
    "bottom": ((0.0, "bottom-left"), (0.5, "bottom-center"), (1.0, "bottom-right")),
    "left": ((0.0, "top-left"), (0.5, "left-center"), (1.0, "bottom-left")),
    "right": ((0.0, "top-right"), (0.5, "right-center"), (1.0, "bottom-right")),
}

# 8 个停顿点的规范顺序（绘制/测试用）
DETENT_ORDER = (
    "top-left", "top-center", "top-right", "right-center",
    "bottom-right", "bottom-center", "bottom-left", "left-center",
)


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


@dataclass
class EdgeDock:
    """四边停靠状态：只存 ``edge`` + ``ratio``，几何全部可推导。"""

    area_w: int
    area_h: int
    edge: str = "bottom"
    ratio: float = 0.75
    magnet_px: int = 34
    release_px: int = 68
    compact: bool = False

    def __post_init__(self) -> None:
        if self.area_w <= 0 or self.area_h <= 0:
            raise ValueError("area_w/area_h must be positive")
        self.set(self.edge, self.ratio)

    # ---------------------------------------------------------------- 基础
    def size(self, edge: str | None = None) -> tuple[int, int]:
        """胶囊在当前边上的宽高（compact = 收纳边缘耳）。"""
        edge = edge or self.edge
        if self.compact:
            return V_COMPACT if edge in ("left", "right") else H_COMPACT
        return V_SIZE if edge in ("left", "right") else H_SIZE

    def span(self, edge: str | None = None) -> int:
        """沿边可滑动像素数（胶囊整体不出界）。"""
        e = edge or self.edge
        w, h = self.size(e)
        return max(1, (self.area_w - w) if e in ("top", "bottom") else (self.area_h - h))

    def set(self, edge: str, ratio: float) -> None:
        if edge not in EDGES:
            raise ValueError(f"unknown edge: {edge!r}")
        self.edge = edge
        self.ratio = _clamp(float(ratio))

    def detents(self, edge: str | None = None) -> tuple[tuple[float, str], ...]:
        return _DETENTS[edge or self.edge]

    def detent_name(self, edge: str | None = None, ratio: float | None = None) -> str | None:
        """离给定 ratio 最近的停顿点名称；不在吸附范围内返回 None。"""
        e = edge or self.edge
        r = self.ratio if ratio is None else float(ratio)
        best, best_px = None, None
        span = self.span(e)
        for d_ratio, name in self.detents(e):
            px = abs(r - d_ratio) * span
            if best_px is None or px < best_px:
                best, best_px = name, px
        return best if best_px is not None and best_px <= self.release_px else None

    # ---------------------------------------------------------------- 投影
    def project(self, x: float, y: float) -> tuple[str, float]:
        """把桌面坐标投影到最近的一条边，返回 ``(edge, ratio)``。

        胶囊整体必须留在可用区域内：ratio 0/1 对应端部贴角。
        """
        px = _clamp(float(x), 0.0, float(self.area_w))
        py = _clamp(float(y), 0.0, float(self.area_h))
        dist = {
            "top": py,
            "bottom": self.area_h - py,
            "left": px,
            "right": self.area_w - px,
        }
        # EDGES 顺序保证角上平局时优先上/下边（行为稳定、可测）
        edge = min(EDGES, key=lambda e: (dist[e], EDGES.index(e)))
        w, h = self.size(edge)
        if edge in ("top", "bottom"):
            span = self.area_w - w
            ratio = 0.5 if span <= 0 else (px - w / 2.0) / span
        else:
            span = self.area_h - h
            ratio = 0.5 if span <= 0 else (py - h / 2.0) / span
        return edge, _clamp(ratio)

    # ---------------------------------------------------------------- 吸附
    def magnetize(self, edge: str | None = None, ratio: float | None = None) -> float:
        """拖动中的软磁吸：距停顿点 <= magnet_px 时吸住，可继续拖过。"""
        e = edge or self.edge
        r = _clamp(self.ratio if ratio is None else float(ratio))
        span = self.span(e)
        best, best_px = r, None
        for d_ratio, _name in self.detents(e):
            px = abs(r - d_ratio) * span
            if px <= self.magnet_px and (best_px is None or px < best_px):
                best, best_px = d_ratio, px
        return best

    def release_snap(self, edge: str | None = None, ratio: float | None = None) -> float:
        """松手吸附：距停顿点 <= release_px 时对齐，否则保留当前位置。"""
        e = edge or self.edge
        r = _clamp(self.ratio if ratio is None else float(ratio))
        span = self.span(e)
        best, best_px = r, None
        for d_ratio, _name in self.detents(e):
            px = abs(r - d_ratio) * span
            if px <= self.release_px and (best_px is None or px < best_px):
                best, best_px = d_ratio, px
        return best

    # ---------------------------------------------------------------- 几何
    def geometry(
        self, edge: str | None = None, ratio: float | None = None
    ) -> tuple[int, int, int, int]:
        """返回可用区域坐标系下的 ``(x, y, w, h)``。"""
        e = edge or self.edge
        r = _clamp(self.ratio if ratio is None else float(ratio))
        w, h = self.size(e)
        if e == "bottom":
            return int(round((self.area_w - w) * r)), self.area_h - h, w, h
        if e == "top":
            return int(round((self.area_w - w) * r)), 0, w, h
        if e == "left":
            return 0, int(round((self.area_h - h) * r)), w, h
        return self.area_w - w, int(round((self.area_h - h) * r)), w, h

    def corner_is_shared(self, name: str) -> bool:
        """角点在相邻边共享；边中点是该边独有。"""
        return name.endswith(("-left", "-right")) and "center" not in name


def flyout_rect(
    capsule: tuple[int, int, int, int],
    area: tuple[int, int, int, int],
    edge: str,
    end: str,
    size: tuple[int, int],
) -> tuple[int, int, int, int]:
    """窄边 flyout 的屏幕矩形：贴边对齐，放不下就翻到胶囊另一侧，最后夹进可用区。

    ``capsule`` / ``area`` 都是 ``(x, y, w, h)`` 屏幕坐标；``end`` 为 ``content`` 或
    ``system``。横向停驻时面板底/顶与胶囊对齐；纵向停驻时面板左/右与胶囊对齐。
    """
    cx, cy, cw, ch = capsule
    ax, ay, aw, ah = area
    w, h = size
    if edge in ("top", "bottom"):
        x = cx - w if end == "content" else cx + cw
        if x < ax:
            x = cx + cw
        if x + w > ax + aw:
            x = cx - w
        x = max(ax, min(x, ax + aw - w))
        y = cy + ch - h if edge == "bottom" else cy
        y = max(ay, min(y, ay + ah - h))
    else:
        y = cy - h if end == "content" else cy + ch
        if y < ay:
            y = cy + ch
        if y + h > ay + ah:
            y = cy - h
        y = max(ay, min(y, ay + ah - h))
        x = cx if edge == "left" else cx + cw - w
        x = max(ax, min(x, ax + aw - w))
    return int(round(x)), int(round(y)), w, h


def event_rect(
    capsule: tuple[int, int, int, int],
    area: tuple[int, int, int, int],
    edge: str,
    size: tuple[int, int],
    gap: int = 50,
) -> tuple[int, int, int, int]:
    """事件胶囊位置：在胶囊内侧、留出 44px 箭头带 + 6px 间距，并夹进可用区。"""
    cx, cy, cw, ch = capsule
    ax, ay, aw, ah = area
    w, h = size
    if edge == "bottom":
        x = cx + cw / 2 - w / 2
        y = cy - gap - h
    elif edge == "top":
        x = cx + cw / 2 - w / 2
        y = cy + ch + gap
    elif edge == "left":
        x = cx + cw + gap
        y = cy + ch / 2 - h / 2
    else:
        x = cx - gap - w
        y = cy + ch / 2 - h / 2
    x = max(ax, min(x, ax + aw - w))
    y = max(ay, min(y, ay + ah - h))
    return int(round(x)), int(round(y)), w, h
