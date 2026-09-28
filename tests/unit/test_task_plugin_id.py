"""任务关联 plugin_id 持久化。"""
from zentray.core.models import PeriodicTemplate, Task
from zentray.services.task_service import TaskService


def test_task_plugin_id_roundtrip(task_service: TaskService):
    t = task_service.create_task(
        {
            "title": "带插件任务",
            "category": "工作",
            "priority": "medium",
            "plugin_id": "net-cleanup",
        }
    )
    assert t.plugin_id == "net-cleanup"
    found = task_service.find_task(t.id)
    assert found is not None
    assert found.plugin_id == "net-cleanup"

    updated = task_service.update_task(t.id, {"plugin_id": None, "title": "带插件任务"})
    assert updated is not None
    assert updated.plugin_id is None


def test_template_inherits_plugin_id(task_service: TaskService):
    tmpl = task_service.create_template(
        {
            "title": "周期带插件",
            "category": "工作",
            "periodicity": "daily",
            "plugin_id": "net-cleanup",
        }
    )
    assert isinstance(tmpl, PeriodicTemplate)
    assert tmpl.plugin_id == "net-cleanup"
    # 立即派发的实例应继承
    instances = [
        t
        for t in task_service.get_all_tasks()
        if getattr(t, "template_id", None) == tmpl.template_id
    ]
    assert instances
    assert instances[0].plugin_id == "net-cleanup"


def test_empty_plugin_id_normalized():
    t = Task(title="x", category="工作", plugin_id="  ")
    assert t.plugin_id is None
