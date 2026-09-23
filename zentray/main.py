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

from PySide6.QtCore import QObject
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
        self.overlay = None
        self.hotkey = None

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

    def on_reminder_due(self, task, fire_key: str) -> None:
        _on_reminder_due(self, task, fire_key)

    def shutdown(self) -> None:
        """退出前停掉所有 worker，避免 QThread 在运行中被析构导致 abort。"""
        for worker in (self.reminder_worker, self.watcher, self.nightly):
            if worker is None:
                continue
            try:
                worker.stop()
            except Exception:
                logger.exception("停止 worker 失败")


def _start_nightly_if_needed(runtime: AppRuntime, task_repo: TaskRepository) -> None:
    """计划/复盘任一开启且已配置 API，或通知渠道可用时启动调度 worker。"""
    need = False
    try:
        from zentray.services.settings_manager import SettingsManager

        sm = SettingsManager()
        ai = sm.ai
        need = bool(
            (ai.plan.enabled or ai.review.enabled) and sm.is_ai_configured()
        ) or sm.is_notification_configured()
    except Exception:
        features = get_enabled_features()
        need = features["notification"] or features["ai_coach"]

    if need:
        if runtime.nightly is None or not runtime.nightly.isRunning():
            runtime.nightly = NightlyJobWorker(task_repo)
            if runtime.controller:
                runtime.nightly.job_completed.connect(
                    runtime.controller.renderer.show_notification
                )
            runtime.nightly.start()
            logger.info("AI 计划/复盘 worker 已启动")
    else:
        if runtime.nightly and runtime.nightly.isRunning():
            runtime.nightly.stop()
            runtime.nightly = None
            logger.info("AI 计划/复盘 worker 已停止")


def _on_reminder_due(runtime: AppRuntime, task, fire_key: str) -> None:
    try:
        from zentray.ui.vue_commands import try_vue_reminder
        from zentray.ui.vue_commands import try_vue_task_list
        from zentray.ui.web_host import use_vue_ui
        from zentray.ui.dialog_utils import run_modal_loop

        action = "dismiss"
        snooze_minutes = 10
        handled, payload = try_vue_reminder(task, fire_key)
        if handled and isinstance(payload, dict):
            action = payload.get("action") or "dismiss"
            try:
                snooze_minutes = int(payload.get("snooze_minutes") or 10)
            except (TypeError, ValueError):
                snooze_minutes = 10
        else:
            dlg = ReminderDialog(task)
            run_modal_loop(dlg)
            action = dlg.result_action
            snooze_minutes = getattr(dlg, "snooze_minutes", 10) or 10

        rem = apply_reminder_action(
            task,
            action,
            fire_key,
            snooze_minutes=snooze_minutes,
        )
        task_service = injector.get(TaskService)
        task_service.update_task_reminder(task.id, rem)

        if action == "snooze":
            try:
                from zentray.services.activity_log import log_event

                log_event(
                    "task",
                    "delay",
                    getattr(task, "title", "") or "",
                    f"提醒延时 {snooze_minutes} 分钟",
                    meta={"id": getattr(task, "id", None), "snooze_minutes": snooze_minutes},
                )
            except Exception:
                pass

        if action == "done":
            task_service.mark_done(task.id)
            if runtime.controller:
                runtime.controller.update_display()
        elif action == "update":
            fresh = task_service.find_task(task.id) or task
            if use_vue_ui() and runtime.controller:
                # 更新进度并入任务列表右栏：直达选中该任务
                try_vue_task_list(runtime.controller, select_id=fresh.id)
            else:
                from zentray.ui.dialogs import ProgressDialog

                progress = ProgressDialog(task=fresh)
                if run_modal_loop(progress):
                    percent, note = progress.get_data()
                    task_service.update_progress(task.id, percent, note)
            if runtime.controller:
                runtime.controller.update_display()
        elif runtime.controller:
            runtime.controller.update_display()
    finally:
        if runtime.reminder_worker:
            runtime.reminder_worker.clear_pending(task.id)


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

        def _on_api_changed():
            if runtime.controller:
                runtime.controller.reload_data()

        def _on_api_apply_settings():
            if runtime.controller:
                runtime.controller.apply_settings()

        set_api_context(
            ApiContext(
                task_service=task_service_early,
                on_changed=_on_api_changed,
                apply_settings=_on_api_apply_settings,
            )
        )
        if vue_ui_available():
            url = get_api_server().start()
            logger.info("Vue UI API 已启动: %s", url)
        else:
            logger.info("Vue dist 未构建，对话框将使用原生 Qt（可执行 web/ 下 npm run build）")
    except Exception:
        logger.exception("Vue API 初始化失败，将使用原生对话框")

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

    runtime.controller.apply_settings = apply_settings_with_workers

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
