# zentray/services/pomodoro_service.py
"""
番茄钟专注服务 —— 专注/短休/长休循环状态机。

阶段流：idle → focus → short_break / long_break → idle → focus …
- 专注结束：按设置 auto_start_breaks 自动进入休息；每 long_break_every 个专注进长休
- 休息结束：按设置 auto_start_focus 自动开始下一段专注（绑定任务沿用）
- pomodoro_finished 语义不变（专注段结束时发出）；另发 break_finished（休息结束/跳过）
通过 Qt Signal 与 UI 层解耦。
"""
from PySide6.QtCore import QTimer, Signal, QObject
from zentray.config import POMODORO_MINUTES

PHASE_IDLE = "idle"
PHASE_FOCUS = "focus"
PHASE_SHORT_BREAK = "short_break"
PHASE_LONG_BREAK = "long_break"


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


def _settings_break_minutes(long_break: bool) -> int:
    try:
        from zentray.services.settings_manager import SettingsManager

        p = SettingsManager().pomodoro
        m = int(p.long_break_minutes if long_break else p.short_break_minutes)
        return max(1, min(60, m))
    except Exception:
        return 15 if long_break else 5


def _settings_long_break_every() -> int:
    try:
        from zentray.services.settings_manager import SettingsManager

        m = int(SettingsManager().pomodoro.long_break_every)
        return max(0, min(12, m))  # 0=只用短休
    except Exception:
        return 4


def _settings_auto(flag: str) -> bool:
    try:
        from zentray.services.settings_manager import SettingsManager

        return bool(getattr(SettingsManager().pomodoro, flag))
    except Exception:
        return flag == "auto_start_breaks"


class PomodoroService(QObject):
    """番茄钟专注服务"""

    time_updated = Signal(int)       # 剩余秒数更新
    pomodoro_finished = Signal()     # 专注段结束
    break_finished = Signal()        # 休息段结束（自然走完或被跳过）

    def __init__(self, duration_minutes: int = None):
        super().__init__()
        mins = duration_minutes if duration_minutes is not None else _settings_duration_minutes()
        self.duration = max(1, int(mins)) * 60  # 转换为秒
        self.session_total = self.duration  # 当前阶段总时长（饼图用）
        self.remaining_seconds = 0
        self.phase = PHASE_IDLE
        self.completed_focus = 0      # 长休节奏：自上次长休后完成的专注段数
        self.task_id = ""             # 本轮专注绑定的任务（可空）
        self.task_title = ""
        self.last_focus_seconds = 0   # 上一段专注实际秒数（完成或中止时记录，供日志）

        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)

    @property
    def is_active(self) -> bool:
        """整个循环活跃期（含休息）——轮播抢占/脚本双向拦截均以此为准。"""
        return self.phase != PHASE_IDLE

    @property
    def is_break(self) -> bool:
        return self.phase in (PHASE_SHORT_BREAK, PHASE_LONG_BREAK)

    def sync_duration_from_settings(self) -> None:
        """空闲时把服务时长对齐到设置（不打断进行中的番茄）。"""
        if self.is_active:
            return
        self.duration = _settings_duration_minutes() * 60
        self.session_total = self.duration

    def start(self, task_id: str = "", task_title: str = "") -> None:
        """开始专注计时——每次启动都按当前设置的专注时长重置。"""
        self.task_id = str(task_id or "")
        self.task_title = str(task_title or "")
        self._enter_focus()

    def stop(self) -> int:
        """中止（任何阶段）直接回 idle；返回本段已进行秒数（专注中止日志用）。"""
        elapsed = max(0, self.session_total - self.remaining_seconds) if self.is_active else 0
        if self.phase == PHASE_FOCUS:
            self.last_focus_seconds = elapsed
        self._reset_idle()
        return elapsed

    def skip_break(self) -> None:
        """跳过休息 → idle（长休节奏计数保留）。"""
        if not self.is_break:
            return
        self._reset_idle()
        self.break_finished.emit()

    def extend(self, additional_minutes: int = None) -> None:
        """延长专注时间（默认使用设置中的延长步长；仅专注段生效）"""
        if additional_minutes is None:
            additional_minutes = _settings_extend_minutes()
        add = max(1, int(additional_minutes)) * 60
        if self.phase == PHASE_FOCUS:
            self.remaining_seconds += add
            self.session_total += add

    def get_remaining(self) -> int:
        """获取剩余秒数"""
        return self.remaining_seconds

    def get_elapsed_progress_percent(self) -> int:
        """已消耗进度 0–100（用于番茄/休息饼图填充）。"""
        total = max(1, int(self.session_total or self.duration or 1))
        rem = max(0, int(self.remaining_seconds or 0))
        elapsed = max(0, total - rem)
        return max(0, min(100, int(round(elapsed * 100 / total))))

    # ==========================================
    # 内部：阶段流转
    # ==========================================

    def _reset_idle(self) -> None:
        self.phase = PHASE_IDLE
        self.timer.stop()
        self.remaining_seconds = 0
        self.task_id = ""
        self.task_title = ""
        # 停表后重新对齐设置，便于下次菜单/启动一致
        self.duration = _settings_duration_minutes() * 60
        self.session_total = self.duration

    def _enter_focus(self) -> None:
        self.duration = _settings_duration_minutes() * 60
        self.session_total = self.duration
        self.remaining_seconds = self.duration
        self.phase = PHASE_FOCUS
        self.timer.start(1000)

    def _enter_break(self) -> None:
        every = _settings_long_break_every()
        if every > 0 and self.completed_focus > 0 and self.completed_focus % every == 0:
            self.phase = PHASE_LONG_BREAK
            self.session_total = _settings_break_minutes(True) * 60
        else:
            self.phase = PHASE_SHORT_BREAK
            self.session_total = _settings_break_minutes(False) * 60
        self.remaining_seconds = self.session_total
        self.timer.start(1000)

    def _tick(self) -> None:
        """每秒回调"""
        if self.phase == PHASE_IDLE:
            self.timer.stop()
            return
        if self.remaining_seconds > 0:
            self.remaining_seconds -= 1
            self.time_updated.emit(self.remaining_seconds)
            return

        # 阶段走完
        self.timer.stop()
        if self.phase == PHASE_FOCUS:
            self.completed_focus += 1
            self.last_focus_seconds = self.session_total
            self.pomodoro_finished.emit()
            if _settings_auto("auto_start_breaks"):
                self._enter_break()
            else:
                self._reset_idle()  # 不自动休息：计时结束待下次手动专注
        elif self.is_break:
            was_long = self.phase == PHASE_LONG_BREAK
            auto_focus = _settings_auto("auto_start_focus")
            task_id, task_title = self.task_id, self.task_title
            if was_long:
                self.completed_focus = 0
            self._reset_idle()
            self.break_finished.emit()
            if auto_focus:
                self.start(task_id, task_title)  # 沿用绑定开始下一段专注
