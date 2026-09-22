# tests/unit/test_watcher_periodic.py
"""watcher 周期派发路径测试（直调 _do_maintenance，不开线程）。

两处派发路径（task_service / watcher）已收敛到 periodic.build_due_instance，
此处只验证 watcher 的仓库接线：暂停模板不派发、到期模板照常派发。
"""
import datetime

import pytest

from zentray.core.models import PeriodicTemplate
from zentray.workers.watcher import WatcherWorker


@pytest.fixture
def qapp():
    from PySide6.QtCore import QCoreApplication

    return QCoreApplication.instance() or QCoreApplication([])


def test_maintenance_skips_paused_templates(qapp, task_repo, template_repo):
    paused_tmpl = PeriodicTemplate(
        base_title="暂停模板",
        category="工作",
        periodicity="daily",
        last_generated_period=None,
    )
    paused_tmpl.paused = True
    active_tmpl = PeriodicTemplate(
        base_title="活跃模板",
        category="工作",
        periodicity="daily",
        last_generated_period=None,
    )
    template_repo.save_all([paused_tmpl, active_tmpl])

    worker = WatcherWorker(task_repo, template_repo)
    worker._do_maintenance()

    titles = [t.title for t in task_repo.find_all()]
    assert any("活跃模板" in t for t in titles)
    assert not any("暂停模板" in t for t in titles)

    # 暂停模板水位未被推进（仍是未派发状态，恢复后即可派发）
    saved = {t.base_title: t for t in template_repo.find_all()}
    assert saved["活跃模板"].last_generated_period is not None
    assert saved["暂停模板"].last_generated_period is None


def test_maintenance_respects_skipped_watermark(qapp, task_repo, template_repo):
    today = datetime.date.today()
    from zentray.core.periodic import skip_watermark_key

    tmpl = PeriodicTemplate(base_title="跳过模板", category="工作", periodicity="daily")
    tmpl.last_generated_period = skip_watermark_key(tmpl, today, 3)
    template_repo.save_all([tmpl])

    worker = WatcherWorker(task_repo, template_repo)
    worker._do_maintenance()

    assert not any("跳过模板" in t.title for t in task_repo.find_all())
