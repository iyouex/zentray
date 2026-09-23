"""二级分类领域模型与标题前缀组装（纯函数，无 UI 依赖）。"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from typing import List, Optional, Tuple

# 全局括号预设：(显示名, left, right) — 包住「一级-二级」整体
WRAP_PRESETS: List[Tuple[str, str, str]] = [
    ("[]", "[", "]"),
    ("【】", "【", "】"),
    ("<>", "<", ">"),
    ("（）", "（", "）"),
]


@dataclass
class SecondaryCategory:
    id: str
    name: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SecondaryCategory":
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            name=(data.get("name") or "").strip() or "未命名",
        )


@dataclass
class PrimaryCategory:
    id: str
    name: str
    secondaries: List[SecondaryCategory] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "secondaries": [s.to_dict() for s in self.secondaries],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PrimaryCategory":
        secs = [
            SecondaryCategory.from_dict(s)
            for s in (data.get("secondaries") or [])
            if isinstance(s, dict)
        ]
        return cls(
            id=data.get("id") or str(uuid.uuid4()),
            name=(data.get("name") or "").strip() or "未命名",
            secondaries=secs,
        )

    def find_secondary(self, secondary_id: Optional[str]) -> Optional[SecondaryCategory]:
        if not secondary_id:
            return None
        return next((s for s in self.secondaries if s.id == secondary_id), None)

    def find_secondary_by_name(self, name: str) -> Optional[SecondaryCategory]:
        name = (name or "").strip()
        return next((s for s in self.secondaries if s.name == name), None)

    def add_secondary(self, name: str) -> SecondaryCategory:
        name = (name or "").strip() or "未命名"
        existing = self.find_secondary_by_name(name)
        if existing:
            return existing
        sec = SecondaryCategory(id=str(uuid.uuid4()), name=name)
        self.secondaries.append(sec)
        return sec


@dataclass
class CategorySettings:
    """分类体系设置。"""

    enabled_secondary: bool = True
    # 全局括号：包住「一级-二级」整体，如 [工作-需求]
    wrap_left: str = "["
    wrap_right: str = "]"
    # 一二级之间的分隔符（默认 -）
    level_separator: str = "-"
    primary_list: List[PrimaryCategory] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "enabled_secondary": self.enabled_secondary,
            "wrap_left": self.wrap_left,
            "wrap_right": self.wrap_right,
            "level_separator": self.level_separator,
            "primary_list": [p.to_dict() for p in self.primary_list],
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "CategorySettings":
        if not data:
            return default_category_settings()
        primaries = [
            PrimaryCategory.from_dict(p)
            for p in (data.get("primary_list") or [])
            if isinstance(p, dict)
        ]
        if not primaries:
            primaries = default_category_settings().primary_list

        # 兼容旧配置：从第一个一级的 wrap 迁移到全局
        wl = data.get("wrap_left")
        wr = data.get("wrap_right")
        if (wl is None or wr is None) and data.get("primary_list"):
            first = data["primary_list"][0] if data["primary_list"] else {}
            if isinstance(first, dict):
                if wl is None:
                    wl = first.get("wrap_left", "【")
                if wr is None:
                    wr = first.get("wrap_right", "】")

        # 旧默认 · 仍可读；新默认 -
        sep = data.get("level_separator")
        if sep is None:
            sep = "-"
        return cls(
            enabled_secondary=bool(data.get("enabled_secondary", True)),
            wrap_left=str(wl if wl is not None else "["),
            wrap_right=str(wr if wr is not None else "]"),
            level_separator=str(sep),
            primary_list=primaries,
        )

    def find_primary(self, primary_id: Optional[str]) -> Optional[PrimaryCategory]:
        if not primary_id:
            return None
        return next((p for p in self.primary_list if p.id == primary_id), None)

    def find_primary_by_name(self, name: str) -> Optional[PrimaryCategory]:
        name = (name or "").strip()
        return next((p for p in self.primary_list if p.name == name), None)

    def ensure_primary_named(self, name: str) -> PrimaryCategory:
        name = (name or "").strip() or "工作"
        found = self.find_primary_by_name(name)
        if found:
            return found
        p = PrimaryCategory(id=str(uuid.uuid4()), name=name)
        self.primary_list.append(p)
        return p

    def wrap(self, text: str) -> str:
        return f"{self.wrap_left}{text}{self.wrap_right}"


def default_category_settings() -> CategorySettings:
    def _p(name: str) -> PrimaryCategory:
        return PrimaryCategory(id=str(uuid.uuid4()), name=name)

    return CategorySettings(
        primary_list=[_p("工作"), _p("生活"), _p("学习")],
    )


def resolve_primary_secondary(
    settings: CategorySettings,
    *,
    primary_id: Optional[str] = None,
    secondary_id: Optional[str] = None,
    category_name: Optional[str] = None,
) -> Tuple[Optional[PrimaryCategory], Optional[SecondaryCategory]]:
    primary = settings.find_primary(primary_id)
    if primary is None and category_name:
        primary = settings.find_primary_by_name(category_name)
    secondary = None
    if primary and settings.enabled_secondary:
        secondary = primary.find_secondary(secondary_id)
    return primary, secondary


def format_category_prefix(
    settings: CategorySettings,
    *,
    primary_id: Optional[str] = None,
    secondary_id: Optional[str] = None,
    category_name: Optional[str] = None,
) -> str:
    """
    组装分类前缀：一对括号包住整体，一二级用分隔符连接。

    示例：[工作-需求评审]  或仅  [工作]
    """
    primary, secondary = resolve_primary_secondary(
        settings,
        primary_id=primary_id,
        secondary_id=secondary_id,
        category_name=category_name,
    )
    if primary is None:
        name = (category_name or "").strip()
        return settings.wrap(name) if name else ""

    if settings.enabled_secondary and secondary is not None:
        sep = settings.level_separator if settings.level_separator is not None else "-"
        inner = f"{primary.name}{sep}{secondary.name}"
    else:
        inner = primary.name
    return settings.wrap(inner)


def format_display_title_with_category(
    raw_title: str,
    settings: CategorySettings,
    *,
    primary_id: Optional[str] = None,
    secondary_id: Optional[str] = None,
    category_name: Optional[str] = None,
    overdue_prefix: str = "",
) -> str:
    """分类前缀 + 空格 + 可选逾期前缀 + 标题。"""
    cat = format_category_prefix(
        settings,
        primary_id=primary_id,
        secondary_id=secondary_id,
        category_name=category_name,
    )
    title = raw_title or ""
    if overdue_prefix:
        title = f"{overdue_prefix}{title}"
    if not cat:
        return title
    return f"{cat} {title}"
