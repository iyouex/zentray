"""插件定时触发 worker（daily / interval / cron）。

镜像 NightlyJobWorker 的「每轮重读设置 → 判定 → 落盘 → 60×1s 睡眠」结构。
事件触发（task_done / pomodoro_end / startup）不走本 worker，
见 zentray.plugins.triggers.dispatch_event。
"""
import logging
import time

from PySide6.QtCore import QThread

logger = logging.getLogger(__name__)


class PluginTriggerWorker(QThread):
    def __init__(self):
        super().__init__()
        self.is_running = True

    def run(self):
        from zentray.plugins import triggers

        logger.info("插件触发 worker 循环启动")
        while self.is_running:
            try:
                triggers.poll_timers()
            except Exception:
                logger.exception("插件定时轮询失败")
            for _ in range(60):
                if not self.is_running:
                    break
                time.sleep(1)
        logger.info("插件触发 worker 已停止")

    def stop(self):
        self.is_running = False
        self.wait()
