# tests/unit/test_category_uuid_guard.py
"""坏分类 id/uuid 名根治：写侧不再生、读侧遮蔽、分类表自愈。"""
import uuid as _uuid

from zentray.api.handlers import _task_dict, _template_dict
from zentray.core.categories import CategorySettings, PrimaryCategory, is_uuid_like
from zentray.core.models import PeriodicTemplate, Task
from zentray.core.scheduler import Scheduler
from zentray.repositories.file_periodic_repository import FilePeriodicTemplateRepository
from zentray.repositories.file_repository import FileTaskRepository
from zentray.services.task_service import TaskService

DEAD_ID = str(_uuid.uuid4())
DEAD_ID_2 = str(_uuid.uuid4())


def test_is_uuid_like():
    assert is_uuid_like(DEAD_ID)
    assert is_uuid_like(DEAD_ID.upper())
    assert not is_uuid_like("工作")
    assert not is_uuid_like("")
    assert not is_uuid_like(None)


def test_write_side_never_recreates_uuid_category(tmp_data_dir):
    """编辑带死 id + uuid 名的任务：不得 ensure 出 uuid 名分类（原放大器）。"""
    from zentray.services.settings_manager import SettingsManager

    svc = TaskService(FileTaskRepository(), FilePeriodicTemplateRepository(), Scheduler())
    before = len(SettingsManager().categories.primary_list)
    svc.create_task(
        {
            "title": "坏分类任务",
            "category": DEAD_ID,  # uuid 被当名字
            "category_primary_id": DEAD_ID_2,  # 已删分类的旧 id
        }
    )
    cats = SettingsManager().categories.primary_list
    assert not any(is_uuid_like(c.name) for c in cats), "不得再生 uuid 名分类"
    assert len(cats) == before  # 表未膨胀
    task = svc.get_all_tasks()[-1]
    assert task.category == "工作"  # 回落默认


def test_read_side_masks_uuid_category(tmp_data_dir):
    """API 读出遮蔽：任务/模板存 uuid 名时列表不显示垃圾。"""
    t = Task(id="t1", title="x", category=DEAD_ID)
    assert _task_dict(t)["category"] == ""

    tmpl = PeriodicTemplate(base_title="x", category=DEAD_ID, periodicity="daily")
    assert _template_dict(tmpl)["category"] == ""


def test_category_table_heals_uuid_names():
    """分类表加载自愈：剔除 uuid 名分类；全空回落默认。"""
    data = {
        "primary_list": [
            {"id": DEAD_ID, "name": DEAD_ID},
            {"id": "p1", "name": "工作"},
        ]
    }
    cs = CategorySettings.from_dict(data)
    assert [p.name for p in cs.primary_list] == ["工作"]

    cs2 = CategorySettings.from_dict({"primary_list": [{"id": DEAD_ID, "name": DEAD_ID}]})
    assert not any(is_uuid_like(p.name) for p in cs2.primary_list)
    assert len(cs2.primary_list) > 0  # 回落默认而非空表
