"""扫描插件目录并加载通过校验的插件。"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from zentray.plugins.manifest import ValidationResult, validate_plugin_dir
from zentray.plugins.models import PluginManifest

logger = logging.getLogger(__name__)


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    source: str  # bundled | user
    validation: ValidationResult


class PluginLoader:
    """扫描多个根目录；同 id 时后扫描的覆盖先前（用户覆盖内置）。"""

    def __init__(self) -> None:
        self._plugins: Dict[str, LoadedPlugin] = {}
        self._failures: List[tuple[Path, ValidationResult]] = []

    @property
    def plugins(self) -> List[LoadedPlugin]:
        return list(self._plugins.values())

    @property
    def failures(self) -> List[tuple[Path, ValidationResult]]:
        return list(self._failures)

    def get(self, plugin_id: str) -> Optional[LoadedPlugin]:
        return self._plugins.get(plugin_id)

    def scan(
        self,
        *,
        bundled_dir: Optional[Path] = None,
        user_dir: Optional[Path] = None,
        load_bundled: bool = True,
        load_user: bool = True,
    ) -> List[LoadedPlugin]:
        self._plugins.clear()
        self._failures.clear()

        if load_bundled and bundled_dir:
            self._scan_root(Path(bundled_dir), source="bundled")
        if load_user and user_dir:
            self._scan_root(Path(user_dir), source="user")

        return self.plugins

    def _scan_root(self, root: Path, *, source: str) -> None:
        if not root.is_dir():
            logger.debug("插件目录不存在，跳过: %s", root)
            return
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if not (child / "plugin.yaml").is_file():
                continue
            result = validate_plugin_dir(child)
            if not result.ok or result.manifest is None:
                self._failures.append((child, result))
                logger.warning(
                    "插件校验失败 %s: %s", child, result.error_text()
                )
                continue
            prev = self._plugins.get(result.manifest.id)
            if prev:
                logger.info(
                    "插件 id=%s 由 %s 覆盖 %s",
                    result.manifest.id,
                    source,
                    prev.source,
                )
            self._plugins[result.manifest.id] = LoadedPlugin(
                manifest=result.manifest,
                source=source,
                validation=result,
            )
