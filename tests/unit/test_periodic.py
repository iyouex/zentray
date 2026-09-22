"""周期调度纯函数测试。"""
import datetime

from zentray.core.models import PeriodicTemplate
from zentray.core.periodic import (
    advance_period_key,
    build_due_instance,
    compute_instance_deadline,
    is_schedule_active,
    next_spawn_date,
    parse_period_key,
    period_key,
    should_spawn,
    skip_watermark_key,
)


def test_period_key_daily_interval():
    d = datetime.date(2026, 7, 17)
    k1 = period_key("daily", d, 1)
    k2 = period_key("daily", d + datetime.timedelta(days=1), 1)
    assert k1 != k2
    # 每 2 天：相邻两天可能同桶
    k_a = period_key("daily", d, 2)
    k_b = period_key("daily", d + datetime.timedelta(days=1), 2)
    # ordinal//2 相邻可能相同或不同，只校验稳定性
    assert period_key("daily", d, 2) == k_a


def test_should_spawn_and_long_term():
    today = datetime.date(2026, 7, 17)
    tmpl = PeriodicTemplate(
        base_title="站会",
        category="工作",
        periodicity="daily",
        interval=1,
        long_term=True,
        last_generated_period=None,
    )
    assert should_spawn(tmpl, today)
    tmpl.last_generated_period = period_key("daily", today, 1)
    assert not should_spawn(tmpl, today)


def test_schedule_end_stops_spawn():
    today = datetime.date(2026, 7, 17)
    tmpl = PeriodicTemplate(
        base_title="临时",
        category="工作",
        periodicity="daily",
        long_term=False,
        schedule_end_date="2026-07-10",
        last_generated_period=None,
    )
    assert not is_schedule_active(tmpl, today)
    assert not should_spawn(tmpl, today)


def test_weekly_deadline():
    # 2026-07-17 is Friday (weekday 4)
    today = datetime.date(2026, 7, 17)
    tmpl = PeriodicTemplate(
        base_title="周报",
        category="工作",
        periodicity="weekly",
        deadline_weekday=4,
    )
    assert compute_instance_deadline(tmpl, today) == "2026-07-17"
    tmpl.deadline_weekday = 0  # Monday → 7-20
    assert compute_instance_deadline(tmpl, today) == "2026-07-20"


def test_monthly_deadline():
    today = datetime.date(2026, 7, 10)
    tmpl = PeriodicTemplate(
        base_title="月结",
        category="工作",
        periodicity="monthly",
        deadline_day_of_month=25,
    )
    assert compute_instance_deadline(tmpl, today) == "2026-07-25"


# ---- v3.10 暂停 / 跳过 / 有序水位 ----


