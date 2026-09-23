# zentray/services/pomodoro_service.py
"""
番茄钟专注服务 —— 独立的番茄钟计时与状态管理。

将原 TrayManager 中的番茄钟逻辑抽取为独立服务，
通过 Qt Signal 与 UI 层解耦。
"""
from PySide6.QtCore import QTimer, Signal, QObject
from zentray.config import POMODORO_MINUTES


def _settings_duration_minutes() -> int:
    """始终读最新设置，避免菜单显示与倒计时脱节。"""
    try:
        from zentray.services.settings_manager import SettingsManager

        m = int(SettingsManager().pomodoro.duration_minutes)
        return max(1, min(180, m))
    except Exception:
        return int(POMODORO_MINUTES or 25)


def _settings_extend_minutes() -> int:
    try:
        from zentray.services.settings_manager import SettingsManager

        m = int(SettingsManager().pomodoro.extend_minutes)
        return max(1, min(60, m))
    except Exception:
        return 10


class PomodoroService(QObject):
    """番茄钟专注服务"""

    time_updated = Signal(int)       # 剩余秒数更新
    pomodoro_finished = Signal()     # 专注结束

    def __init__(self, duration_minutes: int = None):
        super().__init__()
        mins = duration_minutes if duration_minutes is not None else _settings_duration_minutes()
        self.duration = max(1, int(mins)) * 60  # 转换为秒
        self.session_total = self.duration  # 含延长后的本轮总时长（饼图用）
        self.remaining_seconds = 0
        self.is_active = False

        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)

    def sync_duration_from_settings(self) -> None:
        """空闲时把服务时长对齐到设置（不打断进行中的番茄）。"""
        if self.is_active:
            return
        self.duration = _settings_duration_minutes() * 60
        self.session_total = self.duration

    def start(self) -> None:
        """开始专注计时——每次启动都按当前设置的专注时长重置。"""
        self.duration = _settings_duration_minutes() * 60
        self.session_total = self.duration
        self.remaining_seconds = self.duration
        self.is_active = True
        self.timer.start(1000)  # 每秒触发一次

    def stop(self) -> None:
        """中止专注计时"""
        self.is_active = False
        self.timer.stop()
        self.remaining_seconds = 0
        # 停表后重新对齐设置，便于下次菜单/启动一致
        self.duration = _settings_duration_minutes() * 60
        self.session_total = self.duration

    def extend(self, additional_minutes: int = None) -> None:
        """延长专注时间（默认使用设置中的延长步长）"""
        if additional_minutes is None:
            additional_minutes = _settings_extend_minutes()
        add = max(1, int(additional_minutes)) * 60
        if self.is_active:
            self.remaining_seconds += add
            self.session_total += add

    def get_remaining(self) -> int:
        """获取剩余秒数"""
        return self.remaining_seconds

    def get_elapsed_progress_percent(self) -> int:
        """已消耗进度 0–100（用于番茄饼图填充）。"""
        total = max(1, int(self.session_total or self.duration or 1))
        rem = max(0, int(self.remaining_seconds or 0))
        elapsed = max(0, total - rem)
        return max(0, min(100, int(round(elapsed * 100 / total))))

    def _tick(self) -> None:
        """每秒回调"""
        if self.remaining_seconds > 0:
            self.remaining_seconds -= 1
            self.time_updated.emit(self.remaining_seconds)
        else:
            self.is_active = False
            self.timer.stop()
            self.pomodoro_finished.emit()
