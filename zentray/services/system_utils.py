# zentray/services/system_utils.py
"""
系统级工具：单例锁、空闲检测、全局快捷键监听。
"""
import sys
import logging

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtCore import QObject, Signal
from pynput import keyboard

logger = logging.getLogger(__name__)


SERVER_NAME = "ZenTray_SingleInstance"


class SingleInstanceGuard(QObject):
    """单例模式锁：基于 Qt 本地套接字实现跨平台防多开 + IPC 通信"""

    quit_requested = Signal()
    activate_requested = Signal()  # 二次点击桌面图标时唤醒已有实例

    def __init__(self, server_name: str = SERVER_NAME):
        super().__init__()
        self.server_name = server_name

        # 尝试连接已有实例 —— 若成功则通知其「激活」后安静退出
        socket = QLocalSocket()
        socket.connectToServer(self.server_name)
        if socket.waitForConnected(500):
            try:
                socket.write(b"activate")
                socket.waitForBytesWritten(500)
            except Exception:
                pass
            socket.close()
            logger.info("ZenTray 已在运行，已通知前台实例激活。")
            # 正常退出码 0，避免桌面显示「启动失败」
            sys.exit(0)

        # 创建本地服务端，占住单例锁 + 接收外部指令
        self._server = QLocalServer()
        # 清理残留 socket 文件（异常退出后）
        QLocalServer.removeServer(self.server_name)
        if not self._server.listen(self.server_name):
            # 再试一次
            QLocalServer.removeServer(self.server_name)
            if not self._server.listen(self.server_name):
                logger.error("SingleInstanceGuard 服务启动失败: %s", self._server.errorString())
                print("SingleInstanceGuard 服务启动失败，程序退出。", file=sys.stderr)
                sys.exit(1)

        self._server.newConnection.connect(self._on_new_connection)

    # ==========================================
    # 内部：处理外部连接（activate / quit）
    # ==========================================

    def _on_new_connection(self) -> None:
        client = self._server.nextPendingConnection()
        if client is None:
            return
        if client.waitForReadyRead(800):
            data = client.readAll().data().decode("utf-8", errors="replace").strip()
            if data == "quit":
                logger.info("收到退出指令，正在关闭...")
                self.quit_requested.emit()
            elif data == "activate" or data == "":
                # 空数据：兼容旧二次启动只 connect 不写内容
                logger.info("收到激活指令（二次点击图标）")
                self.activate_requested.emit()
        else:
            # 连接后无数据也视为激活（旧客户端）
            self.activate_requested.emit()
        client.close()

    # ==========================================
    # 静态工具：供安装器检测 & 通信
    # ==========================================

    @staticmethod
    def is_running(server_name: str = SERVER_NAME) -> bool:
        """检测是否已有 ZenTray 实例在运行（安装器使用）"""
        socket = QLocalSocket()
        socket.connectToServer(server_name)
        if socket.waitForConnected(500):
            socket.close()
            return True
        return False

    @staticmethod
    def send_quit(server_name: str = SERVER_NAME) -> bool:
        """向运行中的 ZenTray 发送退出指令，返回是否发送成功"""
        socket = QLocalSocket()
        socket.connectToServer(server_name)
        if not socket.waitForConnected(1000):
            return False
        socket.write(b"quit")
        if not socket.waitForBytesWritten(1000):
            socket.close()
            return False
        socket.close()
        return True

    @staticmethod
    def send_activate(server_name: str = SERVER_NAME) -> bool:
        """通知已运行实例弹出提示"""
        socket = QLocalSocket()
        socket.connectToServer(server_name)
        if not socket.waitForConnected(1000):
            return False
        socket.write(b"activate")
        ok = socket.waitForBytesWritten(1000)
        socket.close()
        return ok


class HotkeyListener(QObject):
    """后台全局快捷键监听器，通过 Qt Signal 唤醒主线程"""

    triggered = Signal()

    def __init__(self, hotkey_str="<ctrl>+<alt>+t"):
        super().__init__()
        self.hotkey_str = hotkey_str
        self.listener = None

    def start(self) -> bool:
        """启动全局热键。失败时返回 False，不抛出到主流程。"""
        try:
            self.listener = keyboard.GlobalHotKeys({
                self.hotkey_str: self.on_activate,
            })
            self.listener.start()
            return True
        except Exception as e:
            logger.error("全局热键启动失败 (%s): %s", self.hotkey_str, e)
            self.listener = None
            return False

    def on_activate(self):
        self.triggered.emit()

    def stop(self):
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
            self.listener = None
