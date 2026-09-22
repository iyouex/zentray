# zentray/repositories/file_repository.py
import datetime
import re
from pathlib import Path
from typing import List, Optional

from zentray.config import ACTIVE_TASKS_FILE, ARCHIVE_DIR
from zentray.core.file_io import append_text_line, load_json_list, path_lock, save_json_list
from zentray.core.models import Task
from zentray.core.repository import TaskRepository

# archive() 写出行的读侧镜像：[时间] [状态: X] [分类: Y] [PRI] title - details (附件数: n)
_ARCHIVE_LINE_RE = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[状态: (\w+)\] "
    r"\[分类: ([^\]]*)\] \[(HIGH|MEDIUM|LOW)\] (.*)$"
)
_ATTACH_RE = re.compile(r" \(附件数: (\d+)\)$")


def parse_archive_line(line: str) -> Optional[dict]:
    """尽力解析一行归档文本；格式不符返回 None（调用方跳过）。"""
    m = _ARCHIVE_LINE_RE.match(line.strip())
    if not m:
        return None
    ts, status, category, pri, tail = m.groups()
    n = 0
    am = _ATTACH_RE.search(tail)
    if am:
        n = int(am.group(1))
        tail = _ATTACH_RE.sub("", tail)
    if tail.endswith(" - "):  # details 为空时写入方产出 "title - "
        title, details = tail[:-3], ""
    elif " - " in tail:
        title, _, details = tail.rpartition(" - ")  # title 含 " - " 时贪心归 title
    else:
        title, details = tail, ""
    return {
        "archived_at": ts,
        "status": status,
        "category": category,
        "priority": pri.lower(),
        "title": title,
        "details": details,
        "attachment_count": n,
    }


class FileTaskRepository(TaskRepository):
    def __init__(self, active_file: Path | None = None, archive_dir: Path | None = None):
        self.active_file = Path(active_file) if active_file else ACTIVE_TASKS_FILE
        self.archive_dir = Path(archive_dir) if archive_dir else ARCHIVE_DIR

    def find_all(self) -> List[Task]:
        data = load_json_list(self.active_file)
        return [Task.from_dict(d) for d in data]

    def find_by_id(self, task_id: str) -> Optional[Task]:
        with path_lock(self.active_file):
            tasks = self.find_all()
            return next((t for t in tasks if t.id == task_id), None)

    def save(self, task: Task) -> None:
        """保存或更新单个任务（同一把锁下 read-modify-write）。"""
        with path_lock(self.active_file):
            tasks = self.find_all()
            for i, t in enumerate(tasks):
                if t.id == task.id:
                    tasks[i] = task
                    self.save_all(tasks)
                    return
            tasks.append(task)
            self.save_all(tasks)

    def save_all(self, tasks: List[Task]) -> None:
        data = [t.to_dict() for t in tasks]
        save_json_list(self.active_file, data)

    def delete(self, task_id: str) -> None:
        with path_lock(self.active_file):
            tasks = [t for t in self.find_all() if t.id != task_id]
            self.save_all(tasks)

    def find_active(self) -> List[Task]:
        # JSON 模式下 active 文件中的任务均为未归档任务
        return self.find_all()

    def mutate_all(self, mutator) -> bool:
        """
        在同一把锁内完成 read → mutate → write，避免跨线程丢失更新。

        mutator(tasks: List[Task]) -> bool  返回是否有修改。
        """
        with path_lock(self.active_file):
            tasks = self.find_all()
            changed = bool(mutator(tasks))
            if changed:
                self.save_all(tasks)
            return changed

    def archive(self, task: Task, status: str) -> None:
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        archive_file = self.archive_dir / f"{date_str}.log"
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = (
            f"[{timestamp}] [状态: {status}] [分类: {task.category}] "
            f"[{task.priority.upper()}] {task.title} - {task.details} "
            f"(附件数: {len(task.attachments)})\n"
        )
        append_text_line(archive_file, log_line)

    def list_archived(
        self, status: Optional[str] = None, category: Optional[str] = None, days: int = 90
    ) -> List[dict]:
        """解析 archive/*.log 返回归档任务（时间倒序）。status: done|abandoned。"""
        cutoff = datetime.date.today() - datetime.timedelta(days=max(1, int(days or 90)))
        try:
            files = sorted(self.archive_dir.glob("*.log"), reverse=True)
        except OSError:
            return []
        out: List[dict] = []
        for f in files:
            try:
                if datetime.date.fromisoformat(f.stem) < cutoff:
                    continue
            except ValueError:
                continue  # 非 YYYY-MM-DD 命名跳过
            try:
                lines = f.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                item = parse_archive_line(line)
                if not item:
                    continue
                if status == "done" and item["status"] != "DONE":
                    continue
                if status == "abandoned" and item["status"] not in ("ABANDONED", "ABANDONED_OVERDUE"):
                    continue
                if category and item["category"] != category:
                    continue
                out.append(item)
        return out
