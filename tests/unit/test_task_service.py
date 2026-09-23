# tests/unit/test_task_service.py
"""TaskService 单元测试（使用临时数据目录）"""
import datetime

from zentray.core.models import PeriodicTemplate, Task
from zentray.core.periodic import should_spawn


class TestTaskService:
    def test_create_task(self, task_service):
        task = task_service.create_task({
            "title": "测试任务",
            "category": "工作",
            "priority": "high",
        })
        assert isinstance(task, Task)
        assert task.id is not None
        assert task.title == "测试任务"
        assert task.task_type == "one-time"

    def test_create_periodic_template(self, task_service, template_repo, task_repo):
        result = task_service.create_task({
            "title": "每日站会",
            "category": "工作",
            "priority": "medium",
            "task_type": "periodic",
            "periodicity": "daily",
        })
        assert isinstance(result, PeriodicTemplate)
        assert result.base_title == "每日站会"
        assert result.periodicity == "daily"

        templates = template_repo.find_all()
        assert len(templates) == 1
        assert templates[0].last_generated_period  # 已立即派发

        # 应生成一条周期实例任务
        tasks = task_repo.find_all()
        assert len(tasks) == 1
        assert tasks[0].task_type == "periodic_instance"
        assert "每日站会" in tasks[0].title

    def test_get_all_tasks_returns_list(self, task_service):
        tasks = task_service.get_all_tasks()
        assert isinstance(tasks, list)

    def test_mark_done_removes_task(self, task_service):
        task = task_service.create_task({
            "title": "待完成的任务",
            "category": "学习",
            "priority": "medium",
        })
        task_id = task.id
        task_service.mark_done(task_id)
        remaining = task_service.get_all_tasks()
        assert not any(t.id == task_id for t in remaining)

    def test_update_progress(self, task_service):
        task = task_service.create_task({
            "title": "进度测试",
            "category": "生活",
            "priority": "low",
        })
        updated = task_service.update_progress(task.id, 50, "完成一半")
        assert updated is not None
        assert updated.progress == 50
        assert len(updated.progress_logs) == 1
        assert updated.progress_logs[0]["percent"] == 50

    def test_abandon_removes_task(self, task_service):
        task = task_service.create_task({
            "title": "要废弃的任务",
            "category": "工作",
            "priority": "low",
        })
        task_id = task.id
        task_service.abandon(task_id)
        remaining = task_service.get_all_tasks()
        assert not any(t.id == task_id for t in remaining)

    def test_select_task_keeps_queue(self, task_service):
        t1 = task_service.create_task({"title": "A", "category": "工作", "priority": "high"})
        t2 = task_service.create_task({"title": "B", "category": "工作", "priority": "low"})
        task_service.select_task(t2.id)
        assert task_service.get_current_task().id == t2.id
        # 队列仍包含全部任务
        assert len(task_service.scheduler._active_queue) + len(
            task_service.scheduler._overdue_queue
        ) >= 2

    # ---- v3.10 暂停 / 跳过 ----

    def test_skip_template_advances_watermark_without_spawning(
        self, task_service, template_repo, task_repo
    ):
        tmpl = task_service.create_task({
            "title": "日报",
            "category": "工作",
            "task_type": "periodic",
            "periodicity": "daily",
        })
        tasks_before = len(task_repo.find_all())  # 创建时已派发今天实例

        got = task_service.skip_template(tmpl.template_id, 2)
        assert got is not None
        assert len(task_repo.find_all()) == tasks_before  # 跳过不产生实例

        t2 = template_repo.find_all()[0]
        today = datetime.date.today()
        assert not should_spawn(t2, today + datetime.timedelta(days=1))
        assert not should_spawn(t2, today + datetime.timedelta(days=2))
        assert should_spawn(t2, today + datetime.timedelta(days=3))

    def test_update_template_preserves_paused(self, task_service, task_repo):
        tmpl = task_service.create_task({
            "title": "暂停模板",
            "category": "工作",
            "task_type": "periodic",
            "periodicity": "daily",
        })
        task_service.update_template(tmpl.template_id, {"paused": True})
        t = task_service.find_template(tmpl.template_id)
        assert t.paused is True

        # 再 PUT 其他字段：白名单重建不得丢 paused，且暂停期不派发
        tasks_before = len(task_repo.find_all())
        task_service.update_template(tmpl.template_id, {"priority": "high"})
        t = task_service.find_template(tmpl.template_id)
        assert t.paused is True
        assert t.priority == "high"
        assert len(task_repo.find_all()) == tasks_before
