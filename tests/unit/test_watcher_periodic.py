# tests/unit/test_watcher_periodic.py
"""watcher 周期派发路径测试（直调 _do_maintenance，不开线程）。

两处派发路径（task_service / watcher）已收敛到 periodic.build_due_instance，
此处只验证 watcher 的仓库接线：暂停模板不派发、到期模板照常派发。
"""
import datetime

import pytest

from zentray.core.models import PeriodicTemplate
from zentray.core.periodic import period_key
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


# ---- 逾期作废对无截止周期实例（周期桶翻篇判定，2026-11 修复）----

def _mk_instance(tmpl, created_at, *, aa=True, deadline=""):
    from zentray.core.models import Task

    return Task(
        title=f"实例-{created_at}",
        category="工作",
        task_type="periodic_instance",
        template_id=tmpl.template_id,
        deadline=deadline,
        auto_abandon_on_overdue=aa,
        created_at=created_at,
    )


def test_abandon_no_deadline_instance_when_bucket_rolled(qapp, task_repo, template_repo):
    """旧模板无截止规则 → 实例 deadline 空；aa=True 时周期桶翻篇即作废。"""
    tmpl = PeriodicTemplate(
        base_title="周任务", category="工作", periodicity="weekly",
        auto_abandon_on_overdue=True,
        last_generated_period=period_key("weekly", datetime.date.today()),
    )
    template_repo.save_all([tmpl])
    stale = _mk_instance(tmpl, "2026-10-19T09:00:00")  # 旧周期
    task_repo.save_all([stale])

    WatcherWorker(task_repo, template_repo)._do_maintenance()

    assert [t.title for t in task_repo.find_all()] == []
    logs = "\n".join(
        f.read_text() for f in (task_repo.archive_dir).glob("*.log")
    )
    assert "ABANDONED_OVERDUE" in logs and stale.title in logs


def test_keep_no_deadline_instance_in_current_bucket(qapp, task_repo, template_repo):
    """本周期内的无截止实例不作废（含 interval>1 未翻篇）。"""
    today = datetime.date.today()
    tmpl = PeriodicTemplate(
        base_title="双周任务", category="工作", periodicity="weekly", interval=2,
        auto_abandon_on_overdue=True,
        last_generated_period=period_key("weekly", datetime.date.today(), 2),
    )
    template_repo.save_all([tmpl])
    fresh = _mk_instance(tmpl, today.isoformat() + "T08:00:00")
    task_repo.save_all([fresh])

    WatcherWorker(task_repo, template_repo)._do_maintenance()

    assert [t.title for t in task_repo.find_all()] == [fresh.title]


def test_keep_when_aa_off_or_template_gone(qapp, task_repo, template_repo):
    """aa=False 或模板已删：无截止实例一律保留（保守不动）。"""
    tmpl = PeriodicTemplate(
        base_title="周任务", category="工作", periodicity="weekly",
        auto_abandon_on_overdue=False,
        last_generated_period=period_key("weekly", datetime.date.today()),
    )
    template_repo.save_all([tmpl])
    no_aa = _mk_instance(tmpl, "2026-10-19T09:00:00", aa=False)
    orphan = _mk_instance(tmpl, "2026-10-19T09:00:00", aa=True)
    orphan.template_id = "已删除模板id"
    task_repo.save_all([no_aa, orphan])

    WatcherWorker(task_repo, template_repo)._do_maintenance()

    titles = [t.title for t in task_repo.find_all()]
    assert sorted(titles) == sorted([no_aa.title, orphan.title])
