"""系统日历订阅源：模板未来日程投影、ics 构建（去重/头字段）、开关联动与 UID 稳定。"""
import datetime
import json

from zentray.core.models import PeriodicTemplate, Task
from zentray.core.periodic import project_future_instances
from zentray.services import data_migration as dm
from zentray.services.calendar_feed import (
    EMPTY_ICS,
    CalendarFeedService,
    build_tasks_ics,
)
from zentray.services.settings_manager import SettingsManager

TODAY = datetime.date(2026, 10, 14)  # 周三


def _tmpl(**kw):
    base = dict(
        base_title="打卡",
        category="工作",
        periodicity="daily",
        calendar_enabled=True,
    )
    base.update(kw)
    return PeriodicTemplate(**base)


# ---------- 投影 ----------


def test_project_daily_count_default():
    # 未设截止时分的日模板：投影无截止（日历侧回落派发日）
    out = project_future_instances(_tmpl(), TODAY)
    assert [(d.isoformat(), dl) for d, dl in out] == [
        ("2026-10-14", ""),
        ("2026-10-15", ""),
        ("2026-10-16", ""),
        ("2026-10-17", ""),
    ]
    # 设了截止时分：截止=派发日当天
    out2 = project_future_instances(_tmpl(due_time="18:00"), TODAY)
    assert [dl for _, dl in out2] == ["2026-10-14", "2026-10-15", "2026-10-16", "2026-10-17"]


def test_project_disabled_returns_empty():
    assert project_future_instances(_tmpl(calendar_enabled=False), TODAY) == []


def test_project_days_mode_truncation():
    out = project_future_instances(
        _tmpl(calendar_horizon_mode="days", calendar_horizon_value=7), TODAY
    )
    assert len(out) == 7
    assert out[-1][0] == TODAY + datetime.timedelta(days=6)


def test_project_weekly_one_per_week():
    # 无水位：should_spawn 每天为真，跨周桶去重后每周只投影一次
    t = _tmpl(
        periodicity="weekly",
        deadline_weekday=2,
        calendar_horizon_mode="count",
        calendar_horizon_value=3,
    )
    out = project_future_instances(t, TODAY)
    assert len(out) == 3
    # 投影日跨周桶递增（周中起步可仅隔 5 天）；截止=所在周周三，恒隔 7 天
    spawns = [d for d, _ in out]
    assert all(b > a for a, b in zip(spawns, spawns[1:]))
    assert out[0] == (TODAY, "2026-10-14")
    assert out[1][1] == "2026-10-21"
    assert out[2][1] == "2026-10-28"


def test_project_monthly_day_of_month():
    t = _tmpl(
        periodicity="monthly",
        deadline_day_of_month=1,
        calendar_horizon_mode="count",
        calendar_horizon_value=2,
    )
    out = project_future_instances(t, TODAY)
    # 首个投影在今天所在月（dom 已过=本月 1 号），其后逐月 1 号
    assert [dl for _, dl in out] == ["2026-10-01", "2026-11-01"]


def test_project_interval_bucketing():
    t = _tmpl(interval=2, calendar_horizon_mode="count", calendar_horizon_value=2)
    out = project_future_instances(t, TODAY)
    assert len(out) == 2
    a, b = out
    assert 1 <= (b[0] - a[0]).days <= 2  # 桶界对齐差异，间隔 1 或 2 天


def test_project_respects_pause_end_and_watermark():
    assert project_future_instances(_tmpl(paused=True), TODAY) == []
    ended = _tmpl(long_term=False, schedule_end_date="2026-10-13")
    assert project_future_instances(ended, TODAY) == []
    # 跳过水位压到 today+2 桶：today+3 起才恢复投影
    from zentray.core.periodic import _bucket_index

    skipped = _tmpl()
    cur = _bucket_index("daily", TODAY, 1)
    skipped.last_generated_period = f"D{cur + 2}"
    out = project_future_instances(skipped, TODAY)
    assert out and out[0][0] == TODAY + datetime.timedelta(days=3)


def test_project_clamps_invalid_values():
    # mode 无效回落 count；value 钳制不炸且输出有序
    out = project_future_instances(
        _tmpl(calendar_horizon_mode="bogus", calendar_horizon_value=4), TODAY
    )
    assert len(out) == 4
    days = [d for d, _ in out]
    assert days == sorted(days)


# ---------- ics 构建 ----------


