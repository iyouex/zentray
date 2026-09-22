"""进程内文件读写工具：线程锁 + 原子写 + .bak 自愈。"""
from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_locks_guard = threading.Lock()
_path_locks: Dict[str, threading.RLock] = {}


def path_lock(filepath: Path | str) -> threading.RLock:
    """同一路径共享一把可重入锁（支持同一线程内 load+save）。"""
    p = Path(filepath)
    try:
        key = str(p.resolve())
    except OSError:
        key = str(p.absolute())
    with _locks_guard:
        if key not in _path_locks:
            _path_locks[key] = threading.RLock()
        return _path_locks[key]


def _bak_path(filepath: Path) -> Path:
    return filepath.with_suffix(filepath.suffix + ".bak")


def _restore_from_bak(filepath: Path) -> Optional[List[dict]]:
    """从 .bak 恢复主文件并返回内容；.bak 不存在或不可用则 None。"""
    bak = _bak_path(filepath)
    if not bak.exists():
        return None
    try:
        with open(bak, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return None
        try:
            shutil.copy2(bak, filepath)  # best-effort 恢复主文件
        except OSError:
            pass
        return data
    except (OSError, json.JSONDecodeError):
        return None


def load_json_list(filepath: Path) -> List[dict]:
    """读取 JSON 列表；主文件丢失/损坏时自动从 .bak 恢复（自愈）。"""
    lock = path_lock(filepath)
    with lock:
        if not filepath.exists():
            data = _restore_from_bak(filepath)
            if data is not None:
                logger.warning("数据文件丢失，已从备份恢复: %s", filepath)
                return data
            return []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            # 损坏件另存 .corrupt-<时间戳>，不覆盖 .bak；再尝试从 .bak 恢复
            corrupt = filepath.with_suffix(f"{filepath.suffix}.corrupt-{int(time.time())}")
            try:
                shutil.copy(filepath, corrupt)
            except OSError:
                pass
            data = _restore_from_bak(filepath)
            if data is not None:
                logger.warning("数据文件损坏，已从备份恢复: %s（原件存 %s）", filepath, corrupt.name)
                return data
            return []
        except OSError:
            return []


def save_json_list(filepath: Path, data: List[Any]) -> None:
    """原子写入 JSON 列表（temp + os.replace），并镜像一份 .bak 供丢失/损坏自愈。"""
    lock = path_lock(filepath)
    with lock:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        tmp = filepath.with_suffix(filepath.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, filepath)
        try:
            shutil.copy2(filepath, _bak_path(filepath))  # 留底失败不阻断保存
        except OSError:
            pass


def append_text_line(filepath: Path, line: str) -> None:
    """线程安全追加一行文本。"""
    lock = path_lock(filepath)
    with lock:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(line)
