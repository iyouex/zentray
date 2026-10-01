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
from zentray.plugins.loader import PluginLoader
from zentray.plugins.runtime import PluginRuntime
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

        # 插件运行时（信号必须连 QObject 绑定方法：发射方在 python 线程，
        # AutoConnection 会排队回主线程；连 lambda 会进错误线程）
        self.plugin_runtime = PluginRuntime()
        self.plugin_loader = PluginLoader()
        self._ops_plugins = []
        self._ops_active = False
        self._ops_tray_text = ""

        self.renderer.backend.action_received.connect(self.handle_action)
        self.pomodoro_service.time_updated.connect(self._on_pomodoro_tick)
        self.pomodoro_service.pomodoro_finished.connect(self._on_pomodoro_end)
        self.pomodoro_service.break_finished.connect(self._on_break_end)
        self.plugin_runtime.log_line.connect(self._on_ops_log)
        self.plugin_runtime.script_finished.connect(self._on_ops_finished)
        self.plugin_runtime.busy_changed.connect(self._on_ops_busy)
        self.plugin_runtime.run_report.connect(self._on_ops_report)

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
        self.reload_ops_plugins()
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

    def reload_ops_plugins(self) -> None:
        """按设置扫描插件。"""
        from zentray.resources import get_resource_path

        ops = self._settings.ops
        if not ops.enabled:
            self._ops_plugins = []
            return
        # 开发态：仓库根 bundled_plugins；打包态：PyInstaller 解压目录
        bundled = get_resource_path("bundled_plugins")
        user = self._settings.get_ops_user_plugins_dir()
        self._ops_plugins = self.plugin_loader.scan(
            bundled_dir=bundled if bundled.is_dir() else None,
            user_dir=user,
        )
        logger.info(
            "插件已加载 %s 个（失败 %s）",
            len(self._ops_plugins),
            len(self.plugin_loader.failures),
        )

    def _on_poll_tick(self) -> None:
        """定时推进轮播并刷新顶栏标题。"""
        try:
            if self._ops_active or self.plugin_runtime.is_busy:
                # 脚本抢占：不推进任务轮播，仅保持 ops 文案
                if not self._carousel_started:
                    self._carousel_started = True
                self.update_display(update_menu=False)
                return

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
        self.reload_ops_plugins()
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
        """更新顶栏：左侧优先级/番茄/休息饼图 + 标题或倒计时。"""
        from zentray.resources import tray_break_icon_name, tray_pie_icon_name, tray_tomato_icon_name

        # 启动阶段未进入轮播：强制仅应用图标
        if (
            not self._carousel_started
            and not self.pomodoro_service.is_active
            and not self._ops_active
        ):
            self._show_boot_placeholder(update_menu=update_menu)
            return

        if self._ops_active or self.plugin_runtime.is_busy:
            icon = "app_icon"
            text = (self._ops_tray_text or "⚡ 脚本运行中")[:50]
        elif self.pomodoro_service.is_break:
            # 休息段：茶绿饼图 + 倒计时（自定义文案对休息无意义）
            pct = self.pomodoro_service.get_elapsed_progress_percent()
            icon = tray_break_icon_name(pct)
            rem = self.pomodoro_service.get_remaining()
            text = f"{rem // 60:02d}:{rem % 60:02d}"
        elif self.pomodoro_service.is_active:
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
            # 绑定任务的专注：右侧文字带任务标题后缀（截断由托盘层统一处理）
            focus_title = (self.pomodoro_service.task_title or "").strip()
            if focus_title:
                text = f"{text} · {focus_title}"
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
        pomo = self.pomodoro_service
        items = self.menu_builder.build_main_menu(
            is_pomodoro=pomo.is_active,
            ops_enabled=bool(self._settings.ops.enabled),
            ops_plugins=self._ops_plugins,
            ops_busy=self.plugin_runtime.is_busy or self._ops_active,
            pomodoro_phase=pomo.phase,
            pomodoro_today=self._pomodoro_today_stats(),
            focus_task_title=pomo.task_title if pomo.phase == "focus" else "",
            pomodoro_label_format=self._settings.pomodoro.menu_label_format,
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

    # ==========================================
    # 番茄钟循环（启动/中止/阶段结束）
    # ==========================================

    def start_pomodoro(self, task_id: str = None) -> bool:
        """开始专注（可绑定任务）。托盘菜单与任务列表 🍅 按钮共用此入口。"""
        if getattr(self, "plugin_runtime", None) and (
            self.plugin_runtime.is_busy or getattr(self, "_ops_active", False)
        ):
            self.renderer.show_notification("番茄钟", "脚本运行中，请稍后再开始专注。")
            return False
        if self.pomodoro_service.is_active:
            return False  # 循环进行中（含休息段）不重复启动
        tid = str(task_id or "")
        title = ""
        if tid:
            task = self.task_service.find_task(tid)
            if task is None:
                tid = ""  # 任务已不存在：降级为无绑定
            else:
                title = task.title or ""
        self.pomodoro_service.start(tid, title)
        self.update_display()
        return True

    def stop_pomodoro(self) -> None:
        """中止当前阶段；专注段按已专注时长记日志（≥1 分钟才记）。"""
        was_focus = self.pomodoro_service.phase == "focus"
        task_id = self.pomodoro_service.task_id
        task_title = self.pomodoro_service.task_title
        elapsed = self.pomodoro_service.stop()
        if was_focus and elapsed >= 60:
            self._log_focus(int(round(elapsed / 60.0)), task_id, task_title, aborted=True)
        self.update_display()

    def _log_focus(self, minutes: int, task_id: str, task_title: str, *, aborted: bool) -> None:
        try:
            from zentray.services.activity_log import log_event

            log_event(
                "pomodoro",
                "pomodoro_abort" if aborted else "pomodoro_done",
                title=task_title or "专注",
                detail=("中止专注" if aborted else "完成专注") + f"，共 {minutes} 分钟",
                meta={"minutes": minutes, "task_id": task_id, "phase": "focus"},
            )
        except Exception:
            logger.exception("番茄钟日志写入失败")

    def _pomodoro_today_stats(self) -> tuple:
        """今日 (番茄数, 专注分钟)——建菜单时现算，不引常驻缓存。"""
        try:
            from datetime import datetime as _dt

            from zentray.services.activity_log import query_events

            today = _dt.now().strftime("%Y-%m-%d")
            count = minutes = 0
            for ev in query_events(category="pomodoro", days=1, limit=500):
                if (ev.get("time") or "")[:10] != today:
                    continue
                if ev.get("action") != "pomodoro_done":
                    continue
                count += 1
                minutes += int((ev.get("meta") or {}).get("minutes") or 0)
            return count, minutes
        except Exception:
            return 0, 0

    def _on_pomodoro_end(self) -> None:
        """专注段结束（service 已流转到休息或 idle）。"""
        svc = self.pomodoro_service
        minutes = max(1, int(round(svc.last_focus_seconds / 60.0)))
        count_before, _m = self._pomodoro_today_stats()
        self._log_focus(minutes, svc.task_id, svc.task_title, aborted=False)
        self._carousel_started = True
        if svc.is_break:
            kind = "长休" if svc.phase == "long_break" else "短休"
            rem = svc.get_remaining()
            self.renderer.show_notification(
                "专注完成",
                f"🍅 第 {svc.completed_focus} 个番茄！{kind} {rem // 60} 分钟已开始",
            )
        else:
            self.renderer.show_notification("专注结束", "番茄钟已完成，休息一下吧！")
        goal = int(getattr(self._settings.pomodoro, "daily_goal_pomodoros", 0) or 0)
        if goal > 0 and count_before < goal <= count_before + 1:
            self.renderer.show_notification("今日目标达成 🎉", f"今天已完成 {goal} 个番茄！")
        self.update_display(update_menu=True)
        self.start_rotation()
        try:
            from zentray.plugins import triggers

            triggers.dispatch_event("pomodoro_end")
        except Exception:
            logger.exception("pomodoro_end 插件事件分发失败")

    def _on_break_end(self) -> None:
        """休息段结束（自然走完或被跳过）。"""
        if getattr(self._settings.pomodoro, "auto_start_focus", False):
            self.renderer.show_notification("休息结束", "新一段专注已开始 🍅")
        else:
            self.renderer.show_notification("休息结束", "准备开始下一个番茄吧！")
        self._carousel_started = True
        self.update_display(update_menu=True)
        self.start_rotation()
        try:
            from zentray.plugins import triggers

            triggers.dispatch_event("break_end")
        except Exception:
            logger.exception("break_end 插件事件分发失败")

    # ==========================================
    # 插件脚本生命周期（信号槽，主线程）
    # ==========================================

    def _on_ops_log(self, text: str) -> None:
        self._ops_active = True
        self._carousel_started = True
        self._ops_tray_text = (text or "")[:50]
        self.renderer.set_state("app_icon", self._ops_tray_text)
        self._last_icon = "app_icon"
        self._last_label = self._ops_tray_text

    def _on_ops_busy(self, busy: bool) -> None:
        if busy:
            self._ops_active = True
            self._carousel_started = True
        self._refresh_menu()

    def _on_ops_finished(self, plugin_id: str, success: bool, summary: str) -> None:
        self._ops_active = False
        self._ops_tray_text = ""
        self._carousel_started = True
        self.update_display(update_menu=True)
        self.start_rotation()

    def _on_ops_report(self, report: dict) -> None:
        """运行报告（run_report 信号，主线程）：通知 + activity log + 可选写回任务。"""
        plugin_id = report.get("id", "")
        ok = bool(report.get("ok"))
        summary = report.get("summary", "")
        name = report.get("name") or plugin_id
        status = "执行成功" if ok else f"执行失败: {summary}"
        self.renderer.show_notification(
            f"脚本: {name}",
            status[:120],
            on_click=self._make_report_opener(report.get("run_id", "")),
        )
        try:
            from zentray.services.activity_log import log_event

            log_event(
                "system",
                "plugin_run",
                title=name,
                detail=summary,
                meta={
                    "id": plugin_id,
                    "ok": ok,
                    "log": report.get("log", ""),
                    "trigger": report.get("trigger", ""),
                    "task_id": report.get("task_id", ""),
                },
            )
        except Exception:
            pass
        self._write_back_result(report, name)

    @staticmethod
    def _make_report_opener(run_id: str):
        """通知点击回调：复用报告端点逻辑（html 报告→浏览器，否则 md→阅读器）。"""
        if not run_id:
            return None

        def opener():
            try:
                from zentray.api.handlers import _plugin_run_open

                _plugin_run_open({"run_id": run_id})
            except Exception:
                logger.exception("打开运行报告失败: %s", run_id)

        return opener

    def _write_back_result(self, report: dict, plugin_name: str) -> None:
        """manifest write_back 开启且有任务上下文时，把 RESULT 文本写回任务。"""
        result_text = (report.get("result_text") or "").strip()
        task_id = report.get("task_id") or ""
        if not result_text or not task_id:
            return
        try:
            plug = self.plugin_loader.get(report.get("id", ""))
            if plug is None or not plug.manifest.write_back:
                return

            from datetime import datetime as _dt

            stamp = _dt.now().strftime("%H:%M")
            line = f"\n[插件 {plugin_name} {stamp}] {result_text}"
            task = self.task_service.find_task(task_id)
            if task is not None:
                self.task_service.task_repo.mutate_all(
                    lambda tasks: self._append_task_details(tasks, task_id, line)
                )
            else:
                # 任务已归档（task_done 触发场景）：追加到当日归档日志
                from zentray.config import ARCHIVE_DIR
                from zentray.core.file_io import append_text_line

                archive_file = (
                    ARCHIVE_DIR / f"{_dt.now().strftime('%Y-%m-%d')}.log"
                )
                ts = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
                append_text_line(
                    archive_file, f"[{ts}] [插件: {plugin_name}] {result_text}\n"
                )
        except Exception:
            logger.exception("插件结果写回失败")

    @staticmethod
    def _append_task_details(tasks, task_id: str, line: str) -> bool:
        for t in tasks:
            if t.id == task_id:
                t.details = (t.details or "") + line
                return True
        return False

    def _on_about_to_quit(self) -> None:
        try:
            self.poll_timer.stop()
        except Exception:
            pass
        try:
            self.renderer.shutdown()
        except Exception:
            pass
