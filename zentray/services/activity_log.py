"""操作活动日志：精确到秒的任务操作 + 查询。"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from zentray.config import DATA_DIR

logger = logging.getLogger(__name__)

_LOG_FILE = DATA_DIR / "activity.jsonl"
_lock = threading.Lock()


def _ensure_parent() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def log_event(
    category: str,
    action: str,
    title: str = "",
    detail: str = "",
    *,
    meta: Optional[Dict[str, Any]] = None,
) -> None:
    """
    追加一条日志。
    category: task | ai | system
    action: create/update/progress/done/abandon/select/plan/review/...
    time 精确到秒（ISO 本地时间）。
    """
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "category": category,
        "action": action,
        "title": title or "",
        "detail": detail or "",
        "meta": meta or {},
    }
    try:
        _ensure_parent()
        line = json.dumps(entry, ensure_ascii=False)
        with _lock:
            with open(_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError as e:
        logger.warning("activity log write failed: %s", e)


def query_events(
    *,
    category: Optional[str] = None,
    days: int = 30,
    limit: int = 500,
) -> List[dict]:
    """按时间倒序返回日志。"""
    if not _LOG_FILE.exists():
        return []
    since = datetime.now() - timedelta(days=max(1, int(days or 30)))
    items: List[dict] = []
    try:
        with _lock:
            lines = _LOG_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = obj.get("time") or ""
        try:
            dt = datetime.fromisoformat(t)
        except ValueError:
            continue
        if dt < since:
            # 文件按时间追加，更早的可提前结束
            # 但中间可能有乱序，仍继续扫有限行
            continue
        if category and category != "all" and obj.get("category") != category:
            continue
        items.append(obj)
        if len(items) >= limit:
            break
    return items


def pomodoro_today_stats() -> tuple:
    """今日 (番茄数, 专注分钟)：托盘菜单融合按钮与速览面板共用。"""
    today = datetime.now().strftime("%Y-%m-%d")
    count = minutes = 0
    for ev in query_events(category="pomodoro", days=1, limit=500):
        if (ev.get("time") or "")[:10] != today:
            continue
        if ev.get("action") != "pomodoro_done":
            continue
        count += 1
        minutes += int((ev.get("meta") or {}).get("minutes") or 0)
    return count, minutes


def list_ai_reports(days: int = 90) -> List[dict]:
    """列出 reviews/ 下 AI 报告文件，带日期-类型-序号标签。"""
    reviews = DATA_DIR / "reviews"
    if not reviews.is_dir():
        return []
    since = datetime.now() - timedelta(days=max(1, int(days or 90)))
    raw: List[dict] = []
    for p in reviews.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".md", ".txt", ".log"):
            continue
        try:
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
        except OSError:
            continue
        if mtime < since:
            continue
        kind, date_str, seq = _parse_report_name(p.name, mtime)
        raw.append(
            {
                "name": p.name,
                "kind": kind,
                "date": date_str,
                "seq": seq,
                "mtime": mtime.isoformat(timespec="seconds"),
                "size": p.stat().st_size,
                "_mtime": mtime,
            }
        )

    # 按 (date, kind) 分组，按时间升序重算序号；同日多次计划/复盘 #1 #2 …
    from collections import defaultdict

    groups: Dict[tuple, List[dict]] = defaultdict(list)
    for item in raw:
        groups[(item["date"], item["kind"])].append(item)
    out: List[dict] = []
    for (_date, kind), items in groups.items():
        items.sort(key=lambda x: x["_mtime"])
        for i, item in enumerate(items, start=1):
            item["seq"] = i
            kind_cn = "计划" if kind == "plan" else "复盘"
            item["label"] = f"{item['date']}-{kind_cn}-#{i}"
            del item["_mtime"]
            out.append(item)
    out.sort(key=lambda x: x["mtime"], reverse=True)
    return out


def _parse_report_name(name: str, mtime: datetime) -> tuple:
    """从文件名解析 kind/date/seq 初值。"""
    stem = name.rsplit(".", 1)[0]
    # plan-YYYY-MM-DD / plan-YYYY-MM-DD-N
    if stem.startswith("plan-"):
        rest = stem[5:]
        return "plan", *_split_date_seq(rest, mtime)
    # review-YYYY-MM-DD / review-YYYY-MM-DD-N
    if stem.startswith("review-"):
        rest = stem[7:]
        return "review", *_split_date_seq(rest, mtime)
    # 旧名 YYYY-MM-DD.md → 复盘
    if len(stem) >= 10 and stem[4] == "-" and stem[7] == "-":
        date_part = stem[:10]
        seq = 1
        if len(stem) > 10 and stem[10] == "-" and stem[11:].isdigit():
            seq = int(stem[11:])
        return "review", date_part, seq
    return "review", mtime.strftime("%Y-%m-%d"), 1


def _split_date_seq(rest: str, mtime: datetime) -> tuple:
    if len(rest) >= 10 and rest[4] == "-" and rest[7] == "-":
        date_part = rest[:10]
        seq = 1
        if len(rest) > 10 and rest[10] == "-" and rest[11:].isdigit():
            seq = int(rest[11:])
        return date_part, seq
    return mtime.strftime("%Y-%m-%d"), 1


def read_ai_report(name: str) -> Optional[str]:
    """安全读取 reviews 下报告内容。"""
    if not name or "/" in name or "\\" in name or ".." in name:
        return None
    path = (DATA_DIR / "reviews" / name).resolve()
    reviews = (DATA_DIR / "reviews").resolve()
    try:
        path.relative_to(reviews)
    except ValueError:
        return None
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None
