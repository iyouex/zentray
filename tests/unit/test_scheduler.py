# tests/unit/test_scheduler.py
import datetime
from zentray.core.models import Task
from zentray.core.scheduler import Scheduler


def test_overdue_prefix_not_on_task_object():
    s = Scheduler()
    s.configure("random", True, "【已逾期】")
    t = Task(
        title="重要",
        category="工作",
        priority="high",
        deadline="2020-01-01",
        id="abc",
    )
    s.build_queue([t])
    cur = s.get_next()
    assert cur is not None
    assert cur.title == "重要"  # 本体未改
    assert cur.id == "abc"


def test_focus_does_not_shrink_queue():
    s = Scheduler()
    tasks = [
        Task(title=f"t{i}", category="工作", priority="medium", id=str(i))
        for i in range(3)
    ]
    s.build_queue(tasks)
    s.focus(tasks[1])
    assert s.get_current().id == "1"
    assert len(s._active_queue) == 3
