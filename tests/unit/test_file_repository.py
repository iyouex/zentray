# tests/unit/test_file_repository.py
import datetime

from zentray.core.models import Task
from zentray.repositories.file_repository import parse_archive_line


def test_save_and_load_task(task_repo, tmp_data_dir):
    task = Task(id="test-1", title="test task", category="工作")
    task_repo.save_all([task])
    loaded = task_repo.find_all()
    assert len(loaded) == 1
    assert loaded[0].title == "test task"
    assert loaded[0].category == "工作"


def test_save_single_and_delete(task_repo):
    t1 = Task(id="a", title="A", category="工作")
    t2 = Task(id="b", title="B", category="生活")
    task_repo.save(t1)
    task_repo.save(t2)
    assert len(task_repo.find_all()) == 2
    task_repo.delete("a")
    remaining = task_repo.find_all()
    assert len(remaining) == 1
    assert remaining[0].id == "b"


def test_archive_writes_log(task_repo, tmp_data_dir):
    task = Task(id="x", title="归档我", category="工作", priority="high")
    task_repo.archive(task, "DONE")
    logs = list((tmp_data_dir / "archive").glob("*.log"))
    assert logs
    content = logs[0].read_text(encoding="utf-8")
    assert "DONE" in content
    assert "归档我" in content


# ---- 归档任务列表（历史视图） ----

def test_archive_roundtrip_fields(task_repo):
    """archive() 写入 → list_archived 读出，字段完整往返。"""
    task_repo.archive(Task(id="a", title="吃药", category="生活", priority="medium", details="饭后"), "DONE")
    items = task_repo.list_archived()
    assert len(items) == 1
    it = items[0]
    assert it["title"] == "吃药" and it["category"] == "生活"
    assert it["priority"] == "medium" and it["details"] == "饭后"
    assert it["status"] == "DONE" and it["attachment_count"] == 0
    assert it["archived_at"].startswith(datetime.date.today().isoformat())


def test_parse_line_edge_cases():
    """details 为空、title 含 ' - '、坏行跳过。"""
    # details 为空：写入方产出 "title - "
    it = parse_archive_line("[2026-09-22 10:00:00] [状态: DONE] [分类: 工作] [HIGH] A - B -  (附件数: 0)")
    assert it["title"] == "A - B" and it["details"] == ""
    # title 含 " - " 且有 details：贪心归 title
    it = parse_archive_line("[2026-09-22 10:00:00] [状态: ABANDONED] [分类: 工作] [LOW] A - B - 备注 (附件数: 2)")
    assert it["title"] == "A - B" and it["details"] == "备注" and it["attachment_count"] == 2
    # 坏行 → None
    assert parse_archive_line("") is None
    assert parse_archive_line("随便一行乱码") is None
    assert parse_archive_line("[2026-09-22 10:00:00] 缺状态段") is None


def test_list_archived_filters_and_order(task_repo, tmp_data_dir):
    """状态过滤（OVERDUE 归废弃族）、分类过滤、倒序、坏行跳过、天数窗口。"""
    arch = tmp_data_dir / "archive"
    # 手写两天归档 + 一行坏行 + 一个超窗口旧文件
    (arch / "2026-01-01.log").write_text(
        "[2026-01-01 09:00:00] [状态: DONE] [分类: 工作] [HIGH] 太旧的 (附件数: 0)\n", encoding="utf-8")
    today = datetime.date.today()
    d1, d2 = (today - datetime.timedelta(days=1)).isoformat(), today.isoformat()
    (arch / f"{d1}.log").write_text(
        f"[{d1} 09:00:00] [状态: DONE] [分类: 工作] [HIGH] 昨天-done (附件数: 0)\n"
        f"[{d1} 10:00:00] [状态: ABANDONED_OVERDUE] [分类: 生活] [LOW] 昨天-overdue (附件数: 0)\n"
        "坏行\n",
        encoding="utf-8")
    (arch / f"{d2}.log").write_text(
        f"[{d2} 08:00:00] [状态: DONE] [分类: 生活] [MEDIUM] 今天-done (附件数: 0)\n"
        f"[{d2} 09:00:00] [状态: ABANDONED] [分类: 工作] [LOW] 今天-abandoned (附件数: 0)\n",
        encoding="utf-8")

    all_items = task_repo.list_archived()
    assert [i["title"] for i in all_items] == ["今天-abandoned", "今天-done", "昨天-overdue", "昨天-done"]

    assert [i["title"] for i in task_repo.list_archived(status="done")] == ["今天-done", "昨天-done"]
    assert [i["title"] for i in task_repo.list_archived(status="abandoned")] == ["今天-abandoned", "昨天-overdue"]
    assert [i["title"] for i in task_repo.list_archived(category="生活")] == ["今天-done", "昨天-overdue"]
    assert all(i["title"] != "太旧的" for i in task_repo.list_archived(days=30))
