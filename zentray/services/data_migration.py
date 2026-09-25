"""跨设备数据迁移：导出 / 导入（替换）/ 归档打包 / 自动备份轮转。"""
from __future__ import annotations

import json
import logging
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set

import pyzipper

from zentray.config import (
    ACTIVE_TASKS_FILE,
    ARCHIVE_DIR,
    DATA_DIR,
    PERIODIC_TEMPLATES_FILE,
    VERSION,
)

logger = logging.getLogger(__name__)

FORMAT_NAME = "zentray-backup"
FORMAT_VERSION = 1

# 自动备份专用前缀：轮转（prune）只清理此前缀，绝不碰手动导出/另存为/导入前安全备份
AUTO_PREFIX = "zentray-auto"

# include 键 → 相对 DATA_DIR 的路径（文件或目录）
INCLUDE_MAP: Dict[str, str] = {
    "tasks": "active_tasks.json",
    "templates": "periodic_templates.json",
    "settings": "settings.json",
    "history": "activity.jsonl",
    "archive": "archive",
    "reviews": "reviews",
    "env": ".env",
    "plugins": "plugins",
    "schedule": "ai_schedule_state.json",
    "holidays": "holidays.json",
}

DEFAULT_INCLUDE: List[str] = [
    "tasks",
    "templates",
    "settings",
    "history",
    "archive",
    "reviews",
]

EXPORTS_DIR_NAME = "exports"


@dataclass
class MigrationResult:
    ok: bool
    message: str = ""
    path: Optional[str] = None
    size: int = 0
    include: List[str] = field(default_factory=list)
    safety_backup: Optional[str] = None
    details: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "message": self.message,
            "path": self.path,
            "size": self.size,
            "include": self.include,
            "safety_backup": self.safety_backup,
            "details": self.details,
        }


def exports_dir(data_dir: Optional[Path] = None) -> Path:
    root = Path(data_dir) if data_dir else DATA_DIR
    d = root / EXPORTS_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def normalize_include(include: Optional[Sequence[str]]) -> List[str]:
    if not include:
        return list(DEFAULT_INCLUDE)
    seen: Set[str] = set()
    out: List[str] = []
    for raw in include:
        key = str(raw or "").strip().lower()
        if key in INCLUDE_MAP and key not in seen:
            seen.add(key)
            out.append(key)
    return out or list(DEFAULT_INCLUDE)


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _add_path_to_zip(zf: zipfile.ZipFile, src: Path, arcname: str) -> None:
    if src.is_file():
        zf.write(src, arcname)
        return
    if src.is_dir():
        empty = True
        for child in sorted(src.rglob("*")):
            if child.is_file():
                empty = False
                rel = child.relative_to(src)
                zf.write(child, f"{arcname}/{rel.as_posix()}")
        if empty:
            # 保留空目录占位
            zf.writestr(f"{arcname}/", "")


def create_export_zip(
    include: Optional[Sequence[str]] = None,
    *,
    data_dir: Optional[Path] = None,
    prefix: str = "zentray-backup",
    out_dir: Optional[Path] = None,
    out_path: Optional[Path] = None,
    password: Optional[str] = None,
) -> MigrationResult:
    """导出 zip。out_path 精确指定另存为文件；out_dir 覆盖输出目录；
    password 非空则全包 AES-256 加密（含 manifest.json）。"""
    root = Path(data_dir) if data_dir else DATA_DIR
    keys = normalize_include(include)
    if out_path is None:
        out_path = (out_dir or exports_dir(root)) / f"{prefix}-{_stamp()}.zip"
    out_path = Path(out_path).expanduser()
    details: Dict[str, str] = {}
    packed: List[str] = []

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # 带 password 才启用 WZ_AES（pyzipper 设了 encryption 又无密码会直接报错）；
        # 不加密时等价普通 zipfile 写出
        with pyzipper.AESZipFile(
            out_path,
            "w",
            compression=pyzipper.ZIP_DEFLATED,
            encryption=pyzipper.WZ_AES if password else None,
        ) as zf:
            if password:
                zf.setpassword(password.encode("utf-8"))
            for key in keys:
                rel = INCLUDE_MAP[key]
                src = root / rel
                if not src.exists():
                    details[key] = "missing"
                    continue
                _add_path_to_zip(zf, src, rel)
                packed.append(key)
                details[key] = "ok"
            manifest = {
                "format": FORMAT_NAME,
                "format_version": FORMAT_VERSION,
                "app_version": VERSION,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "include": packed,
                "requested_include": keys,
                "encrypted": bool(password),
            }
            zf.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
        size = out_path.stat().st_size
        return MigrationResult(
            ok=True,
            message="导出成功",
            path=str(out_path),
            size=size,
            include=packed,
            details=details,
        )
    except Exception as e:
        logger.exception("导出失败")
        if out_path.exists():
            try:
                out_path.unlink()
            except OSError:
                pass
        return MigrationResult(ok=False, message=f"导出失败: {e}", include=keys)


