# tests/unit/test_reminder_redesign.py
"""提醒重构（2026-10-19）：开始提醒时间门控 / 公休日跳过。
时间重设计（2026-10-20）：截止时分+截止弹窗 / 逾期粒度 / 交付改额外弹窗时间。"""
import datetime

from zentray.core.categories import CategorySettings, PrimaryCategory
from zentray.core.models import PeriodicTemplate, ReminderSlot, Task
from zentray.core.periodic import (
    build_due_instance,
    compute_instance_deadline,
    resolve_remind_start,
)
from zentray.core.reminder import (
    due_delivery_ats,
    due_popup_at,
    is_task_overdue,
    normalize_deliveries,
    normalize_due_time,
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


class TestDuePopup:
    """截止时刻弹窗：到点一次、due_fired 去重、改 due_time 换时刻。"""

    def test_fires_in_window(self):
        t = _task(deadline="2026-10-20", due_time="18:00", popup_at_due=True)
        assert due_popup_at(t, _dt("2026-10-20T18:00:30")) == "2026-10-20T18:00"
        # 窗外不弹
        assert due_popup_at(t, _dt("2026-10-20T18:01:00")) is None
        assert due_popup_at(t, _dt("2026-10-20T17:59:00")) is None

    def test_dedupe_by_due_fired(self):
        t = _task(deadline="2026-10-20", due_time="18:00", popup_at_due=True,
                  due_fired="2026-10-20T18:00")
        assert due_popup_at(t, _dt("2026-10-20T18:00:30")) is None

    def test_retime_refires(self):
        t = _task(deadline="2026-10-20", due_time="19:00", popup_at_due=True,
                  due_fired="2026-10-20T18:00")
        assert due_popup_at(t, _dt("2026-10-20T19:00:20")) == "2026-10-20T19:00"

    def test_no_deadline_or_switch_off(self):
        assert due_popup_at(_task(popup_at_due=True), _dt("2026-10-20T18:00")) is None
        assert due_popup_at(_task(deadline="2026-10-20", due_time="18:00"),
                            _dt("2026-10-20T18:00")) is None

    def test_due_time_default_2359(self):
        t = _task(deadline="2026-10-20", popup_at_due=True)
        assert due_popup_at(t, _dt("2026-10-20T23:59:10")) == "2026-10-20T23:59"


class TestOverdueGranularity:
    """逾期判定：有 due_time 分钟级、无则日级。"""

    def test_day_level_without_due_time(self):
        t = _task(deadline="2026-10-19")
        assert is_task_overdue(t, _dt("2026-10-20T00:00"))      # 次日逾期
        assert not is_task_overdue(t, _dt("2026-10-19T23:59"))  # 当日不逾期
        assert not is_task_overdue(_task(), _dt("2026-10-19T10:00"))  # 无截止

    def test_minute_level_with_due_time(self):
        t = _task(deadline="2026-10-20", due_time="18:00")
        assert not is_task_overdue(t, _dt("2026-10-20T17:59"))
        assert is_task_overdue(t, _dt("2026-10-20T18:00"))


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


class TestDailyStartAndDueInheritance:
    """时间重设计（2026-10-20）：日模板仅时分开始点；due_time/popup 派发继承。"""

    def test_daily_time_only_start(self):
        # 2026-10-19（未来校验靠 400 天外日期防时间炸弹）
        d = datetime.date.today() + datetime.timedelta(days=400)
        tmpl = PeriodicTemplate(
            base_title="晨读", category="工作", periodicity="daily",
            remind_start_slots=[ReminderSlot(time_of_day="23:30")],
        )
        assert resolve_remind_start(tmpl, d) == d.isoformat() + "T23:30"

    def test_daily_start_past_is_none(self):
        tmpl = PeriodicTemplate(
            base_title="晨读2", category="工作", periodicity="daily",
            remind_start_slots=[ReminderSlot(time_of_day="00:00")],
        )
        assert resolve_remind_start(tmpl, datetime.date.today()) is None

    def test_spawn_inherits_due_time_and_popup(self):
        tmpl = PeriodicTemplate(
            base_title="日报", category="工作", periodicity="daily",
            due_time="18:30", popup_at_due=True,
        )
        inst = build_due_instance(tmpl, datetime.date(2026, 10, 19))
        assert inst is not None
        assert inst.deadline == "2026-10-19"
        assert inst.due_time == "18:30"
        assert inst.popup_at_due is True
        assert inst.due_fired is None  # 新实例截止弹窗待触发

    def test_daily_without_due_time_has_no_deadline(self):
        tmpl = PeriodicTemplate(base_title="闲记", category="生活", periodicity="daily")
        inst = build_due_instance(tmpl, datetime.date(2026, 10, 19))
        assert inst is not None
        assert inst.deadline == ""

    def test_monthly_deadline_clamps_feb(self):
        tmpl = PeriodicTemplate(
            base_title="月报", category="工作", periodicity="monthly",
            deadline_day_of_month=31, due_time="20:00",
        )
        assert compute_instance_deadline(tmpl, datetime.date(2026, 2, 1)) == "2026-02-28"


class TestTemplatePopupSlots:
    """时间重设计二轮（2026-10-21）：模板周期内弹窗点位 → 派发实例 deliveries。"""

    def test_daily_materializes_sorted(self):
        d = datetime.date.today() + datetime.timedelta(days=400)
        tmpl = PeriodicTemplate(
            base_title="日报", category="工作", periodicity="daily",
            popup_slots=[
                ReminderSlot(time_of_day="09:30"),
                ReminderSlot(time_of_day="07:00"),
            ],
        )
        inst = build_due_instance(tmpl, d)
        assert inst.deliveries == [
            {"at": d.isoformat() + "T07:00", "notify": True},
            {"at": d.isoformat() + "T09:30", "notify": True},
        ]

    def test_past_moment_not_materialized(self):
        # 今日 00:00 恒已过 → 不物化
        tmpl = PeriodicTemplate(
            base_title="晨报", category="工作", periodicity="daily",
            popup_slots=[ReminderSlot(time_of_day="00:00")],
        )
        inst = build_due_instance(tmpl, datetime.date.today())
        assert inst.deliveries == []

    def test_weekly_point_in_current_week(self):
        monday = _future_monday()
        tmpl = PeriodicTemplate(
            base_title="周会", category="工作", periodicity="weekly",
            deadline_weekday=4,
            popup_slots=[ReminderSlot(time_of_day="10:00", weekday=3)],
        )
        inst = build_due_instance(tmpl, monday)
        expect = (monday + datetime.timedelta(days=3)).isoformat() + "T10:00"
        assert inst.deliveries == [{"at": expect, "notify": True}]

    def test_monthly_point_clamps_month_end(self):
        import calendar as _cal

        monday = _future_monday()
        tmpl = PeriodicTemplate(
            base_title="月检", category="工作", periodicity="monthly",
            deadline_day_of_month=31,
            popup_slots=[ReminderSlot(time_of_day="12:00", day_of_month=35)],
        )
        inst = build_due_instance(tmpl, monday)
        last = _cal.monthrange(monday.year, monday.month)[1]
        expect = datetime.date(monday.year, monday.month, last).isoformat() + "T12:00"
        assert inst.deliveries == [{"at": expect, "notify": True}]

    def test_template_roundtrip_popup_slots(self):
        tmpl = PeriodicTemplate(
            base_title="月检", category="工作", periodicity="monthly",
            popup_slots=[{"time_of_day": "12:00", "day_of_month": 5}],
        )
        d = tmpl.to_dict()
        assert d["popup_slots"] == [
            {"time_of_day": "12:00", "weekday": None, "day_of_month": 5}
        ]
        back = PeriodicTemplate.from_dict(d)
        assert isinstance(back.popup_slots[0], ReminderSlot)
        assert back.popup_slots[0].day_of_month == 5


class TestServiceNormalize:
    def test_create_no_deadline_derivation_and_seeds_skip(self, task_service):
        """退役「最晚交付=截止」：截止只由截止行决定；skip_holidays 取分类预设。"""
        task = task_service.create_task({
            "title": "交付", "category": "工作",
            "deliveries": [
                {"at": "2026-10-20T18:00", "notify": True},
                {"at": "2026-10-22T10:00", "notify": False},
            ],
            "deadline": "2026-10-19",
        })
        assert task.deadline == "2026-10-19"  # 手工截止不再被交付覆盖
        assert [d["notify"] for d in task.deliveries] == [True, False]  # 按 at 排序后

    def test_create_normalizes_due_fields(self, task_service):
        task = task_service.create_task({
            "title": "带时分", "category": "工作",
            "deadline": "2026-10-20", "due_time": "9:5", "popup_at_due": 1,
        })
        assert task.due_time == "09:05"
        assert task.popup_at_due is True
        bad = task_service.create_task({
            "title": "坏时分", "category": "工作", "due_time": "junk",
        })
        assert bad.due_time is None and bad.popup_at_due is False

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
