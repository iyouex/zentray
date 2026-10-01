import sys
import os

# 将项目根目录加入路径，兼容直接 `python zentray/main.py` 启动
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# 修复 Linux 下无法唤出 Fcitx5 输入法的底层 BUG
if sys.platform.startswith("linux"):
    os.environ["QT_IM_MODULE"] = "ibus"
    os.environ.setdefault("XMODIFIERS", "@im=fcitx")

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication
from zentray.dependencies import injector, init_tray_controller
from zentray.core.repository import TaskRepository, PeriodicTemplateRepository
from zentray.services.system_utils import SingleInstanceGuard, HotkeyListener
from zentray.services.task_service import TaskService
from zentray.ui.overlay import QuickAddOverlay
from zentray.ui.reminder_dialog import ReminderDialog, apply_reminder_action
from zentray.workers.watcher import WatcherWorker
from zentray.workers.nightly_job import NightlyJobWorker
from zentray.workers.reminder_job import ReminderWorker
from zentray.config import HOTKEY_QUICK_ADD, VERSION, validate_config, get_enabled_features
from zentray.logging_config import setup_logging
from zentray.resources import ensure_app_icons, get_resource_path
import logging

logger = logging.getLogger(__name__)


class AppRuntime(QObject):
    """运行时持有可热启停的 worker。

    worker 线程的信号必须连接到本类的 bound method：AutoConnection 会排队回主线程。
    连接 lambda / 普通函数时 PySide6 走 direct，弹窗会在 worker 线程上创建，
    导致输入事件错乱（下拉点击失效）甚至 QtWebEngine 线程断言崩溃。
    """

    def __init__(self):
        super().__init__()
        self.controller = None
        self.nightly = None
        self.reminder_worker = None
        self.watcher = None
        self.plugin_trigger_worker = None
        self.overlay = None
        self.hotkey = None
        # 聚合提醒窗状态：模态打开期间新到期排队，关窗后统一处理
        self.reminder_modal_open = False
        self.reminder_queue: list = []

    def on_plugin_authorize(self, plugin_id: str, name: str) -> None:
        """插件级一次性授权弹窗（triggers.authorize_requested → 主线程）。"""
        from PySide6.QtWidgets import QMessageBox

        from zentray.plugins import triggers

        ret = QMessageBox.question(
            None,
            "允许插件自动运行",
            f"插件「{name}」声明了自动触发器。\n"
            f"允许它在触发条件满足时自动运行吗？\n"
            f"（仅询问这一次；拒绝后可在插件页重新开启）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        triggers.authorize(plugin_id, ret == QMessageBox.StandardButton.Yes)

    def on_quick_add(self) -> None:
        from zentray.ui.vue_commands import try_vue_quick_add

        if try_vue_quick_add(self.controller):
            return
        self.overlay.show_center()

    def on_task_overdue(self, task) -> None:
        if self.controller:
            self.controller.renderer.show_notification(
                "⏰ 任务逾期",
                f"「{task.title}」已逾期，优先级已自动提升为 {task.priority.upper()}",
            )

    def on_reminder_due(self, batch: list) -> None:
        _on_reminder_due(self, batch)

    def shutdown(self) -> None:
        """退出前停掉所有 worker，避免 QThread 在运行中被析构导致 abort。"""
        for worker in (
            self.reminder_worker,
            self.watcher,
            self.nightly,
            self.plugin_trigger_worker,
        ):
            if worker is None:
                continue
            try:
                worker.stop()
            except Exception:
                logger.exception("停止 worker 失败")


def _start_plugin_trigger_worker_if_needed(runtime: AppRuntime) -> None:
    """插件总开关开启时启动定时触发 worker（事件触发不走 worker）。"""
    from zentray.plugins import triggers

    need = False
    try:
        from zentray.services.settings_manager import SettingsManager

        need = bool(SettingsManager().ops.enabled)
    except Exception:
        pass

    if need:
        if runtime.plugin_trigger_worker is None or not (
            runtime.plugin_trigger_worker.isRunning()
        ):
            from zentray.workers.plugin_trigger import PluginTriggerWorker

            runtime.plugin_trigger_worker = PluginTriggerWorker()
            runtime.plugin_trigger_worker.start()
            logger.info("插件触发 worker 已启动")
    else:
        if runtime.plugin_trigger_worker and runtime.plugin_trigger_worker.isRunning():
            runtime.plugin_trigger_worker.stop()
            runtime.plugin_trigger_worker = None
            logger.info("插件触发 worker 已停止")


def _start_nightly_if_needed(runtime: AppRuntime, task_repo: TaskRepository) -> None:
    """计划/复盘任一开启且已配置 API，或通知渠道可用时启动调度 worker。"""
    need = False
    try:
        from zentray.services.settings_manager import SettingsManager

        sm = SettingsManager()
        ai = sm.ai
        need = bool(
            (ai.plan.enabled or ai.review.enabled) and sm.is_ai_configured()
        ) or sm.is_notification_configured() or bool(sm.backup.auto_enabled)
    except Exception:
        features = get_enabled_features()
        need = features["notification"] or features["ai_coach"]

    if need:
        if runtime.nightly is None or not runtime.nightly.isRunning():
            runtime.nightly = NightlyJobWorker(task_repo)
            if runtime.controller:
                # 连 controller 绑定方法（QObject，排队回主线程）：
                # 通知可点击开报告 + 未查看报告进入顶栏轮播
                runtime.nightly.job_completed.connect(
                    runtime.controller.on_ai_job_completed
                )
            runtime.nightly.start()
            logger.info("AI 计划/复盘 worker 已启动")
    else:
        if runtime.nightly and runtime.nightly.isRunning():
            runtime.nightly.stop()
            runtime.nightly = None
            logger.info("AI 计划/复盘 worker 已停止")


def _on_reminder_due(runtime: AppRuntime, batch: list) -> None:
    """聚合提醒：一轮到期 batch=[(task, fire_key), ...] 弹一窗。

    Vue 路径逐卡动作由前端直调 POST /reminder-action 即时落库；
    窗口关闭后对未处理卡（last_fired_key 未写的）统一 dismiss。
    模态打开期间新到期排队（不顶窗——旧行为是后到 reject 前窗、先到被静默 dismiss）。
    """
    if runtime.reminder_modal_open:
        runtime.reminder_queue.extend(batch)
        return
    runtime.reminder_modal_open = True
    try:
        from zentray.ui.vue_commands import try_vue_reminders
        from zentray.ui.dialog_utils import run_modal_loop

        task_service = injector.get(TaskService)
        handled, _payload = try_vue_reminders(batch)
        if not handled:
            # Qt 回退：逐个顺序弹，本地应用动作
            for task, fire_key in batch:
                dlg = ReminderDialog(task)
                run_modal_loop(dlg)
                action = dlg.result_action
                snooze = getattr(dlg, "snooze_minutes", 10) or 10
                rem = apply_reminder_action(
                    task, action, fire_key, snooze_minutes=snooze
                )
                task_service.update_task_reminder(task.id, rem)
                if action == "snooze":
                    try:
                        from zentray.services.activity_log import log_event

                        log_event(
                            "task",
                            "delay",
                            task.title,
                            f"提醒延时 {snooze} 分钟",
                            meta={"id": task.id, "snooze_minutes": snooze},
                        )
                    except Exception:
                        pass
                if action == "done":
                    task_service.mark_done(task.id)
        else:
            # 未处理卡（本轮 fire_key 未写 last_fired_key）统一 dismiss；
            # 已完成/已忽略/已稍后的卡状态不被覆盖（幂等）
            for task, fire_key in batch:
                fresh = task_service.find_task(task.id)
                if not fresh or not fresh.reminder:
                    continue
                if fresh.reminder.last_fired_key == fire_key:
                    continue
                rem = apply_reminder_action(task, "dismiss", fire_key)
                task_service.update_task_reminder(task.id, rem)
        if runtime.controller:
            runtime.controller.update_display()
    finally:
        runtime.reminder_modal_open = False
        if runtime.reminder_worker:
            runtime.reminder_worker.clear_pending_batch(
                [t.id for t, _ in batch]
            )
        # 关窗后处理打开期间排队的新到期
        if runtime.reminder_queue:
            queued = runtime.reminder_queue
            runtime.reminder_queue = []
            _on_reminder_due(runtime, queued)


def main():
    setup_logging()
    warnings = validate_config()

    features = get_enabled_features()
    logger.info("ZenTray v%s 启动中...", VERSION)
    logger.info("核心功能: ✓ 已启用")
    logger.info(
        "通知服务: %s",
        "✓ 已启用" if features["notification"] else "✗ 未配置（设置 WXPUSHER 凭据以启用）",
    )
    logger.info(
        "AI 教练: %s",
        "✓ 已启用" if features["ai_coach"] else "✗ 未配置（设置 AI_API_KEY 以启用）",
    )

    for warning in warnings:
        logger.warning(warning)

    ensure_app_icons()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("ZenTray")
    app.setApplicationDisplayName("ZenTray")
    app.setDesktopFileName("zentray")

    # 应用主图标（任务栏 / 对话框）
    try:
        from PySide6.QtGui import QIcon

        icon_path = ensure_app_icons() / "app_icon.png"
        if not icon_path.exists():
            icon_path = get_resource_path("resources/icons/app_icon.png")
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))
    except Exception as e:
        logger.warning("应用图标加载失败: %s", e)

    # 应用主题（白天 / 黑夜 / 跟随系统）
    try:
        from zentray.ui.theme import apply_app_theme

        apply_app_theme()
    except Exception as e:
        logger.warning("主题加载失败: %s", e)

    # 仅首次无配置时显示向导；之后一律静默托盘启动（优先 Vue）
    try:
        from zentray.ui.setup_wizard import should_show_wizard, show_setup_wizard
        from zentray.ui.vue_commands import try_vue_setup_wizard
        from zentray.api.handlers import ApiContext, set_api_context
        from zentray.services.task_service import TaskService as _TS

        if should_show_wizard():
            # 向导可能早于 controller：先挂最小 API 上下文
            try:
                set_api_context(ApiContext(task_service=injector.get(_TS)))
                from zentray.api.server import get_api_server, vue_ui_available

                if vue_ui_available():
                    get_api_server().start()
            except Exception:
                pass
            if not try_vue_setup_wizard():
                show_setup_wizard()
            from zentray.services.settings_manager import SettingsManager

            SettingsManager.reload()
            apply_app_theme()
            features = get_enabled_features()
    except Exception as e:
        logger.warning("配置向导跳过: %s", e)

    _guard = SingleInstanceGuard()
    _guard.quit_requested.connect(app.quit)

    runtime = AppRuntime()
    # 初始化托盘控制器：顶栏图标 + 任务标题轮播（无主窗口）
    runtime.controller = init_tray_controller(app)

    # Vue 前端 API：复用 TaskService，不改变业务逻辑
    try:
        from zentray.api.handlers import ApiContext, set_api_context
        from zentray.api.server import get_api_server, vue_ui_available

        task_service_early = injector.get(TaskService)

        class _ApiUiRelay(QObject):
            """HTTP 线程回调 → 主线程中继。

            回调在 HTTP 处理线程直接调 controller 会跨线程启停 QTimer
            （journal: Timers cannot be started from another thread）。
            经信号 + QObject 绑定槽发射，AutoConnection 自动排队回主线程；
            槽内运行时取属性，后续 monkeypatch 的 apply_settings 也能命中。
            """

            changed_requested = Signal()
            apply_settings_requested = Signal()
            pomodoro_requested = Signal(str)  # task_id（空=无绑定）
            report_viewed = Signal(str)  # 报告 key（run:<id>/ai:<path>），移出顶栏轮播
            pomodoro_control_requested = Signal(str)  # stop|extend|skip_break（速览面板）

            def __init__(self, runtime_ref):
                super().__init__()
                self._runtime_ref = runtime_ref
                self.changed_requested.connect(self._on_changed)
                self.apply_settings_requested.connect(self._on_apply)
                self.pomodoro_requested.connect(self._on_pomodoro)
                self.report_viewed.connect(self._on_report_viewed)

            def _on_changed(self):
                if self._runtime_ref.controller:
                    self._runtime_ref.controller.reload_data()

            def _on_apply(self):
                if self._runtime_ref.controller:
                    self._runtime_ref.controller.apply_settings()

            def _on_pomodoro(self, task_id):
                controller = self._runtime_ref.controller
                if controller:
                    controller.start_pomodoro(task_id or None)

            def _on_report_viewed(self, key):
                controller = self._runtime_ref.controller
                if controller:
                    controller.mark_report_viewed(key)

            def _on_pomodoro_control(self, action):
                controller = self._runtime_ref.controller
                if not controller:
                    return
                svc = controller.pomodoro_service
                if action == "stop":
                    controller.stop_pomodoro()
                elif action == "skip_break":
                    try:
                        svc.skip_break()
                    except Exception:
                        logger.exception("跳过休息失败")
                    controller.update_display(update_menu=True)
                elif action == "extend":
                    try:
                        svc.extend()
                    except Exception:
                        logger.exception("延长专注失败")
                    controller.update_display(update_menu=True)

        _api_ui_relay = _ApiUiRelay(runtime)
        set_api_context(
            ApiContext(
                task_service=task_service_early,
                on_changed=_api_ui_relay.changed_requested.emit,
                apply_settings=_api_ui_relay.apply_settings_requested.emit,
                plugin_runtime=getattr(runtime.controller, "plugin_runtime", None),
                plugin_loader=getattr(runtime.controller, "plugin_loader", None),
                pomodoro_service=getattr(runtime.controller, "pomodoro_service", None),
                start_pomodoro=_api_ui_relay.pomodoro_requested.emit,
                mark_report_viewed=_api_ui_relay.report_viewed.emit,
                pomodoro_control=_api_ui_relay.pomodoro_control_requested.emit,
                report_rotation=getattr(runtime.controller, "report_rotation", None),
            )
        )
        if vue_ui_available():
            url = get_api_server().start()
            logger.info("Vue UI API 已启动: %s", url)
        else:
            logger.info("Vue dist 未构建，对话框将使用原生 Qt（可执行 web/ 下 npm run build）")
    except Exception:
        logger.exception("Vue API 初始化失败，将使用原生对话框")

    # 插件触发系统：依赖注入 + 授权弹窗信号（绑定方法，AutoConnection 回主线程）
    try:
        from zentray.plugins import triggers

        triggers.configure(
            loader=getattr(runtime.controller, "plugin_loader", None),
            runtime=getattr(runtime.controller, "plugin_runtime", None),
            pomodoro_service=getattr(runtime.controller, "pomodoro_service", None),
        )
        triggers.signals().authorize_requested.connect(runtime.on_plugin_authorize)
    except Exception:
        logger.exception("插件触发系统初始化失败")

    def _on_activate_existing():
        """再次点击桌面图标：唤醒顶栏显示并打开任务列表界面。"""
        try:
            if runtime.controller:
                runtime.controller.start_rotation()
                runtime.controller.update_display(update_menu=True)
                from zentray.ui.commands import TaskListCommand

                TaskListCommand().execute(runtime.controller)
                logger.info("二次点击：已唤醒前台并打开任务列表界面")
        except Exception:
            logger.exception("激活已有实例时出错")

    _guard.activate_requested.connect(_on_activate_existing)

    # 设置保存后刷新 nightly
    original_apply = runtime.controller.apply_settings

    def apply_settings_with_workers():
        original_apply()
        task_repo = injector.get(TaskRepository)
        _start_nightly_if_needed(runtime, task_repo)
        _start_plugin_trigger_worker_if_needed(runtime)

    runtime.controller.apply_settings = apply_settings_with_workers

    # 空闲预载 Vue 页面：首次弹窗命中保活槽，免约 2s 的 SPA 冷加载。
    # 5s 延迟避开启动关键路径；构造在主线程但加载在 WebEngine 渲染进程。
    try:
        from zentray.api.server import vue_ui_available
        from PySide6.QtCore import QTimer
        from zentray.ui.web_host import prewarm_vue_page

        if vue_ui_available():
            QTimer.singleShot(5000, prewarm_vue_page)
    except Exception:
        logger.exception("Vue 预载挂载失败")

    # 静默启动：仅托盘（启动占位 → 随后轮播）
    logger.info("静默启动完成：仅顶栏托盘 + 任务标题轮播")

    task_service = injector.get(TaskService)
    # 闪电添加：优先 Vue 浮层，否则 Qt Overlay
    runtime.overlay = QuickAddOverlay(task_service=task_service)
    runtime.overlay.task_added.connect(runtime.controller.reload_data)

    runtime.hotkey = HotkeyListener(HOTKEY_QUICK_ADD)
    runtime.hotkey.triggered.connect(runtime.on_quick_add)
    if not runtime.hotkey.start():
        logger.warning("全局热键不可用（权限/Wayland？），仍可通过任务列表新建任务")

    task_repo = injector.get(TaskRepository)
    template_repo = injector.get(PeriodicTemplateRepository)
    runtime.watcher = WatcherWorker(task_repo, template_repo)
    runtime.watcher.tasks_updated.connect(runtime.controller.reload_data)
    runtime.watcher.task_overdue.connect(runtime.on_task_overdue)
    runtime.watcher.start()

    _start_nightly_if_needed(runtime, task_repo)
    _start_plugin_trigger_worker_if_needed(runtime)

    # 启动事件（startup 触发器）：worker 与插件系统就绪后派发一次
    try:
        from zentray.plugins import triggers

        triggers.dispatch_event("startup")
    except Exception:
        logger.exception("startup 插件事件分发失败")

    runtime.reminder_worker = ReminderWorker(task_repo)
    runtime.reminder_worker.reminder_due.connect(runtime.on_reminder_due)
    runtime.reminder_worker.start()

    if warnings:
        for w in warnings:
            logger.warning("配置提示: %s", w)

    app.aboutToQuit.connect(runtime.shutdown)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