def pack_archive(
    *,
    data_dir: Optional[Path] = None,
) -> MigrationResult:
    """仅打包 archive/ 目录。"""
    root = Path(data_dir) if data_dir else DATA_DIR
    return create_export_zip(
        ["archive"],
        data_dir=root,
        prefix="zentray-archive",
    )


def is_encrypted_zip(zip_path: Path) -> bool:
    """zip 通用标志位第 0 位（ZipCrypto/AES 通用），读 infolist 即可，无需密码。"""
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            return any(info.flag_bits & 0x1 for info in zf.infolist())
    except Exception:
        return False


def read_manifest(zip_path: Path, password: Optional[str] = None) -> Optional[dict]:
    try:
        with pyzipper.AESZipFile(zip_path, "r") as zf:
            if password:
                zf.setpassword(password.encode("utf-8"))
            if "manifest.json" in zf.namelist():
                return json.loads(zf.read("manifest.json").decode("utf-8"))
    except Exception:
        logger.exception("读取 manifest 失败")
    return None


def import_replace(
    zip_path: str | Path,
    include: Optional[Sequence[str]] = None,
    *,
    data_dir: Optional[Path] = None,
    make_safety_backup: bool = True,
    password: Optional[str] = None,
) -> MigrationResult:
    """
    替换模式导入：按 include 覆盖 DATA_DIR 对应文件。
    导入前默认对当前数据做安全备份（明文）。
    """
    root = Path(data_dir) if data_dir else DATA_DIR
    src = Path(zip_path).expanduser().resolve()
    if not src.is_file():
        return MigrationResult(ok=False, message=f"备份文件不存在: {src}")

    # 检测顺序：flag_bits 加密位 → 密码 → manifest（加密包的 manifest 本身是密文）
    encrypted = is_encrypted_zip(src)
    if encrypted and not password:
        return MigrationResult(ok=False, message="备份已加密，请输入密码", path=str(src))
    if encrypted:
        # 密码探针：读任一成员（pyzipper 带 HMAC 校验，错密码抛 RuntimeError 而非解出脏数据）
        try:
            with pyzipper.AESZipFile(src, "r") as zf:
                zf.setpassword(password.encode("utf-8"))
                member = next(
                    (n for n in zf.namelist() if not n.endswith("/")), None
                )
                if member:
                    zf.read(member)
        except RuntimeError:
            return MigrationResult(
                ok=False, message="密码错误或备份文件损坏", path=str(src)
            )

    try:
        with pyzipper.AESZipFile(src, "r") as zf:
            if password:
                zf.setpassword(password.encode("utf-8"))
            names = set(zf.namelist())
    except zipfile.BadZipFile:
        return MigrationResult(ok=False, message="不是有效的 zip 文件")
    except Exception as e:
        return MigrationResult(ok=False, message=f"无法打开备份: {e}")

    manifest = read_manifest(src, password=password)
    if manifest and manifest.get("format") not in (None, FORMAT_NAME):
        return MigrationResult(
            ok=False,
            message=f"不支持的备份格式: {manifest.get('format')}",
        )

    # 决定导入键：请求 ∩ 包内实际存在
    if include:
        keys = normalize_include(include)
    elif manifest and manifest.get("include"):
        keys = normalize_include(manifest["include"])
    else:
        keys = list(DEFAULT_INCLUDE)

    available: List[str] = []
    for key in keys:
        rel = INCLUDE_MAP[key]
        if rel in names or any(n.startswith(rel.rstrip("/") + "/") for n in names):
            available.append(key)
    if not available:
        return MigrationResult(ok=False, message="备份中没有可导入的数据项", include=keys)

    safety_path: Optional[str] = None
    if make_safety_backup:
        safety = create_export_zip(
            available,
            data_dir=root,
            prefix="zentray-pre-import",
        )
        if safety.ok:
            safety_path = safety.path
        else:
            logger.warning("安全备份失败，仍继续导入: %s", safety.message)

    details: Dict[str, str] = {}
    try:
        with pyzipper.AESZipFile(src, "r") as zf:
            if password:
                zf.setpassword(password.encode("utf-8"))
            for key in available:
                rel = INCLUDE_MAP[key]
                dest = root / rel
                # 清理目标
                if dest.is_file():
                    dest.unlink()
                elif dest.is_dir():
                    shutil.rmtree(dest)

                # 提取
                members = [
                    n
                    for n in zf.namelist()
                    if n == rel or n.startswith(rel.rstrip("/") + "/")
                ]
                if not members:
                    details[key] = "missing_in_zip"
                    continue

                # 单文件
                if rel in members and not rel.endswith("/"):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(rel) as src_f, open(dest, "wb") as out_f:
                        shutil.copyfileobj(src_f, out_f)
                    details[key] = "replaced_file"
                    continue

                # 目录
                dest.mkdir(parents=True, exist_ok=True)
                for name in members:
                    if name.endswith("/"):
                        (root / name).mkdir(parents=True, exist_ok=True)
                        continue
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as src_f, open(target, "wb") as out_f:
                        shutil.copyfileobj(src_f, out_f)
                details[key] = "replaced_dir"

        return MigrationResult(
            ok=True,
            message="导入成功（替换）。建议刷新任务列表或重启应用。",
            path=str(src),
            include=available,
            safety_backup=safety_path,
            details=details,
        )
    except Exception as e:
        logger.exception("导入失败")
        return MigrationResult(
            ok=False,
            message=f"导入失败: {e}",
            include=available,
            safety_backup=safety_path,
            details=details,
        )


