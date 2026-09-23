# zentray/ui/controller.py
"""
托盘协调者 —— 事件路由 + 状态协调 + 扩展管理。

产品行为：
  - 无主窗口，仅顶栏托盘
  - 启动：先只显示应用图标
  - 首个任务进入轮播后：饼图 + 文字标题
"""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from zentray.services.task_service import TaskService
from zentray.services.pomodoro_service import PomodoroService
from zentray.services.settings_manager import SettingsManager
from zentray.ui.renderer import TrayRenderer
from zentray.ui.menu_builder import MenuBuilder

logger = logging.getLogger(__name__)


class TrayController(QObject):
    """托盘协调者"""

    def __init__(
        self,
        app: QApplication,
        task_service: TaskService,
        pomodoro_service: PomodoroService,
        renderer: TrayRenderer,
        menu_builder: MenuBuilder,
    ):
        super().__init__()
        self.app = app
        self.task_service = task_service
        self.pomodoro_service = pomodoro_service
        self.renderer = renderer
        self.menu_builder = menu_builder

        self._settings = SettingsManager()
        self._poll_count = 0
        self._last_label = None  # None = 尚未推送过
        self._last_icon = None
        # 启动阶段：仅应用图标，等首次轮播 tick 再显示饼图+标题
        self._carousel_started = False

        self.renderer.backend.action_received.connect(self.handle_action)
        self.pomodoro_service.time_updated.connect(self._on_pomodoro_tick)
        self.pomodoro_service.pomodoro_finished.connect(self._on_pomodoro_end)

        # 可靠轮播：重复定时器（挂到 self，避免被 GC）
        self.poll_timer = QTimer(self)
        try:
            from PySide6.QtCore import Qt as _Qt

            self.poll_timer.setTimerType(_Qt.TimerType.PreciseTimer)
        except Exception:
            pass
        self.poll_timer.timeout.connect(self._on_poll_tick)

        # 预选中任务（内部焦点），但顶栏仍保持「仅 app 图标」直到首轮轮播
        if self.task_service.get_current_task() is None:
            self.task_service.advance_rotation()

        # 启动占位：应用图标、无标题；菜单先建好
        self._show_boot_placeholder(update_menu=True)
        self.start_rotation()

        self.app.aboutToQuit.connect(self._on_about_to_quit)

    # ==========================================
    # 轮播控制
    # ==========================================

    def _show_boot_placeholder(self, update_menu: bool = True) -> None:
        """初始化：仅应用图标，不显示任务饼图/标题。"""
        self.renderer.set_state("app_icon", "")
        self._last_icon = "app_icon"
        self._last_label = ""
        logger.info("启动占位：仅应用图标，等待首个任务轮播")
        if update_menu:
            self._refresh_menu()

    def start_rotation(self) -> None:
        """按设置启动/重置轮播定时器。"""
        interval_ms = self._next_interval_ms()
        if self.poll_timer.isActive():
            self.poll_timer.stop()
        self.poll_timer.start(interval_ms)
        logger.info("轮播定时器已启动，间隔 %sms", interval_ms)

    def _next_interval_ms(self) -> int:
        task = self.task_service.get_current_task()
        if task:
            sec = self._settings.get_dwell_seconds(task.priority)
        else:
            sec = 3
        # 至少 1.5 秒，保证肉眼能看到标题切换
        return max(1500, int(sec * 1000))

    def handle_action(self, action_id: str) -> None:
        from .commands import dispatch

        if not dispatch(action_id, self):
            logger.debug("未识别的菜单 action: %s", action_id)

    def _on_poll_tick(self) -> None:
        """定时推进轮播并刷新顶栏标题。"""
        try:
            if self.pomodoro_service.is_active:
                if not self._carousel_started:
                    self._carousel_started = True
                    logger.info("首个轮播开始（番茄模式）")
                self.update_display(update_menu=False)
                return

            # 首次 tick：进入轮播展示（饼图 + 标题），再推进
            if not self._carousel_started:
                self._carousel_started = True
                # 确保有当前任务
                if self.task_service.get_current_task() is None:
                    self.task_service.advance_rotation()
                logger.info(
                    "首个任务开始轮播: %s",
                    getattr(self.task_service.get_current_task(), "title", None),
                )
                self.update_display(update_menu=False)
                self.poll_timer.setInterval(self._next_interval_ms())
                return

            prev = self.task_service.get_current_task()
            nxt = self.task_service.advance_rotation()
            self._poll_count += 1
            prev_t = prev.title if prev else None
            next_t = nxt.title if nxt else None
            if prev_t != next_t or self._poll_count <= 3:
                logger.info("轮播 #%s: %s -> %s", self._poll_count, prev_t, next_t)
            self.update_display(update_menu=False)

            self.poll_timer.setInterval(self._next_interval_ms())
        except Exception:
            logger.exception("轮播 tick 失败")
            self.poll_timer.setInterval(3000)

    def apply_settings(self) -> None:
        self._settings = SettingsManager.reload()
        # 空闲时同步专注时长；进行中不打断当前倒计时
        if hasattr(self.pomodoro_service, "sync_duration_from_settings"):
            self.pomodoro_service.sync_duration_from_settings()
        else:
            if not self.pomodoro_service.is_active:
                self.pomodoro_service.duration = (
                    self._settings.pomodoro.duration_minutes * 60
                )
        self.task_service.refresh_scheduler()
        if self.task_service.get_current_task() is None:
            self.task_service.advance_rotation()
        # 设置已在运行中：直接正常展示
        self._carousel_started = True
        self.update_display(update_menu=True)
        self.start_rotation()

    def update_display(self, update_menu: bool = True) -> None:
        """更新顶栏：左侧优先级/番茄饼图 + 标题或倒计时。"""
        from zentray.resources import tray_pie_icon_name, tray_tomato_icon_name

        # 启动阶段未进入轮播：强制仅应用图标
        if not self._carousel_started and not self.pomodoro_service.is_active:
            self._show_boot_placeholder(update_menu=update_menu)
            return

        if self.pomodoro_service.is_active:
            # 左侧：随倒计时填充的番茄饼图；右侧：文案或倒计时
            pct = self.pomodoro_service.get_elapsed_progress_percent()
            icon = tray_tomato_icon_name(pct)
            rem = self.pomodoro_service.get_remaining()
            pomo = self._settings.pomodoro
            mode = getattr(pomo, "tray_display", "countdown") or "countdown"
            if mode == "text":
                text = (getattr(pomo, "tray_text", None) or "专注中").strip() or "专注中"
            else:
                text = f"{rem // 60:02d}:{rem % 60:02d}"
        else:
            task = self.task_service.get_current_task()
            if task:
                # 扇形填充 = 子任务完成比例（10% 步进；无子任务空饼）
                subs = getattr(task, "subtasks", None) or []
                pct = (
                    int(round(sum(1 for s in subs if s.get("status") == "done") * 10.0 / len(subs))) * 10
                    if subs
                    else 0
                )
                icon = tray_pie_icon_name(task.priority, pct)
                text = self.task_service.get_task_display_title(task)
                if not text:
                    text = task.title or "ZenTray"
            else:
                icon = "app_icon"
                text = "ZenTray · 暂无待办"

        # 原子推送图标+标题，避免换饼图时丢文字
        if icon != self._last_icon or text != self._last_label:
            logger.debug("顶栏 state: icon=%s text=%s", icon, text)
        self.renderer.set_state(icon, text)
        self._last_icon = icon
        self._last_label = text

        if update_menu:
            self._refresh_menu()

    def _refresh_menu(self) -> None:
        items = self.menu_builder.build_main_menu(
            is_pomodoro=self.pomodoro_service.is_active,
        )
        if self.menu_builder.should_update(items):
            self.renderer.update_menu(items)

    def reload_data(self) -> None:
        self.task_service.refresh_scheduler()
        if self.task_service.get_current_task() is None:
            self.task_service.advance_rotation()
        # 数据刷新时若已在轮播，保持；否则仍等 tick
        if self._carousel_started:
            self.update_display(update_menu=True)
        else:
            self._show_boot_placeholder(update_menu=True)
        if not self.poll_timer.isActive():
            self.start_rotation()

    def _on_pomodoro_tick(self, seconds: int) -> None:
        if not self._carousel_started:
            self._carousel_started = True
        self.update_display(update_menu=False)

    def _on_pomodoro_end(self) -> None:
        self.renderer.show_notification("专注结束", "番茄钟已完成，休息一下吧！")
        self._carousel_started = True
        self.update_display(update_menu=True)
        self.start_rotation()

    def _on_about_to_quit(self) -> None:
        try:
            self.poll_timer.stop()
        except Exception:
            pass
        try:
            self.renderer.shutdown()
        except Exception:
            pass
