"""跨设备数据迁移：导出 / 导入（替换）/ 归档打包 / 自动备份轮转。"""

from __future__ import annotations

import json
import logging
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union

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

# —— 选择性恢复：include 子键（key:sub）——
# tasks 按 task_type 分区 / settings 按顶层节 / reviews 按文件名前缀；
# archive 按月份（YYYY-MM，动态）/ plugins 按插件目录名（动态，对包内容校验）
SETTINGS_SECTIONS: List[str] = [
    "polling",
    "pomodoro",
    "nightly",
    "notification",
    "ai",
    "categories",
    "quick_add",
    "appearance",
    "backup",
    "ops",
]
TASK_TYPES: List[str] = ["one-time", "periodic_instance"]
REVIEW_PREFIXES: List[str] = ["plan", "review"]

_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_STATIC_SUBKEYS: Dict[str, Set[str]] = {
    "tasks": set(TASK_TYPES),
    "settings": set(SETTINGS_SECTIONS),
    "reviews": set(REVIEW_PREFIXES),
}

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
    """导出侧：仅接受裸键（整类备份）。"""
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


def _parse_include_entry(raw: str) -> Optional[Tuple[str, Optional[str]]]:
    """'tasks' → ('tasks', None)；'tasks:one-time' → ('tasks', 'one-time')。
    plugins（目录名）/archive（月份）子键只做形状校验，存在性对包内容动态校验。"""
    text = str(raw or "").strip()
    if not text:
        return None
    if ":" in text:
        key, _, sub = text.partition(":")
        key = key.strip().lower()
        sub = sub.strip()
        if not key or not sub:
            return None
    else:
        key, sub = text.lower(), None
    if key not in INCLUDE_MAP:
        return None
    if sub is not None:
        if key in _STATIC_SUBKEYS and sub not in _STATIC_SUBKEYS[key]:
            return None
        if key == "archive" and not _MONTH_RE.match(sub):
            return None
        if key not in _STATIC_SUBKEYS and key not in ("archive", "plugins"):
            return None
    return key, sub


def parse_include_entries(include: Optional[Sequence[str]]) -> List[Tuple[str, Optional[str]]]:
    """导入侧：解析 (key, sub) 列表，去重；裸键吞并同键子键。"""
    out: List[Tuple[str, Optional[str]]] = []
    seen: Set[Tuple[str, Optional[str]]] = set()
    for raw in include or []:
        entry = _parse_include_entry(raw)
        if entry is None or entry in seen:
            continue
        seen.add(entry)
        out.append(entry)
    bare = {k for k, s in out if s is None}
    return [e for e in out if e[1] is None or e[0] not in bare]


def _fmt_entry(key: str, sub: Optional[str]) -> str:
    return f"{key}:{sub}" if sub is not None else key


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


def _probe_encrypted(src: Path, password: Optional[str]) -> Optional[str]:
    """加密包密码探针；返回错误 message 或 None（未加密直通）。
    pyzipper 带 HMAC 校验，错密码抛 RuntimeError 而非解出脏数据。"""
    if not is_encrypted_zip(src):
        return None
    if not password:
        return "备份已加密，请输入密码"
    try:
        with pyzipper.AESZipFile(src, "r") as zf:
            zf.setpassword(password.encode("utf-8"))
            member = next((n for n in zf.namelist() if not n.endswith("/")), None)
            if member:
                zf.read(member)
    except RuntimeError:
        return "密码错误或备份文件损坏"
    return None


def _entry_in_zip(entry: Tuple[str, Optional[str]], names: Set[str]) -> bool:
    key, sub = entry
    rel = INCLUDE_MAP[key]
    if sub is None:
        return rel in names or any(n.startswith(rel.rstrip("/") + "/") for n in names)
    if key in ("tasks", "settings"):
        return rel in names
    if key in ("reviews", "archive"):
        return any(n.startswith(f"{rel}/{sub}-") for n in names)
    # plugins：目录成员
    return any(n.startswith(f"{rel}/{sub}/") for n in names)


