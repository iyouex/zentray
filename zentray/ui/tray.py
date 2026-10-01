# zentray/ui/tray.py
"""
跨平台系统托盘。

Linux：优先 AppIndicator 桥接（顶栏显示文字轮播 + 菜单）。
不可用时回退 Qt 托盘（图标 + 菜单 + tooltip 轮播）。

产品约定：启动不弹主窗口；顶栏标签 = 当前活跃任务标题。
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import logging

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QCursor, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from zentray.resources import get_resource_path

logger = logging.getLogger(__name__)

# 顶栏文字不宜过长
_LABEL_MAX = 48


def _short_label(text: str) -> str:
    t = (text or "ZenTray").replace("\n", " ").strip()
    if len(t) <= _LABEL_MAX:
        return t
    return t[: _LABEL_MAX - 1] + "…"


class TrayImplementation(QObject):
    action_received = Signal(str)
    label_changed = Signal(str)
    # 通知点击回调（跨线程投递到主线程执行）
    notification_clicked = Signal(object)

    def __init__(self):
        super().__init__()
        self.notification_clicked.connect(lambda cb: cb() if cb else None)

    def set_label(self, text: str):
        pass

    def set_icon(self, name: str):
        pass

    def set_state(self, icon: str, text: str):
        """原子更新图标 + 标题（优先实现；默认可拆成两次调用）。"""
        self.set_icon(icon)
        self.set_label(text)

    def update_menu(self, items: list):
        pass

    def show_notification(self, title: str, msg: str, on_click=None):
        pass

    def shutdown(self):
        pass


class LinuxBridgeTray(TrayImplementation):
    """系统顶栏 AppIndicator：文字轮播 + 右键菜单。"""

    # 桥接写队列上限：托盘消息是尽力而为的 UI 状态，宁可丢弃也不堆积
    _QUEUE_MAX = 200

    def __init__(self):
        super().__init__()
        self.bridge_process = None
        self._last_label = ""
        self._last_icon = ""
        self._drop_warn_at = 0.0
        self._start_bridge()

    def _start_bridge(self):
        from zentray.resources import ensure_app_icons

        bridge_script = str(get_resource_path("zentray/ui/linux_tray_bridge.py"))
        icon_dir = str(ensure_app_icons())
        if not os.path.exists(bridge_script):
            raise FileNotFoundError(f"bridge script missing: {bridge_script}")

        self.bridge_process = subprocess.Popen(
            ["/usr/bin/python3", bridge_script, icon_dir],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        def read_bridge():
            for line in self.bridge_process.stdout:
                try:
                    data = json.loads(line)
                    if "action" in data:
                        self.action_received.emit(data["action"])
                    if "error" in data:
                        logger.error("tray bridge error: %s", data["error"])
                except Exception:
                    pass

        threading.Thread(target=read_bridge, daemon=True).start()

        def monitor_stderr():
            for line in self.bridge_process.stderr:
                s = line.rstrip()
                if s:
                    print(f"[ZenTray Bridge] {s}", file=sys.stderr)

        threading.Thread(target=monitor_stderr, daemon=True).start()

        # 写桥接走独立线程：桥接卡死/管道满时主线程绝不能跟着阻塞
        # （历史 bug：主线程直接 stdin.write，桥接 wedge 后 64KB 管道写满
        #   → 整个 UI 连同插件面板冻结，只能杀进程。修复=队列+丢弃。）
        self._out_queue: queue.Queue = queue.Queue(maxsize=self._QUEUE_MAX)
        self._writer_stop = threading.Event()

        def write_bridge():
            while not self._writer_stop.is_set():
                try:
                    data = self._out_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                if data is None:
                    break
                try:
                    self.bridge_process.stdin.write(json.dumps(data, ensure_ascii=False) + "\n")
                    self.bridge_process.stdin.flush()
                except Exception as e:
                    logger.warning("bridge send failed: %s", e)

        threading.Thread(target=write_bridge, daemon=True).start()

        # 启动占位：仅应用图标，无标题（等 controller 进入轮播后再 state）
        self._send({"type": "state", "icon": "app_icon", "text": ""})
        logger.info("AppIndicator 桥接已启动 (pid=%s)", self.bridge_process.pid)

    def _send(self, data):
        """入队发给桥接（非阻塞）。桥接异常时丢弃并限频告警，绝不阻塞调用线程。"""
        if self.bridge_process is None or self.bridge_process.poll() is not None:
            return
        try:
            self._out_queue.put_nowait(data)
        except queue.Full:
            now = time.monotonic()
            if now - self._drop_warn_at > 30:
                self._drop_warn_at = now
                logger.warning("桥接写队列已满（桥接无响应？），丢弃托盘消息")

    def set_icon(self, name: str):
        icon = (name or "app_icon").strip() or "app_icon"
        # 改图标后带上当前 label，防止文字被桌面清掉
        self._send({"type": "state", "icon": icon, "text": self._last_label})
        self._last_icon = icon

    def set_label(self, text: str):
        label = _short_label(text) if text else ""
        # 空字符串保留（启动仅图标阶段）
        if text and not label:
            label = _short_label(text)
        self._send({
            "type": "state",
            "icon": self._last_icon or "app_icon",
            "text": label,
        })
        self._last_label = label
        self.label_changed.emit(text or "")

    def set_state(self, icon: str, text: str):
        icon_name = (icon or "app_icon").strip() or "app_icon"
        # text 允许为空：启动阶段仅图标
        label = _short_label(text) if text else ""
        self._send({"type": "state", "icon": icon_name, "text": label})
        self._last_icon = icon_name
        self._last_label = label
        self.label_changed.emit(text or "")

    def update_menu(self, items: list):
        self._send({"type": "menu", "items": items})

    def show_notification(self, title: str, msg: str, on_click=None):
        # 带 on_click 且 notify-send 支持 --action（libnotify≥0.8）时：
        # --wait 常驻至用户操作，点击通知即触发回调（主线程执行）
        if on_click and _notify_send_supports_actions():
            def run_action():
                try:
                    out = subprocess.run(
                        [
                            "notify-send", "-a", "ZenTray",
                            "--action", "default=点击查看报告",
                            "--wait", str(title), str(msg),
                        ],
                        capture_output=True, text=True, timeout=300,
                    )
                    if out.stdout.strip():
                        self.notification_clicked.emit(on_click)
                except Exception:
                    pass

            threading.Thread(target=run_action, daemon=True).start()
            return
        # 优先 notify-send，避免临时 QSystemTrayIcon 造成“弹窗感”
        try:
            subprocess.Popen(
                ["notify-send", "-a", "ZenTray", "-t", "4000", str(title), str(msg)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        except Exception:
            pass
        try:
            tray = QSystemTrayIcon(QIcon.fromTheme("emblem-default"))
            if on_click:
                tray.messageClicked.connect(lambda: on_click() or tray.hide)
            tray.show()
            tray.showMessage(title, msg, QSystemTrayIcon.Information, 4000)
            QTimer.singleShot(4500, tray.hide)
        except Exception:
            pass

    def shutdown(self):
        self._send({"type": "quit"})
        self._writer_stop.set()
        if self.bridge_process and self.bridge_process.poll() is None:
            try:
                self.bridge_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    self.bridge_process.terminate()
                except Exception:
                    pass


class QtStandardTray(TrayImplementation):
    """Qt 托盘回退：图标 + 菜单；标题走 tooltip（无顶栏文字能力）。"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.tray = QSystemTrayIcon()

        from zentray.resources import ensure_app_icons

        icon_dir = ensure_app_icons()
        self._icon_dir = icon_dir
        app_icon = icon_dir / "app_icon.png"
        if not app_icon.exists():
            app_icon = get_resource_path("resources/icons/app_icon.png")
        self._app_icon_path = str(app_icon) if app_icon.exists() else ""
        if self._app_icon_path:
            self.tray.setIcon(QIcon(self._app_icon_path))
        else:
            self.tray.setIcon(QIcon.fromTheme("emblem-default"))

        self.menu = QMenu()
        self.menu.addAction("加载中…").setEnabled(False)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)
        self._pending_click = None
        self.tray.messageClicked.connect(self._on_message_clicked)
        self.tray.setToolTip("ZenTray")
        self.tray.show()
        self.actions = []
        self._last_icon = "app_icon"
        self._last_label = ""
        logger.info("使用 Qt 标准托盘（无顶栏文字，标题在 tooltip）")

    def _on_activated(self, reason):
        # 左键/中键也弹出菜单，方便发现入口；不打开任何主窗口
        if reason in (
            QSystemTrayIcon.Trigger,
            QSystemTrayIcon.DoubleClick,
            QSystemTrayIcon.MiddleClick,
            QSystemTrayIcon.Context,
        ):
            self.menu.popup(QCursor.pos())

    def _on_message_clicked(self):
        cb, self._pending_click = self._pending_click, None
        if cb:
            cb()

    def set_label(self, text: str):
        tip = _short_label(text) if text else "ZenTray"
        self.tray.setToolTip(tip)
        self._last_label = tip
        self.label_changed.emit(text or "")

    def set_icon(self, name: str):
        icon = (name or "app_icon").strip() or "app_icon"
        path = self._icon_dir / f"{icon}.png"
        if not path.exists() and self._app_icon_path:
            from pathlib import Path

            path = Path(self._app_icon_path)
        if path.exists():
            self.tray.setIcon(QIcon(str(path)))
            self._last_icon = icon

    def set_state(self, icon: str, text: str):
        self.set_icon(icon)
        self.set_label(text)

    def update_menu(self, items: list):
        self.menu.clear()
        self.actions.clear()
        if not items:
            self.menu.addAction("（空）").setEnabled(False)
            return
        self._build_qt_menu(self.menu, items)
        self.tray.setContextMenu(self.menu)

    def _build_qt_menu(self, qt_menu, items):
        for item in items:
            if item == "separator":
                qt_menu.addSeparator()
            elif isinstance(item, dict) and "submenu" in item:
                submenu = QMenu(item.get("label", ""), qt_menu)
                self._build_qt_menu(submenu, item["submenu"])
                qt_menu.addMenu(submenu)
            elif isinstance(item, dict):
                action = QAction(item.get("label", ""), qt_menu)
                action.setEnabled(item.get("enabled", True))
                aid = item.get("id", "")
                action.triggered.connect(
                    lambda checked=False, a=aid: self.action_received.emit(a)
                )
                qt_menu.addAction(action)
                self.actions.append(action)

    def show_notification(self, title: str, msg: str, on_click=None):
        self._pending_click = on_click
        self.tray.showMessage(title, msg, QSystemTrayIcon.Information, 4000)

    def shutdown(self):
        self.tray.hide()


