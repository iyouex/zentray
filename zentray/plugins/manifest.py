"""plugin.yaml 解析与校验门禁。"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from zentray.plugins.models import PluginManifest, PluginType

_ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_SUPPORTED_API = {1}


@dataclass
class ValidationResult:
    ok: bool
    errors: List[str] = field(default_factory=list)
    manifest: Optional[PluginManifest] = None

    def error_text(self) -> str:
        return "; ".join(self.errors)


def validate_plugin_dir(plugin_dir: str | Path) -> ValidationResult:
    """校验插件目录；通过时带解析后的 manifest。"""
    root = Path(plugin_dir).resolve()
    errors: List[str] = []

    if not root.is_dir():
        return ValidationResult(ok=False, errors=[f"不是目录: {root}"])

    yaml_path = root / "plugin.yaml"
    if not yaml_path.is_file():
        return ValidationResult(ok=False, errors=["缺少 plugin.yaml"])

    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except Exception as e:
        return ValidationResult(ok=False, errors=[f"YAML 解析失败: {e}"])

    if not isinstance(raw, dict):
        return ValidationResult(ok=False, errors=["plugin.yaml 根节点必须是 mapping"])

    return _validate_mapping(raw, root)


def _validate_mapping(raw: Dict[str, Any], root: Path) -> ValidationResult:
    errors: List[str] = []

    pid = str(raw.get("id") or "").strip()
    if not pid or not _ID_RE.match(pid):
        errors.append("id 必须匹配 [a-z0-9]+(-[a-z0-9]+)*")

    name = str(raw.get("name") or "").strip()
    if not name:
        errors.append("name 必填")

    version = str(raw.get("version") or "").strip()
    if not version:
        errors.append("version 必填")

    type_raw = str(raw.get("type") or "").strip().lower()
    if type_raw not in ("script", "service"):
        errors.append("type 必须是 script 或 service")
        ptype = PluginType.SCRIPT
    else:
        ptype = PluginType(type_raw)

    try:
        api_version = int(raw.get("api_version"))
    except (TypeError, ValueError):
        errors.append("api_version 必须是整数")
        api_version = 0
    if api_version and api_version not in _SUPPORTED_API:
        errors.append(f"不支持的 api_version={api_version}（支持 {sorted(_SUPPORTED_API)}）")

    entry = str(raw.get("entry") or "").strip()
    if not entry:
        errors.append("entry 必填")
    elif ".." in Path(entry).parts or entry.startswith(("/", "\\")) or (
        len(entry) > 1 and entry[1] == ":"
    ):
        # 禁止绝对路径与 .. 逃逸
        if ".." in Path(entry).parts:
            errors.append("entry 不得包含 '..'")
        if entry.startswith(("/", "\\")) or (len(entry) > 1 and entry[1] == ":"):
            errors.append("entry 必须是相对插件根的路径")

    args = raw.get("args") or []
    if args is None:
        args = []
    if not isinstance(args, list) or not all(isinstance(a, (str, int, float)) for a in args):
        errors.append("args 必须是字符串数组")
        args = []
    else:
        args = [str(a) for a in args]

    workdir = raw.get("workdir")
    if workdir is not None:
        workdir = str(workdir).strip() or None
        if workdir and ".." in Path(workdir).parts:
            errors.append("workdir 不得包含 '..'")

    try:
        timeout_sec = int(raw.get("timeout_sec", 300))
    except (TypeError, ValueError):
        errors.append("timeout_sec 必须是整数")
        timeout_sec = 300
    if timeout_sec < 0:
        errors.append("timeout_sec 不能为负")

    env = raw.get("env") or {}
    if not isinstance(env, dict):
        errors.append("env 必须是 mapping")
        env = {}
    else:
        env = {str(k): str(v) for k, v in env.items()}

    description = str(raw.get("description") or "").strip()

    if ptype == PluginType.SERVICE:
        # api_version=1: entry start|stop|status 约定，无需额外 commands 块
        pass

    if errors:
        return ValidationResult(ok=False, errors=errors)

    entry_path = (root / entry).resolve()
    try:
        entry_path.relative_to(root.resolve())
    except ValueError:
        return ValidationResult(ok=False, errors=["entry 解析后越出插件根目录"])

    if not entry_path.is_file():
        return ValidationResult(ok=False, errors=[f"entry 文件不存在: {entry}"])

    # P2: 可执行；Windows 仅要求存在
    if sys.platform != "win32":
        if not os.access(entry_path, os.X_OK):
            return ValidationResult(
                ok=False,
                errors=[f"entry 不可执行（请 chmod +x）: {entry}"],
            )

    if workdir:
        wd = (root / workdir).resolve()
        try:
            wd.relative_to(root.resolve())
        except ValueError:
            return ValidationResult(ok=False, errors=["workdir 越出插件根目录"])
        if not wd.is_dir():
            return ValidationResult(ok=False, errors=[f"workdir 不是目录: {workdir}"])

    manifest = PluginManifest(
        id=pid,
        name=name,
        version=version,
        type=ptype,
        api_version=api_version,
        entry=entry,
        root=root.resolve(),
        args=args,
        workdir=workdir,
        timeout_sec=timeout_sec,
        env=env,
        description=description,
    )
    return ValidationResult(ok=True, errors=[], manifest=manifest)
