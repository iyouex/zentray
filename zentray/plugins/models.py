"""插件清单数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class PluginType(str, Enum):
    SCRIPT = "script"
    SERVICE = "service"


@dataclass(frozen=True)
class PluginParam:
    """manifest 声明的命名入参（api_version: 2，仅 script；顺序即 argv 顺序）。

    variadic: 可变长度参数（仅允许声明在最后一个参数上）——
    值可为字符串列表，按顺序逐个追加进 argv，空串跳过。
    """

    name: str
    default: str = ""
    description: str = ""
    variadic: bool = False


def resolve_param_values(
    params: List[PluginParam],
    presets: Optional[Dict[str, Any]],
    explicit: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """参数值优先级：显式传入 > 预设 > manifest default（托盘弹窗/API/触发共用）。

    variadic 参数的值可为 str 或 List[str]（多值按序展开追加 argv，空串过滤）。
    """
    presets = presets or {}
    explicit = explicit or {}
    values: List[str] = []
    for p in params:
        raw = explicit.get(p.name, presets.get(p.name, p.default))
        if p.variadic:
            items = raw if isinstance(raw, list) else [raw]
            values.extend(str(v) for v in items if str(v) != "")
        else:
            values.append(str(raw))
    return values


@dataclass(frozen=True)
class PluginManifest:
    """已解析的 plugin.yaml。"""

    id: str
    name: str
    version: str
    type: PluginType
    api_version: int
    entry: str
    root: Path
    args: List[str] = field(default_factory=list)
    workdir: Optional[str] = None
    timeout_sec: int = 300
    env: Dict[str, str] = field(default_factory=dict)
    category: str = ""
    params: List[PluginParam] = field(default_factory=list)
    write_back: bool = False

    @property
    def entry_path(self) -> Path:
        return (self.root / self.entry).resolve()

    @property
    def work_path(self) -> Path:
        if self.workdir:
            return (self.root / self.workdir).resolve()
        return self.root.resolve()
