# tests/unit/test_reminder_redesign.py
"""提醒重构（2026-10-19）：开始提醒时间门控 / 关键交付时间 / 公休日跳过。"""
import datetime

from zentray.core.categories import CategorySettings, PrimaryCategory
from zentray.core.models import PeriodicTemplate, ReminderSlot, Task
from zentray.core.periodic import build_due_instance, resolve_remind_start
from zentray.core.reminder import (
    deliveries_deadline,
    due_delivery_ats,
    normalize_deliveries,
)
from zentray.core.scheduler import task_reminder_gated


def _task(**kw):
    base = dict(id="t1", title="T", category="", priority="medium")
    base.update(kw)
    return Task(**base)


def _cats(primary: PrimaryCategory) -> CategorySettings:
    return CategorySettings(primary_list=[primary])


def _dt(s: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(s)


class TestGate:
    def test_remind_start_future_gates(self):
        t = _task(remind_start="2030-01-01T09:00")
        assert task_reminder_gated(t, _dt("2029-12-31T23:59"), _cats(PrimaryCategory(id="p", name="工作")))

    def test_remind_start_past_passes(self):
        t = _task(remind_start="2029-01-01T09:00")
        assert not task_reminder_gated(t, _dt("2029-12-31T23:59"), _cats(PrimaryCategory(id="p", name="工作")))

    def test_category_window(self):
        cats = _cats(PrimaryCategory(
            id="p", name="工作", remind_window_enabled=True,
            remind_window_start="09:00", remind_window_end="18:00",
        ))
        assert task_reminder_gated(_task(), _dt("2026-10-19T08:59"), cats)
        assert not task_reminder_gated(_task(), _dt("2026-10-19T09:00"), cats)
        assert task_reminder_gated(_task(), _dt("2026-10-19T18:00"), cats)

    def test_category_window_overnight(self):
        cats = _cats(PrimaryCategory(
            id="p", name="工作", remind_window_enabled=True,
            remind_window_start="22:00", remind_window_end="06:00",
        ))
        assert not task_reminder_gated(_task(), _dt("2026-10-19T23:30"), cats)
        assert not task_reminder_gated(_task(), _dt("2026-10-19T05:00"), cats)
        assert task_reminder_gated(_task(), _dt("2026-10-19T12:00"), cats)

    def test_skip_holidays_weekend(self):
        # 2026-10-17 是周六
        cats = _cats(PrimaryCategory(id="p", name="工作", skip_holidays=True))
        assert task_reminder_gated(_task(), _dt("2026-10-17T10:00"), cats)
        assert not task_reminder_gated(_task(), _dt("2026-10-19T10:00"), cats)
        # 任务级开关独立于分类
        cats2 = _cats(PrimaryCategory(id="p", name="工作"))
        assert task_reminder_gated(_task(skip_holidays=True), _dt("2026-10-17T10:00"), cats2)


class TestDeliveries:
    def test_normalize_sorts_and_drops_invalid(self):
        out = normalize_deliveries([
            {"at": "2026-10-20T18:00", "notify": True},
            {"at": "bad", "notify": True},
            {"at": "2026-10-19T10:00"},
            {"at": "2026-10-19T10:00", "notify": True, "fired": True},
        ])
        assert [d["at"] for d in out] == [
            "2026-10-19T10:00", "2026-10-19T10:00", "2026-10-20T18:00",
        ]
        assert out[1]["fired"] is True
        assert "fired" not in out[2]

    def test_due_only_unfired_notify_in_window(self):
        ds = [
            {"at": "2026-10-19T10:00", "notify": True, "fired": True},
            {"at": "2026-10-19T10:00:30", "notify": True},
            {"at": "2026-10-19T10:01", "notify": True},
            {"at": "2026-10-19T10:00:30", "notify": False},
        ]
        assert due_delivery_ats(ds, _dt("2026-10-19T10:00:45")) == ["2026-10-19T10:00:30"]

    def test_deadline_is_latest_date(self):
        assert deliveries_deadline([
            {"at": "2026-10-20T18:00"},
            {"at": "2026-10-19T10:00", "notify": True},
        ]) == "2026-10-20"
        assert deliveries_deadline([]) is None


def _future_monday() -> datetime.date:
    """400 天外的周一：保证相对 now 恒为未来（防时间炸弹）"""
    d = datetime.date.today() + datetime.timedelta(days=400)
    return d - datetime.timedelta(days=d.weekday())


class TestResolveRemindStart:
    def test_weekly_upcoming(self):
        monday = _future_monday()
        tmpl = PeriodicTemplate(
            base_title="周报", category="工作", periodicity="weekly",
            remind_start_slots=[ReminderSlot(time_of_day="09:30", weekday=2)],
        )
        expect = (monday + datetime.timedelta(days=2)).isoformat() + "T09:30"
        assert resolve_remind_start(tmpl, monday) == expect

    def test_monthly_clamps_and_past_is_none(self):
        tmpl = PeriodicTemplate(
            base_title="月报", category="工作", periodicity="monthly",
            remind_start_slots=[ReminderSlot(time_of_day="08:00", day_of_month=31)],
        )
        # 2026-02 无 31 日 → 钳到月末 28；2026-02-28 08:00 已过（now > 该时刻）→ None
        tmpl2 = PeriodicTemplate(
            base_title="月报2", category="工作", periodicity="monthly",
            remind_start_slots=[ReminderSlot(time_of_day="00:00", day_of_month=1)],
        )
        assert resolve_remind_start(tmpl, datetime.date(2026, 2, 1)) is None
        assert resolve_remind_start(tmpl2, datetime.date(2026, 2, 15)) is None

    def test_spawn_inherits_start_and_skip(self):
        monday = _future_monday()
        tmpl = PeriodicTemplate(
            base_title="周会", category="工作", periodicity="weekly",
            remind_start_slots=[ReminderSlot(time_of_day="23:59", weekday=6)],
            skip_holidays=True,
        )
        inst = build_due_instance(tmpl, monday)
        assert inst is not None
        assert inst.remind_start == (monday + datetime.timedelta(days=6)).isoformat() + "T23:59"
        assert inst.skip_holidays is True

    def test_spawn_without_slots_is_immediate(self):
        tmpl = PeriodicTemplate(base_title="日报", category="工作", periodicity="daily")
        inst = build_due_instance(tmpl, datetime.date(2026, 10, 19))
        assert inst is not None
        assert inst.remind_start is None


class TestServiceNormalize:
    def test_create_derives_deadline_and_seeds_skip(self, task_service):
        task = task_service.create_task({
            "title": "交付", "category": "工作",
            "deliveries": [
                {"at": "2026-10-20T18:00", "notify": True},
                {"at": "2026-10-22T10:00", "notify": False},
            ],
            "deadline": "2026-10-19",
        })
        assert task.deadline == "2026-10-22"  # 最晚交付日期覆盖手工截止
        assert [d["notify"] for d in task.deliveries] == [True, False]  # 按 at 排序后

    def test_update_keeps_fired_flags(self, task_service):
        task = task_service.create_task({
            "title": "交付2", "category": "工作",
            "deliveries": [{"at": "2026-10-20T18:00", "notify": True, "fired": True}],
        })
        task_service.update_task(task.id, {
            "deliveries": [{"at": "2026-10-20T18:00", "notify": True, "fired": True}],
        })
        updated = [t for t in task_service.get_all_tasks() if t.id == task.id][0]
        assert updated.deliveries[0].get("fired") is True

    def test_update_without_deliveries_key_untouched(self, task_service):
        task = task_service.create_task({
            "title": "保留", "category": "工作",
            "deliveries": [{"at": "2026-10-20T18:00", "notify": True}],
        })
        task_service.update_task(task.id, {"title": "改名"})
        updated = [t for t in task_service.get_all_tasks() if t.id == task.id][0]
        assert updated.deliveries and updated.title == "改名"
