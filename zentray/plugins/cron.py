"""最小 5 字段 cron 表达式解析与匹配（分 时 日 月 周）。

支持: * 、*/n 、a-b 、a-b/n 、逗号列表（可混合）。不支持的写法一律
抛 CronError，由 manifest 装载期捕获报错。

dom/dow 语义遵循 vixie-cron：两者都受限时取 OR（任一匹配即触发）。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, NamedTuple, Set

_FIELDS = (
    # (字段名, 下界, 上界, 是否 dow)
    ("minute", 0, 59, False),
    ("hour", 0, 23, False),
    ("dom", 1, 31, False),
    ("month", 1, 12, False),
    ("dow", 0, 7, True),
)


class CronError(ValueError):
    """cron 表达式非法。"""


def _parse_field(spec: str, lo: int, hi: int, is_dow: bool) -> Tuple[Set[int], bool]:
    """解析单字段 → (匹配值集合, 是否受限)。

    受限 = 非 `*`（dom/dow 的 OR 语义需要区分）。
    """
    values: Set[int] = set()
    restricted = spec.strip() != "*"

    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise CronError(f"空字段段: {spec!r}")
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            try:
                step = int(step_s)
            except ValueError:
                raise CronError(f"步长非法: {step_s!r}") from None
            if step < 1:
                raise CronError(f"步长必须 >=1: {step_s!r}")

        if part in ("*", ""):
            start, end = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            try:
                start, end = int(a), int(b)
            except ValueError:
                raise CronError(f"范围非法: {part!r}") from None
            if start > end:
                raise CronError(f"范围起点大于终点: {part!r}")
        else:
            try:
                start = end = int(part)
            except ValueError:
                raise CronError(f"数值非法: {part!r}") from None

        if start < lo or end > hi:
            raise CronError(f"数值越界 [{lo}-{hi}]: {part!r}")
        values.update(range(start, end + 1, step))

    if is_dow and 7 in values:
        values.discard(7)
        values.add(0)  # 0 与 7 都是周日
    return values, restricted


class ParsedCron(NamedTuple):
    minute: Set[int]
    hour: Set[int]
    dom: Set[int]
    month: Set[int]
    dow: Set[int]
    dom_restricted: bool
    dow_restricted: bool


def parse(expr: str) -> ParsedCron:
    """解析整条表达式 → ParsedCron。"""
    parts = expr.split()
    if len(parts) != 5:
        raise CronError(f"必须是 5 个字段（分 时 日 月 周）: {expr!r}")

    sets: List[Set[int]] = []
    dom_restricted = dow_restricted = False
    for spec, (name, lo, hi, is_dow) in zip(parts, _FIELDS):
        try:
            vals, restricted = _parse_field(spec, lo, hi, is_dow)
        except CronError as e:
            raise CronError(f"字段 {name}: {e}") from None
        sets.append(vals)
        if name == "dom":
            dom_restricted = restricted
        if name == "dow":
            dow_restricted = restricted
    return ParsedCron(*sets, dom_restricted, dow_restricted)


def matches(expr: str, now: datetime) -> bool:
    """now 是否命中该 cron 表达式（秒级忽略，按分钟判定）。"""
    p = parse(expr)
    if now.minute not in p.minute or now.hour not in p.hour or now.month not in p.month:
        return False
    # Python weekday 周一=0；cron dow 周日=0
    cron_dow = (now.weekday() + 1) % 7
    dom_hit = now.day in p.dom
    dow_hit = cron_dow in p.dow
    # vixie-cron: dom 与 dow 均受限时 OR，否则 AND（`*` 一侧恒真）
    if p.dom_restricted and p.dow_restricted:
        return dom_hit or dow_hit
    return dom_hit and dow_hit
