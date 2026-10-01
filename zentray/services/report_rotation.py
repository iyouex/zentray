"""待查看报告的托盘轮播登记表。

每日计划/复盘与插件运行报告完成时，若通知未被点击查看，报告提示临时
加入顶栏任务轮播，到期或被查看后自动退出。纯数据结构，无 Qt 依赖，
由 TrayController 持有并在轮播 tick 中交替展示。
"""
import time


class ReportRotation:
    """key 唯一（run:<run_id> / ai:<报告路径>）；同 key 再完成 = 刷新时长。"""

    def __init__(self):
        self._slots = []  # [{key, text, expires_at(单调时钟)}]

    def add(self, key: str, text: str, minutes: int, now: float = None) -> None:
        now = time.monotonic() if now is None else now
        minutes = max(1, int(minutes or 0))
        self._slots = [s for s in self._slots if s["key"] != key]
        self._slots.append({"key": key, "text": text, "expires_at": now + minutes * 60})

    def mark_viewed(self, key: str) -> bool:
        """报告被打开：移出轮播。返回是否确实移除了一个槽位。"""
        before = len(self._slots)
        self._slots = [s for s in self._slots if s["key"] != key]
        return len(self._slots) != before

    def active(self, now: float = None) -> list:
        """清理过期槽位后返回仍存活的列表（浅拷贝）。"""
        now = time.monotonic() if now is None else now
        if any(s["expires_at"] <= now for s in self._slots):
            self._slots = [s for s in self._slots if s["expires_at"] > now]
        return list(self._slots)
