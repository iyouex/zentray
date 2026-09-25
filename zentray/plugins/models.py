"""插件清单数据模型。"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class PluginType(str, Enum):
    SCRIPT = "script"
    SERVICE = "service"


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
    description: str = ""

    @property
    def entry_path(self) -> Path:
        return (self.root / self.entry).resolve()

    @property
    def work_path(self) -> Path:
        if self.workdir:
            return (self.root / self.workdir).resolve()
        return self.root.resolve()
