"""后台更新检查：启动 4 秒后静默检查一次，此后每 6 小时。

对齐 taomni 的自动更新逻辑（useMainLayoutState 的定时 effect）：
- 静默检查不打扰：关闭了自动检查、或正有更新任务在进行（检查/下载/安装、包已就绪、
  待重启）时跳过；检查失败也不弹任何提示。
- 发现新版只发信号，由界面层决定怎么提示；每个版本只发一次（记在 updates/notified.json，
  跨重启有效）。用户手动检查到同一版本也算「已看过」，不再通知。
- 上次退出后的替换结果（Windows/macOS 的 helper 写入）在启动时取出并上报。
- 状态机的每次变化都转发为 changed 信号，界面据此刷新托盘菜单。

网络与磁盘清理都在守护线程；信号一律连到 QObject 的绑定方法，由 Qt 排队回 GUI 线程。
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from zentray.services import updater
from zentray.services.settings_manager import SettingsManager
from zentray.services.updater import HOLD_STATES, UpdaterService

logger = logging.getLogger(__name__)

INITIAL_DELAY_MS = 4000
INTERVAL_MS = 6 * 60 * 60 * 1000


class UpdateWatcher(QObject):
    """定时发起静默检查。信号可能在守护线程发出，接收方须是 QObject 的绑定方法。"""

    found = Signal(str)  # 发现新版本（每个版本只发一次）
    swap_failed = Signal(str)  # 上次退出后的替换失败，带原因
    changed = Signal()  # 更新状态机有变化

    def __init__(self, initial_delay_ms: int = INITIAL_DELAY_MS,
                 interval_ms: int = INTERVAL_MS, parent=None) -> None:
        super().__init__(parent)
        self._initial_delay_ms = initial_delay_ms
        self._timer = QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.timeout.connect(self.check_now)
        self._service = UpdaterService.instance()
        self._service.subscribe(self._on_service_state)

    def start(self) -> None:
        self._report_last_swap()
        QTimer.singleShot(self._initial_delay_ms, self.check_now)
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def check_now(self) -> None:
        """静默检查；关闭了自动检查或正有更新任务在进行时跳过。"""
        try:
            settings = SettingsManager().update
            if not settings.auto_check:
                return
            if self._service.status()["state"] in HOLD_STATES:
                return
            proxy = settings.proxy
        except Exception:
            logger.debug("更新检查的前置条件读取失败", exc_info=True)
            return
        threading.Thread(target=self._check, args=(proxy,), daemon=True).start()

    def _check(self, proxy: str) -> None:
        updater.cleanup_stale()  # 上次更新留下的半包/暂存目录：先清再查
        self._service.start_check(proxy, manual=False, on_done=self._checked)

    def _checked(self, result, error) -> None:
        if error or not result or not result.get("has_update"):
            return
        version = str(result.get("version") or "")
        try:
            if version in updater.notified_versions():
                return
            updater.mark_notified(version)
        except OSError:
            logger.debug("记录更新通知状态失败", exc_info=True)
        self.found.emit(version)

    def _on_service_state(self, snapshot: dict) -> None:
        # 用户手动检查到的新版本，他已经看到了：不再另发通知
        result = snapshot.get("result") or {}
        if (snapshot.get("state") == "available" and snapshot.get("manual")
                and result.get("has_update")):
            try:
                updater.mark_notified(str(result.get("version") or ""))
            except OSError:
                pass
        self.changed.emit()

    def _report_last_swap(self) -> None:
        try:
            result = updater.pop_swap_result()
        except OSError:
            return
        if result and not result.get("ok"):
            self.swap_failed.emit(str(result.get("reason") or "unknown"))
