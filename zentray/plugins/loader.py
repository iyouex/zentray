"""扫描插件目录并加载通过校验的插件。"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from zentray.plugins.manifest import ValidationResult, validate_plugin_dir
from zentray.plugins.models import PluginManifest

logger = logging.getLogger(__name__)

# 扫描缓存：/api/plugins 每次交互都新建 loader 全量扫描（yaml 解析 + 校验 +
# 覆盖日志刷屏），绝大多数时间目录无变化。签名 = 两根目录的一级子目录与
# plugin.yaml stat + 隐藏集合——任何插件增删改都会立刻失配走真扫描；
# TTL 仅兜底 mtime 粒度外的诡异变更。
# ponytail: 模块级单缓存；多用户目录并发切换场景出现再做 key 化
_SCAN_TTL = 5.0
_scan_cache: dict = {"sig": None, "at": 0.0, "plugins": (), "failures": ()}


def _scan_signature(bundled_dir, user_dir, hidden) -> tuple:
    parts = []
    for root, tag in ((bundled_dir, "b"), (user_dir, "u")):
        entries = []
        p = Path(root).resolve() if root else None
        entries.append(("__root__", str(p)))
        try:
            if p and p.is_dir():
                for child in sorted(p.iterdir()):
                    if not child.is_dir() or child.name.startswith("."):
                        continue
                    try:
                        st = (child / "plugin.yaml").stat()
                    except OSError:
                        entries.append((child.name, None, 0, None))
                        continue
                    # origin 标记参与签名：它影响扫描输出（覆盖副本判定），
                    # copytree 保留源 mtime，不含标记的签名会让标记变化被缓存遮蔽
                    try:
                        mk = (child / ".zentray-origin.json").stat().st_mtime_ns
                    except OSError:
                        mk = None
                    entries.append((child.name, st.st_mtime_ns, st.st_size, mk))
        except OSError:
            pass
        parts.append((tag, tuple(entries)))
    return (tuple(parts), frozenset(hidden))


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    source: str  # bundled | user
    validation: ValidationResult
    # 覆盖副本遮蔽同名内置插件（编辑示例插件时复制到用户目录产生）：
    # bundled_shadow=存在同名内置；bundled_update_available=副本带 origin 标记
    # 且复制时的应用版本 != 当前（内置的更新正被副本静默屏蔽，提示让位）。
    bundled_shadow: bool = False
    bundled_update_available: bool = False


class PluginLoader:
    """扫描多个根目录；同 id 时后扫描的覆盖先前（用户覆盖内置）。"""

    def __init__(self) -> None:
        self._plugins: Dict[str, LoadedPlugin] = {}
        self._failures: List[tuple[Path, ValidationResult]] = []
        self._bundled_ids: set = set()

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
    ) -> List[LoadedPlugin]:
        """扫描插件目录（v2：给定的目录恒扫描，无加载开关；未变时命中缓存）。"""
        try:
            from zentray.services.settings_manager import SettingsManager

            hidden = set(SettingsManager().ops.hidden_bundled)
        except Exception:
            logger.exception("隐藏内置插件设置读取失败，按空集过滤")
            hidden = set()

        sig = _scan_signature(bundled_dir, user_dir, hidden)
        if _scan_cache["sig"] == sig and time.monotonic() - _scan_cache["at"] < _SCAN_TTL:
            self._plugins = dict(_scan_cache["plugins"])
            self._failures = list(_scan_cache["failures"])
            return self.plugins

        self._plugins.clear()
        self._failures.clear()
        self._bundled_ids.clear()

        if bundled_dir:
            self._scan_root(Path(bundled_dir), source="bundled")
        if user_dir:
            self._scan_root(Path(user_dir), source="user")

        # 覆盖副本检测：用户副本遮蔽同名内置 → 标记供设置页提示让位更新。
        # origin 标记记录复制时的应用版本，与当前不同 = 内置已更新被屏蔽。
        from zentray.config import VERSION

        for pid, p in self._plugins.items():
            if p.source != "user" or pid not in self._bundled_ids:
                continue
            p.bundled_shadow = True
            try:
                raw = json.loads(
                    (p.manifest.root / ".zentray-origin.json").read_text(encoding="utf-8")
                )
            except Exception:
                continue  # 无标记（历史副本/手工放置）：仅标 shadow，不动
            if str(raw.get("copied_from_bundled_version") or "") != str(VERSION):
                p.bundled_update_available = True

        # 已删除的示例插件：包目录不动（重装会复活），扫描期隐藏。
        # 同 id 的用户副本 source=user，不受影响。
        if hidden:
            for pid in hidden:
                p = self._plugins.get(pid)
                if p is not None and p.source == "bundled":
                    del self._plugins[pid]

        _scan_cache.update(
            sig=sig,
            at=time.monotonic(),
            plugins=dict(self._plugins),
            failures=list(self._failures),
        )
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
            if source == "bundled":
                self._bundled_ids.add(result.manifest.id)
            self._plugins[result.manifest.id] = LoadedPlugin(
                manifest=result.manifest,
                source=source,
                validation=result,
            )
