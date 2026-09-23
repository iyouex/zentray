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

    def test_create_task_with_subtasks_normalizes(self, task_service):
        task = task_service.create_task({
            "title": "子任务归一",
            "category": "工作",
            "subtasks": [
                {"title": "  步骤一 "},
                {"id": "keep", "title": "步骤二", "status": "done"},
                {"title": "bad", "status": "weird"},
                {"title": "   "},
                "not-a-dict",
            ],
        })
        assert [(s["id"], s["title"], s["status"]) for s in task.subtasks] == [
            (task.subtasks[0]["id"], "步骤一", "active"),
            ("keep", "步骤二", "done"),
            (task.subtasks[2]["id"], "bad", "active"),
        ]

    def test_update_task_without_subtasks_key_preserves(self, task_service):
        """Qt TaskDialog.get_data 不带 subtasks——不能被重置为空。"""
        task = task_service.create_task({
            "title": "原任务",
            "category": "工作",
            "subtasks": [{"id": "s1", "title": "存量", "status": "active"}],
        })
        updated = task_service.update_task(task.id, {"title": "改标题"})
        assert updated.title == "改标题"
        assert updated.subtasks == [{"id": "s1", "title": "存量", "status": "active"}]

    def test_add_subtask(self, task_service):
        task = task_service.create_task({"title": "任务", "category": "工作"})
        fresh = task_service.add_subtask(task.id, " 新子任务 ")
        assert len(fresh.subtasks) == 1
        assert fresh.subtasks[0]["title"] == "新子任务"
        assert fresh.subtasks[0]["status"] == "active"
        assert task_service.add_subtask("no-such-id", "x") is None

    def test_subtask_done_no_auto_while_active_remains(self, task_service):
        task = task_service.create_task({
            "title": "两步任务",
            "category": "工作",
            "subtasks": [{"title": "甲"}, {"title": "乙"}],
        })
        t, auto = task_service.set_subtask_status(task.id, task.subtasks[0]["id"], "done")
        assert auto is False
        assert len(t.subtasks) == 2
        assert t.subtasks[0]["status"] == "done"

    def test_subtask_done_auto_completes(self, task_service, task_repo, tmp_data_dir):
        task = task_service.create_task({
            "title": "自动完成",
            "category": "工作",
            "subtasks": [{"title": "甲"}, {"title": "乙"}],
        })
        task_service.set_subtask_status(task.id, task.subtasks[0]["id"], "done")
        t, auto = task_service.set_subtask_status(task.id, task.subtasks[1]["id"], "done")
        assert auto is True
        assert not any(x.id == task.id for x in task_service.get_all_tasks())
        log = (tmp_data_dir / "archive" / f"{datetime.date.today().isoformat()}.log").read_text()
        assert "[状态: DONE]" in log and "自动完成 -" in log  # title + 空 details 的归档行

    def test_subtask_abandon_auto_completes_too(self, task_service):
        task = task_service.create_task({
            "title": "全废弃",
            "category": "工作",
            "subtasks": [{"title": "甲"}],
        })
        _, auto = task_service.set_subtask_status(task.id, task.subtasks[0]["id"], "abandoned")
        assert auto is True
        assert not any(x.id == task.id for x in task_service.get_all_tasks())

    def test_set_subtask_status_not_found(self, task_service):
        task = task_service.create_task({
            "title": "任务",
            "category": "工作",
            "subtasks": [{"title": "甲"}],
        })
        assert task_service.set_subtask_status(task.id, "bad-sid", "done") is None
        # 已非 active 的子任务再操作 → None（幂等保护）
        task_service.set_subtask_status(task.id, task.subtasks[0]["id"], "done")
        assert task_service.set_subtask_status(task.id, task.subtasks[0]["id"], "done") is None

    def test_update_template_preserves_subtasks(self, task_service, task_repo):
        task_service.create_task({
            "title": "模板",
            "category": "工作",
            "task_type": "periodic",
            "periodicity": "daily",
            "subtasks": [{"id": "p1", "title": "预设甲", "status": "active"}],
        })
        tmpl_id = task_repo.find_all()[0].template_id
        updated = task_service.update_template(tmpl_id, {"priority": "high"})
        assert updated.priority == "high"
        assert [s["title"] for s in updated.subtasks] == ["预设甲"]
        assert updated.subtasks[0]["id"] == "p1"

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
