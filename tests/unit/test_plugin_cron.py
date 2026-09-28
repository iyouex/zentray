"""cron 表达式解析与匹配测试。"""
from datetime import datetime

import pytest

from zentray.plugins import cron


def test_star_matches_every_minute():
    assert cron.matches("* * * * *", datetime(2026, 9, 28, 9, 30, 12))


def test_step():
    expr = "*/15 * * * *"
    assert cron.matches(expr, datetime(2026, 9, 28, 9, 0))
    assert cron.matches(expr, datetime(2026, 9, 28, 9, 45))
    assert not cron.matches(expr, datetime(2026, 9, 28, 9, 20))


def test_range():
    expr = "* 9-17 * * *"
    assert cron.matches(expr, datetime(2026, 9, 28, 9, 0))
    assert cron.matches(expr, datetime(2026, 9, 28, 17, 59))
    assert not cron.matches(expr, datetime(2026, 9, 28, 8, 0))
    assert not cron.matches(expr, datetime(2026, 9, 28, 18, 0))


def test_list_mixed():
    expr = "5,20-22,40 * * * *"
    assert cron.matches(expr, datetime(2026, 9, 28, 10, 5))
    assert cron.matches(expr, datetime(2026, 9, 28, 10, 21))
    assert cron.matches(expr, datetime(2026, 9, 28, 10, 40))
    assert not cron.matches(expr, datetime(2026, 9, 28, 10, 6))
    assert not cron.matches(expr, datetime(2026, 9, 28, 10, 23))


def test_range_with_step():
    expr = "0 9-17/2 * * *"
    assert cron.matches(expr, datetime(2026, 9, 28, 9, 0))
    assert cron.matches(expr, datetime(2026, 9, 28, 11, 0))
    assert cron.matches(expr, datetime(2026, 9, 28, 17, 0))
    assert not cron.matches(expr, datetime(2026, 9, 28, 10, 0))


def test_dow_7_is_sunday():
    # 2026-09-27 是周日
    assert cron.matches("* * * * 7", datetime(2026, 9, 27, 12, 0))
    assert cron.matches("* * * * 0", datetime(2026, 9, 27, 12, 0))
    assert not cron.matches("* * * * 1", datetime(2026, 9, 27, 12, 0))
    # 周一（2026-09-28）
    assert cron.matches("* * * * 1", datetime(2026, 9, 28, 12, 0))


def test_dom_dow_or_semantics():
    # vixie-cron: dom 与 dow 均受限 → OR。
    # 2026-09-28 是 28 号、周一：dow 命中即可
    assert cron.matches("0 0 15 * 1", datetime(2026, 9, 28, 0, 0))
    # 2026-09-15 是 15 号、周二：dom 命中即可
    assert cron.matches("0 0 15 * 1", datetime(2026, 9, 15, 0, 0))
    # 两者都不命中
    assert not cron.matches("0 0 20 * 3", datetime(2026, 9, 28, 0, 0))


def test_dom_dow_and_when_one_star():
    # dom=`*` → 只看 dow；2026-09-28 周一
    assert cron.matches("0 0 * * 1", datetime(2026, 9, 28, 0, 0))
    assert not cron.matches("0 0 * * 2", datetime(2026, 9, 28, 0, 0))
    # dow=`*` → 只看 dom
    assert cron.matches("0 0 28 * *", datetime(2026, 9, 28, 0, 0))
    assert not cron.matches("0 0 27 * *", datetime(2026, 9, 28, 0, 0))


def test_month_field():
    assert cron.matches("0 0 1 9 *", datetime(2026, 9, 1, 0, 0))
    assert not cron.matches("0 0 1 10 *", datetime(2026, 9, 1, 0, 0))


@pytest.mark.parametrize(
    "expr",
    [
        "* * * *",            # 字段数不足
        "* * * * * *",        # 字段数超
        "60 * * * *",         # 分越界
        "* 24 * * *",         # 时越界
        "* * 0 * *",          # 日越界（下界 1）
        "* * 32 * *",         # 日越界（上界 31）
        "* * * 0 *",          # 月越界
        "* * * * 8",          # 周越界（0-7）
        "*/0 * * * *",        # 步长 0
        "a * * * *",          # 非数值
        "5-1 * * * *",        # 范围倒置
        "1,,2 * * * *",       # 空段
    ],
)
def test_invalid_expressions(expr):
    with pytest.raises(cron.CronError):
        cron.parse(expr)