def test_build_ics_headers_and_uid_stability():
    t = Task(title="任务A", category="工作", deadline="2026-10-20")
    ics1 = build_tasks_ics([t], [], today=TODAY)
    ics2 = build_tasks_ics([t], [], today=TODAY)
    assert "X-WR-CALNAME:ZenTray" in ics1
    assert "X-PUBLISHED-TTL:PT1H" in ics1
    assert f"UID:zentray-{t.id}@zentray.local" in ics1
    # UID 跨刷新稳定（DTSTAMP 变化无关紧要，只比对 UID 行集合）
    uids1 = {ln for ln in ics1.splitlines() if ln.startswith("UID:")}
    uids2 = {ln for ln in ics2.splitlines() if ln.startswith("UID:")}
    assert uids1 == uids2


def test_build_ics_projection_dedup_with_real_instance():
    tmpl = _tmpl(
        template_id="tp-1",
        calendar_horizon_mode="count",
        calendar_horizon_value=4,
    )
    # 今天已派发真实实例（template_id + deadline 与投影同日）→ 投影去重
    real = Task(
        title="【x】打卡",
        category="工作",
        deadline="2026-10-14",
        task_type="periodic_instance",
        template_id="tp-1",
    )
    ics = build_tasks_ics([real], [tmpl], today=TODAY)
    assert ics.count("BEGIN:VEVENT") == 4  # 真实 1 + 投影 3（今天被去重）
    assert "UID:zentray-tpl-tp-1-2026-10-14@zentray.local" not in ics
    assert "UID:zentray-tpl-tp-1-2026-10-15@zentray.local" in ics


def test_build_ics_delivery_events():
    # 额外弹窗时间每行一条 30 分钟定时事件（⏱ 提醒 · 标题）
    t = Task(
        title="需求B",
        category="工作",
        deadline="2026-10-20",
        deliveries=[
            {"at": "2026-10-18T09:30", "notify": True},
            {"at": "2026-10-20T18:00", "notify": False},
        ],
    )
    ics = build_tasks_ics([t], [], today=TODAY)
    assert ics.count("BEGIN:VEVENT") == 3  # 截止全天事件 + 两个弹窗事件
    assert "UID:zentray-" + t.id + "-dl0@zentray.local" in ics
    assert "DTSTART:20261018T093000" in ics
    assert "SUMMARY:⏱ 提醒 ·" in ics


def test_build_ics_due_popup_event():
    # 截止时刻弹窗：popup_at_due 投影 due 时刻 30 分钟事件；开关关闭不投影
    t = Task(
        title="上线",
        category="工作",
        deadline="2026-10-20",
        due_time="18:00",
        popup_at_due=True,
    )
    ics = build_tasks_ics([t], [], today=TODAY)
    assert "UID:zentray-" + t.id + "-due@zentray.local" in ics
    assert "DTSTART:20261020T180000" in ics
    t.popup_at_due = False
    ics2 = build_tasks_ics([t], [], today=TODAY)
    assert "UID:zentray-" + t.id + "-due@zentray.local" not in ics2


# ---------- 订阅源开关联动 ----------


def _write_settings(enabled: bool, tmp_data_dir):
    sf = tmp_data_dir / "settings.json"
    sf.write_text(json.dumps({"calendar": {"enabled": enabled}}), encoding="utf-8")
    SettingsManager.reload()


def test_feed_disabled_no_file_then_enable_and_clear(tmp_data_dir):
    svc = CalendarFeedService.instance()
    tasks = [Task(title="任务A", category="工作", deadline="2026-10-20")]
    _write_settings(False, tmp_data_dir)
    svc.refresh(tasks, [])
    assert not svc.feed_path.exists()  # 未启用且无文件：不创建
    _write_settings(True, tmp_data_dir)
    svc.refresh(tasks, [])
    text = svc.feed_path.read_text(encoding="utf-8")
    assert "BEGIN:VEVENT" in text and "任务A" in text
    # 再刷新一次：UID 集合稳定
    svc.refresh(tasks, [])
    uids = {
        ln
        for ln in svc.feed_path.read_text(encoding="utf-8").splitlines()
        if ln.startswith("UID:")
    }
    assert uids and all("@zentray.local" in u for u in uids)
    # 关开关 → 空日历（订阅方自动清空）；按字节比对（read_text 会归一化 CRLF）
    _write_settings(False, tmp_data_dir)
    svc.refresh(tasks, [])
    raw = svc.feed_path.read_bytes().decode("utf-8")
    assert "BEGIN:VEVENT" not in raw
    assert raw == EMPTY_ICS


def test_settings_calendar_roundtrip(tmp_data_dir):
    sf = tmp_data_dir / "settings.json"
    sf.write_text(json.dumps({"calendar": {"enabled": True}}), encoding="utf-8")
    assert SettingsManager.reload().calendar.enabled is True
    SettingsManager().save()
    data = json.loads(sf.read_text(encoding="utf-8"))
    assert data["calendar"] == {"enabled": True}


def test_backup_sections_include_calendar():
    assert "calendar" in dm.SETTINGS_SECTIONS