def _replace_tasks_partition(zf, root: Path, rel: str, types: Set[str]) -> str:
    """分区替换：勾选类型的任务整块换成备份内容，其余类型保持本地。"""
    backup = json.loads(zf.read(rel).decode("utf-8"))
    local_path = root / rel
    local: list = []
    if local_path.exists():
        try:
            local = json.loads(local_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "local_read_error"  # 本地损坏时不盲目覆盖
    keep = [t for t in local if (t.get("task_type") or "one-time") not in types]
    picked = [t for t in backup if (t.get("task_type") or "one-time") in types]
    local_path.write_text(json.dumps(keep + picked, ensure_ascii=False, indent=2), encoding="utf-8")
    return "replaced_partition"


def _replace_settings_partition(zf, root: Path, rel: str, sections: List[str]) -> str:
    backup = json.loads(zf.read(rel).decode("utf-8"))
    applied = [s for s in sections if s in backup]
    if not applied:
        return "missing_in_zip"
    local_path = root / rel
    local: dict = {}
    if local_path.exists():
        try:
            local = json.loads(local_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "local_read_error"
    local.update({s: backup[s] for s in applied})
    local_path.write_text(json.dumps(local, ensure_ascii=False, indent=2), encoding="utf-8")
    return "replaced_partition"


def _replace_dir_partition(zf, root: Path, rel: str, subs: Sequence[str], *, exact: bool) -> str:
    """目录分区替换：plugins 按目录名精确匹配；reviews/archive 按前缀 sub- 匹配。"""

    def _hit(name: str) -> bool:
        first = name[len(rel) + 1 :].split("/", 1)[0]
        if exact:
            return first in set(subs)
        return any(first.startswith(s + "-") for s in subs)

    def _rm(p: Path) -> None:
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        else:
            try:
                p.unlink()
            except OSError:
                pass

    members = [
        n for n in zf.namelist() if n.startswith(rel + "/") and not n.endswith("/") and _hit(n)
    ]
    base = root / rel
    if base.is_dir():
        for p in base.iterdir():
            if _hit(f"{rel}/{p.name}"):
                _rm(p)
    for name in members:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(name) as src_f, open(target, "wb") as out_f:
            shutil.copyfileobj(src_f, out_f)
    return "replaced_partition"


def _import_partition(zf, root: Path, key: str, subs: List[str]) -> str:
    rel = INCLUDE_MAP[key]
    if key == "tasks":
        return _replace_tasks_partition(zf, root, rel, set(subs))
    if key == "settings":
        return _replace_settings_partition(zf, root, rel, subs)
    return _replace_dir_partition(zf, root, rel, subs, exact=(key == "plugins"))


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
    支持子键（tasks:one-time 等）做分区替换；裸键仍为整类替换。
    导入前默认对当前数据做安全备份（明文）。
    """
    root = Path(data_dir) if data_dir else DATA_DIR
    src = Path(zip_path).expanduser().resolve()
    if not src.is_file():
        return MigrationResult(ok=False, message=f"备份文件不存在: {src}")

    # 检测顺序：flag_bits 加密位 → 密码 → manifest（加密包的 manifest 本身是密文）
    probe = _probe_encrypted(src, password)
    if probe:
        return MigrationResult(ok=False, message=probe, path=str(src))

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

    # 决定导入项：请求 ∩ 包内实际存在（裸键或子键）
    if include:
        entries = parse_include_entries(include)
    elif manifest and manifest.get("include"):
        entries = parse_include_entries(manifest["include"])
    else:
        entries = [(k, None) for k in DEFAULT_INCLUDE]
    entries = entries or [(k, None) for k in DEFAULT_INCLUDE]

    available = [e for e in entries if _entry_in_zip(e, names)]
    if not available:
        return MigrationResult(
            ok=False,
            message="备份中没有可导入的数据项",
            include=[_fmt_entry(k, s) for k, s in entries],
        )

    safety_path: Optional[str] = None
    if make_safety_backup:
        # 安全备份按父键整类快照（子键恢复也保留完整本地现场）
        safety = create_export_zip(
            sorted({k for k, _ in available}),
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
            # 裸键整类替换
            for key, _ in [e for e in available if e[1] is None]:
                rel = INCLUDE_MAP[key]
                dest = root / rel
                # 清理目标
                if dest.is_file():
                    dest.unlink()
                elif dest.is_dir():
                    shutil.rmtree(dest)

                # 提取
                members = [
                    n for n in zf.namelist() if n == rel or n.startswith(rel.rstrip("/") + "/")
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

            # 子键分区替换（同键合并执行）
            parts: Dict[str, List[str]] = {}
            for k, s in available:
                if s is not None:
                    parts.setdefault(k, []).append(s)
            for key, subs in parts.items():
                details[key] = _import_partition(zf, root, key, subs)

        return MigrationResult(
            ok=True,
            message="导入成功（替换）。建议刷新任务列表或重启应用。",
            path=str(src),
            include=[_fmt_entry(k, s) for k, s in available],
            safety_backup=safety_path,
            details=details,
        )
    except Exception as e:
        logger.exception("导入失败")
        return MigrationResult(
            ok=False,
            message=f"导入失败: {e}",
            include=[_fmt_entry(k, s) for k, s in available],
            safety_backup=safety_path,
            details=details,
        )


def _safe_json(data: Optional[bytes]) -> Optional[Union[list, dict]]:
    if data is None:
        return None
    try:
        return json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def _preview_categories(names: Set[str], blobs: Dict[str, bytes]) -> List[dict]:
    """包内各类/子类计数，供前端渲染选择性恢复勾选树。"""
    templates = _safe_json(blobs.get("periodic_templates.json"))
    tpl_title = {t.get("id"): t.get("title", "") for t in (templates or []) if isinstance(t, dict)}

    out: List[dict] = []
    for key, rel in INCLUDE_MAP.items():
        present = rel in names or any(n.startswith(rel.rstrip("/") + "/") for n in names)
        info: dict = {"key": key, "present": present}
        if present:
            if key == "tasks":
                tasks = _safe_json(blobs.get(rel)) or []
                counts = {"one-time": 0, "periodic_instance": 0}
                by_tpl: Dict[str, int] = {}
                for t in tasks:
                    if not isinstance(t, dict):
                        continue
                    tt = t.get("task_type") or "one-time"
                    if tt in counts:
                        counts[tt] += 1
                    if tt == "periodic_instance":
                        tid = str(t.get("template_id") or "(无模板)")
                        by_tpl[tid] = by_tpl.get(tid, 0) + 1
                info["counts"] = counts
                info["templates"] = [
                    {"template_id": tid, "title": tpl_title.get(tid, ""), "count": c}
                    for tid, c in sorted(by_tpl.items())
                ]
            elif key == "templates":
                info["count"] = len(_safe_json(blobs.get(rel)) or [])
            elif key == "settings":
                data = _safe_json(blobs.get(rel))
                info["sections"] = sorted(data.keys()) if isinstance(data, dict) else []
            elif key == "reviews":
                counts: Dict[str, int] = {p: 0 for p in REVIEW_PREFIXES}
                counts["other"] = 0
                for n in names:
                    if not n.startswith("reviews/"):
                        continue
                    first = n[len("reviews/") :].split("/")[0]
                    if first.startswith("plan-"):
                        counts["plan"] += 1
                    elif first.startswith("review-"):
                        counts["review"] += 1
                    elif first:
                        counts["other"] += 1
                info["counts"] = counts
            elif key == "archive":
                months: Dict[str, int] = {}
                for n in names:
                    if not n.startswith("archive/") or n.endswith("/"):
                        continue
                    month = n[len("archive/") :][:7]
                    if _MONTH_RE.match(month):
                        months[month] = months.get(month, 0) + 1
                info["months"] = [{"month": m, "files": c} for m, c in sorted(months.items())]
            elif key == "plugins":
                dirs = {
                    n[len("plugins/") :].split("/")[0]
                    for n in names
                    if n.startswith("plugins/") and not n.endswith("/")
                }
                info["plugins"] = sorted(d for d in dirs if d)
        out.append(info)
    return out


def preview_import(zip_path: str | Path, *, password: Optional[str] = None) -> dict:
    """导入预览（只读）：包内各类/子类计数 + manifest 摘要。"""
    src = Path(zip_path).expanduser().resolve()
    if not src.is_file():
        return {"ok": False, "message": f"备份文件不存在: {src}"}

    probe = _probe_encrypted(src, password)
    if probe:
        return {"ok": False, "message": probe, "needs_password": True}

    try:
        with pyzipper.AESZipFile(src, "r") as zf:
            if password:
                zf.setpassword(password.encode("utf-8"))
            names = set(zf.namelist())
            blobs: Dict[str, bytes] = {}
            for rel in (
                "active_tasks.json",
                "periodic_templates.json",
                "settings.json",
            ):
                if rel in names:
                    blobs[rel] = zf.read(rel)
    except zipfile.BadZipFile:
        return {"ok": False, "message": "不是有效的 zip 文件"}
    except Exception as e:
        return {"ok": False, "message": f"无法打开备份: {e}"}

    manifest = read_manifest(src, password=password)
    return {
        "ok": True,
        "path": str(src),
        "encrypted": is_encrypted_zip(src),
        "manifest": (
            {
                "created_at": manifest.get("created_at"),
                "app_version": manifest.get("app_version"),
                "include": manifest.get("include") or [],
            }
            if manifest
            else None
        ),
        "categories": _preview_categories(names, blobs),
    }


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
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                "encrypted": encrypted,
                "kind": _kind_of(p.name),
                "manifest": (
                    {
                        "created_at": manifest.get("created_at"),
                        "app_version": manifest.get("app_version"),
                        "include": manifest.get("include") or [],
                    }
                    if manifest
                    else None
                ),
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
