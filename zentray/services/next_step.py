"""下一步操作提示（贴边胶囊详情 / /glance 速览共用，纯函数便于单测）。

规则：
- 有未完成子任务 → 指向第一个未完成子任务（done+1 / total）。
- 子任务全部完成 → 提示标记任务完成。
- 没有子任务 → 推进任务本身；有截止就带上截止。
"""
from __future__ import annotations

from typing import Any


def build_next_step(task: Any, estimate_minutes: int = 25) -> dict | None:
    """把 Task（或同形对象）转成下一步提示；无任务返回 None。"""
    if task is None:
        return None
    title = (getattr(task, "title", "") or "").strip() or "当前任务"
    raw_subs = getattr(task, "subtasks", None) or []
    subs = [s for s in raw_subs if isinstance(s, dict)]
    total = len(subs)
    done = sum(1 for s in subs if s.get("status") == "done")
    active = [s for s in subs if s.get("status") not in ("done", "abandoned")]

    if active:
        first = active[0]
        idx = min(total, done + 1)
        name = (first.get("title") or "未命名").strip()
        return {
            "kind": "subtask",
            "text": f"完成子任务 {idx}/{total}「{name}」",
            "hint": f"预计 {estimate_minutes} 分钟",
            "subtask_id": first.get("id"),
        }

    if total and done >= total:
        return {
            "kind": "done",
            "text": "子任务已全部完成，标记任务完成",
            "hint": "✓ 完成",
            "subtask_id": None,
        }

    deadline = (getattr(task, "deadline", None) or "").strip()
    return {
        "kind": "task",
        "text": f"推进任务「{title}」",
        "hint": f"截止 {deadline}" if deadline else "先推进一小步",
        "subtask_id": None,
    }