_notify_action_cache: bool | None = None


def _notify_send_supports_actions() -> bool:
    """notify-send 是否支持 --action/--wait（libnotify ≥ 0.8），探测一次缓存。"""
    global _notify_action_cache
    if _notify_action_cache is None:
        try:
            res = subprocess.run(
                ["notify-send", "--help"], capture_output=True, text=True, timeout=3
            )
            _notify_action_cache = "--action" in (res.stdout + res.stderr)
        except Exception:
            _notify_action_cache = False
    return _notify_action_cache


def _appindicator_available() -> bool:
    probes = [
        "import gi; gi.require_version('AyatanaAppIndicator3','0.1')",
        "import gi; gi.require_version('AppIndicator3','0.1')",
    ]
    for code in probes:
        try:
            res = subprocess.run(
                ["/usr/bin/python3", "-c", code],
                capture_output=True,
                timeout=1,
            )
            if res.returncode == 0:
                return True
        except Exception:
            continue
    return False


def create_tray_backend(app) -> TrayImplementation:
    """
    Linux：优先顶栏 AppIndicator（文字轮播）。
    Windows：WindowsTray（左键速览 + QPainter 动态图标 + tooltip）。
    其它平台 / 无 Indicator：Qt 托盘。
    """
    if sys.platform == "win32":
        try:
            from zentray.ui.win_tray import WindowsTray

            backend = WindowsTray(app)
            logger.info("托盘后端: WindowsTray (左键速览 + 动态图标)")
            return backend
        except Exception:
            logger.exception("WindowsTray 启动失败，回退 Qt 托盘")
    if sys.platform.startswith("linux") and _appindicator_available():
        try:
            backend = LinuxBridgeTray()
            logger.info("托盘后端: LinuxBridgeTray (顶栏文字轮播)")
            return backend
        except Exception:
            logger.exception("AppIndicator 桥接启动失败，回退 Qt 托盘")
    return QtStandardTray(app)
