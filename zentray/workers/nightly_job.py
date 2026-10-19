import datetime
import logging
import time

from PySide6.QtCore import QThread

logger = logging.getLogger(__name__)


class NightlyJobWorker(QThread):
    """
    调度：自动周期备份（每 N 天，纯文件 IO）。

    原每日计划/每日复盘调度已于 2026-10 迁移为插件 chaowen / musheng
    （周期参数经 设置-插件-参数预设 驱动，见 plugins/triggers.py）。
    """

    def __init__(self):
        super().__init__()
        self.is_running = True

    def run(self):
        from zentray.services.settings_manager import SettingsManager
        from zentray.workers import ai_schedule as sched

        state = sched.load_state()
        logger.info("自动备份 worker 循环启动 last_backup=%s", state.last_backup_date)

        while self.is_running:
            now = datetime.datetime.now()
            today_str = now.strftime("%Y-%m-%d")

            # 每次迭代重新读设置（保存设置后无需重启 worker）
            settings = SettingsManager()
            backup = settings.backup
            if sched.should_fire_backup(
                now,
                enabled=bool(backup.auto_enabled),
                last_date=state.last_backup_date,
                trigger_hour=int(backup.trigger_hour),
                interval_days=int(backup.interval_days),
            ):
                logger.info(
                    "触发自动备份 @%s (每 %d 天，保留 %d 份)",
                    now.strftime("%H:%M"),
                    int(backup.interval_days),
                    int(backup.keep),
                )
                self._run_backup()
                state.last_backup_date = today_str
                state.last_backup_at = now.isoformat(timespec="seconds")
                sched.save_state(state)

            for _ in range(60):
                if not self.is_running:
                    break
                time.sleep(1)

    def _run_backup(self):
        """自动备份失败只留日志，不打扰用户（下次到点重试）。"""
        try:
            from zentray.services.data_migration import run_auto_backup

            result = run_auto_backup()
            if result.ok:
                logger.info("自动备份完成: %s", result.path)
            else:
                logger.warning("自动备份失败: %s", result.message)
        except Exception as e:
            logger.exception("Auto backup error: %s", e)

    def stop(self):
        self.is_running = False
        self.wait()