def backup_dir_from_settings() -> Path:
    """设置的自定义备份目录；空或不可写则回落默认 exports。"""
    from zentray.services.settings_manager import SettingsManager

    raw = ""
    try:
        raw = (SettingsManager().backup.dir or "").strip()
    except Exception:
        pass
    d = Path(raw).expanduser() if raw else exports_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("自定义备份目录不可用，回落默认 exports: %s", e)
        d = exports_dir()
    return d


_KIND_PREFIXES: List[tuple] = [
    (f"{AUTO_PREFIX}-", "auto"),
    ("zentray-pre-import-", "pre_import"),
    ("zentray-archive-", "archive"),
    ("zentray-backup-", "manual"),
]


def _kind_of(name: str) -> str:
    for prefix, kind in _KIND_PREFIXES:
        if name.startswith(prefix):
            return kind
    return "unknown"


def list_backups(*, backup_dir: Optional[Path] = None) -> List[dict]:
    """备份目录内 zip 快照列表（mtime 倒序）；加密包 manifest 读不出为 None。"""
    d = Path(backup_dir) if backup_dir else backup_dir_from_settings()
    if not d.is_dir():
        return []
    items: List[dict] = []
    for p in sorted(d.glob("*.zip"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            st = p.stat()
        except OSError:
            continue
        encrypted = is_encrypted_zip(p)
        manifest = None if encrypted else read_manifest(p)
        items.append(
            {
                "name": p.name,
                "path": str(p),
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(
                    timespec="seconds"
                ),
                "encrypted": encrypted,
                "kind": _kind_of(p.name),
                "manifest": {
                    "created_at": manifest.get("created_at"),
                    "app_version": manifest.get("app_version"),
                    "include": manifest.get("include") or [],
                }
                if manifest
                else None,
            }
        )
    return items


def delete_backup(path: str | Path, *, backup_dir: Optional[Path] = None) -> MigrationResult:
    """删除备份文件（信任边界：仅允许备份目录内的 zip）。"""
    d = (Path(backup_dir) if backup_dir else backup_dir_from_settings()).resolve()
    p = Path(path).expanduser().resolve()
    if p.parent != d or p.suffix.lower() != ".zip" or not p.is_file():
        return MigrationResult(ok=False, message="仅允许删除备份目录内的 zip 文件")
    try:
        p.unlink()
        return MigrationResult(ok=True, message="已删除", path=str(p))
    except OSError as e:
        return MigrationResult(ok=False, message=f"删除失败: {e}")


def prune_auto_backups(*, keep: int, backup_dir: Optional[Path] = None) -> int:
    """轮转：只删 zentray-auto-* 最旧的若干份，保留 keep 份。keep<=0 不轮转。"""
    if keep <= 0:
        return 0
    d = Path(backup_dir) if backup_dir else backup_dir_from_settings()
    if not d.is_dir():
        return 0
    autos = sorted(d.glob(f"{AUTO_PREFIX}-*.zip"), key=lambda x: x.stat().st_mtime)
    removed = 0
    for p in autos[: max(0, len(autos) - int(keep))]:
        try:
            p.unlink()
            removed += 1
        except OSError:
            logger.warning("轮转删除失败: %s", p)
    return removed


def run_auto_backup(
    *,
    data_dir: Optional[Path] = None,
    backup_dir: Optional[Path] = None,
) -> MigrationResult:
    """自动备份：全量默认范围（明文）导出到备份目录，成功后按 keep 轮转。"""
    from zentray.services.settings_manager import SettingsManager

    keep = 7
    try:
        keep = int(SettingsManager().backup.keep)
    except Exception:
        pass
    result = create_export_zip(
        prefix=AUTO_PREFIX,
        data_dir=data_dir,
        out_dir=backup_dir or backup_dir_from_settings(),
    )
    if result.ok:
        prune_auto_backups(keep=keep, backup_dir=backup_dir)
    return result


def list_include_options() -> List[dict]:
    """前端勾选列表。"""
    defaults = set(DEFAULT_INCLUDE)
    labels = {
        "tasks": "活跃任务",
        "templates": "周期模板",
        "settings": "应用配置",
        "history": "操作历史",
        "archive": "任务归档",
        "reviews": "AI 复盘报告",
        "env": ".env 密钥（含 API Key）",
        "plugins": "用户插件",
        "schedule": "AI 调度状态",
        "holidays": "节假日配置",
    }
    return [
        {
            "key": k,
            "label": labels.get(k, k),
            "path": rel,
            "default": k in defaults,
            "sensitive": k == "env",
        }
        for k, rel in INCLUDE_MAP.items()
    ]