def test_parse_period_key():
    assert parse_period_key("D739012") == ("daily", 739012)
    assert parse_period_key("W107381") == ("weekly", 107381)
    assert parse_period_key("M202603x2") == ("monthly", (2026 * 12 + 2) // 2)
    assert parse_period_key("") is None
    assert parse_period_key(None) is None
    assert parse_period_key("X1") is None
    assert parse_period_key("M202603") is None  # monthly 缺 x{n} 后缀


def test_should_spawn_paused():
    today = datetime.date(2026, 9, 22)
    tmpl = PeriodicTemplate(base_title="暂停中", category="工作", periodicity="daily")
    tmpl.paused = True
    assert not should_spawn(tmpl, today)
    tmpl.last_generated_period = None
    assert not should_spawn(tmpl, today)  # 从未派发也压不住 paused


def test_should_spawn_ordered_watermark():
    today = datetime.date(2026, 9, 22)
    tmpl = PeriodicTemplate(base_title="跳过", category="工作", periodicity="daily")
    # 水位领先（跳过中）→ 不派发
    tmpl.last_generated_period = period_key("daily", today + datetime.timedelta(days=3), 1)
    assert not should_spawn(tmpl, today)
    # 水位落后多桶 → 派发（当前桶补一次）
    tmpl.last_generated_period = period_key("daily", today - datetime.timedelta(days=5), 1)
    assert should_spawn(tmpl, today)
    # 前缀不一致（改过 periodicity）→ 与历史 != 行为一致，派发
    tmpl.last_generated_period = period_key("daily", today, 1)
    tmpl.periodicity = "weekly"
    assert should_spawn(tmpl, today)


def test_skip_watermark_key_spawned_today():
    """当前桶已派发：跳 N 次 = 压制接下来 N 个桶。"""
    today = datetime.date(2026, 9, 22)
    tmpl = PeriodicTemplate(base_title="日报", category="工作", periodicity="daily")
    tmpl.last_generated_period = period_key("daily", today, 1)
    tmpl.last_generated_period = skip_watermark_key(tmpl, today, 2)
    assert not should_spawn(tmpl, today + datetime.timedelta(days=1))
    assert not should_spawn(tmpl, today + datetime.timedelta(days=2))
    assert should_spawn(tmpl, today + datetime.timedelta(days=3))


def test_skip_watermark_key_pending_today():
    """当前桶未派发：跳 N 次 = 含今天共 N 个桶。"""
    today = datetime.date(2026, 9, 22)
    tmpl = PeriodicTemplate(base_title="待派", category="工作", periodicity="daily")
    tmpl.last_generated_period = period_key("daily", today - datetime.timedelta(days=1), 1)
    tmpl.last_generated_period = skip_watermark_key(tmpl, today, 1)
    assert not should_spawn(tmpl, today)
    assert should_spawn(tmpl, today + datetime.timedelta(days=1))


def test_advance_period_key_weekly_interval():
    today = datetime.date(2026, 9, 22)  # Tuesday
    tmpl = PeriodicTemplate(base_title="双周", category="工作", periodicity="weekly", interval=2)
    tmpl.last_generated_period = advance_period_key("weekly", today, 2, 1)
    assert not should_spawn(tmpl, today + datetime.timedelta(weeks=2))  # 水位桶内
    assert should_spawn(tmpl, today + datetime.timedelta(weeks=4))  # 下一桶


def test_next_spawn_date():
    today = datetime.date(2026, 9, 22)  # Tuesday
    # 已派发今天的 daily → 明天
    tmpl = PeriodicTemplate(base_title="日", category="工作", periodicity="daily")
    tmpl.last_generated_period = period_key("daily", today, 1)
    assert next_spawn_date(tmpl, today) == today + datetime.timedelta(days=1)
    # 暂停 → None
    tmpl.paused = True
    assert next_spawn_date(tmpl, today) is None
    tmpl.paused = False
    # 过期 → None
    tmpl.long_term = False
    tmpl.schedule_end_date = "2026-09-20"
    assert next_spawn_date(tmpl, today) is None
    # 今天待派 → 今天
    fresh = PeriodicTemplate(base_title="待", category="工作", periodicity="daily")
    assert next_spawn_date(fresh, today) == today
    # 已派发本周的 weekly → 下周一
    wk = PeriodicTemplate(base_title="周", category="工作", periodicity="weekly")
    wk.last_generated_period = period_key("weekly", today, 1)
    assert next_spawn_date(wk, today) == datetime.date(2026, 9, 28)


def test_build_due_instance():
    today = datetime.date(2026, 9, 22)
    tmpl = PeriodicTemplate(
        base_title="站会",
        category="工作",
        periodicity="daily",
        reminder={"enabled": True, "time_of_day": "09:30"},
        auto_abandon_on_overdue=True,
    )
    task = build_due_instance(tmpl, today)
    assert task is not None
    assert task.task_type == "periodic_instance"
    assert task.template_id == tmpl.template_id
    assert task.title.startswith("【") and "站会" in task.title
    assert task.deadline == today.isoformat()
    assert task.reminder is not None and task.reminder.enabled
    assert task.auto_abandon_on_overdue
    assert tmpl.last_generated_period == period_key("daily", today, 1)
    # 水位已推进：再调返回 None
    assert build_due_instance(tmpl, today) is None
    # 暂停模板永不构造
    tmpl.paused = True
    tmpl.last_generated_period = None
    assert build_due_instance(tmpl, today) is None
