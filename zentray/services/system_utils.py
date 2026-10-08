# zentray/services/system_utils.py
"""
系统级工具：单例锁、空闲检测、全局快捷键监听。
"""
import ctypes
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


# ==========================================
# macOS：Carbon RegisterEventHotKey（纯 ctypes，无需 PyObjC，也无需
# 辅助功能授权——NSEvent 全局监听才需要；Carbon 热键是事实标准）
# ==========================================

# HIToolbox ANSI 虚拟键码（命令/修饰键掩码：cmd=0x0100 shift=0x0200
# option=0x0800 control=0x1000；kEventClassKeyboard='keyb'，HotKeyPressed=5）
_MAC_MODS = {
    "ctrl": 0x1000, "control": 0x1000,
    "alt": 0x0800, "option": 0x0800, "opt": 0x0800,
    "cmd": 0x0100, "command": 0x0100, "super": 0x0100, "win": 0x0100,
    "meta": 0x0100, "windows": 0x0100,
    "shift": 0x0200,
}
_MAC_KEYCODES = {
    "space": 49, "return": 36, "enter": 36, "tab": 48,
    "backspace": 51, "esc": 53, "escape": 53,
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
    "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
    "y": 16, "t": 17, "o": 31, "u": 32, "i": 34, "p": 35, "l": 37,
    "j": 38, "k": 40, "n": 45, "m": 46,
    "1": 18, "2": 19, "3": 20, "4": 21, "5": 23, "6": 22, "7": 26,
    "8": 28, "9": 25, "0": 29,
}


def mac_hotkey_parse(hotkey_str: str):
    """pynput 风格热键串 → (Carbon 修饰键掩码, 键码)；无法映射返回 None。

    至少要求一个修饰键（裸键全局热键会吞正常打字，拒绝注册）。
    """
    if not hotkey_str:
        return None
    mods = 0
    key = None
    for part in hotkey_str.lower().split("+"):
        p = part.strip().strip("<>")
        if not p:
            continue
        if p in _MAC_MODS:
            mods |= _MAC_MODS[p]
        elif p in _MAC_KEYCODES and key is None:
            key = _MAC_KEYCODES[p]
        else:
            return None
    if key is None or mods == 0:
        return None
    return mods, key


class _MacCarbonHotkey:
    """Carbon 热键封装。事件经主线程 CFRunLoop 派发（与 Qt 事件循环同线程）。

    CFUNCTYPE 回调必须保活（实例属性），否则回调后段错误。
    """

    _HITOOLBOX = (
        "/System/Library/Frameworks/Carbon.framework/"
        "Frameworks/HIToolbox.framework/HIToolbox"
    )

    def __init__(self, hotkey_str: str, on_trigger):
        parsed = mac_hotkey_parse(hotkey_str)
        if parsed is None:
            raise ValueError(f"热键无法映射为 Carbon 键码: {hotkey_str}")
        self._mods, self._code = parsed
        self._on_trigger = on_trigger

        self._lib = ctypes.CDLL(self._HITOOLBOX)

        class _EventHotKeyID(ctypes.Structure):
            _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]

        class _EventTypeSpec(ctypes.Structure):
            _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]

        # restype + argtypes 都要设：无 argtypes 时 ctypes 把 Python int 按
        # C int（32 位）传参，GetApplicationEventTarget 返回的指针被截断，
        # InstallEventHandler 内部解引用野指针 → SIGSEGV（arm64 macOS 26 实测）
        self._lib.GetApplicationEventTarget.restype = ctypes.c_void_p
        self._lib.GetApplicationEventTarget.argtypes = []
        self._lib.InstallEventHandler.restype = ctypes.c_int
        self._lib.InstallEventHandler.argtypes = [
            ctypes.c_void_p,                   # inTarget
            ctypes.c_void_p,                   # inHandler (EventHandlerUPP)
            ctypes.c_uint,                     # inNumTypes
            ctypes.c_void_p,                   # inList (EventTypeSpec*)
            ctypes.c_void_p,                   # inUserData
            ctypes.POINTER(ctypes.c_void_p),   # outRef
        ]
        self._lib.RegisterEventHotKey.restype = ctypes.c_int
        self._lib.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32,                   # inHotKeyCode
            ctypes.c_uint32,                   # inHotKeyModifiers
            _EventHotKeyID,                    # inHotKeyID（结构体传值）
            ctypes.c_void_p,                   # inTarget
            ctypes.c_uint32,                   # inOptions
            ctypes.POINTER(ctypes.c_void_p),   # outRef
        ]
        self._lib.UnregisterEventHotKey.restype = ctypes.c_int
        self._lib.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]

        target = self._lib.GetApplicationEventTarget()

        # signature 'znty' + id 1；kEventClassKeyboard='keyb'(0x6B657962)，HotKeyPressed=5
        self._hk_id = _EventHotKeyID(0x7A6E7479, 1)
        self._spec = _EventTypeSpec(0x6B657962, 5)
        self._ref = ctypes.c_void_p()
        self._handler_ref = ctypes.c_void_p()
        self._handler = ctypes.CFUNCTYPE(
            ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )(self._on_hotkey)

        err = self._lib.InstallEventHandler(
            target, self._handler, 1, ctypes.byref(self._spec), None,
            ctypes.byref(self._handler_ref),
        )
        if err != 0:
            raise OSError(f"InstallEventHandler 失败: {err}")
        err = self._lib.RegisterEventHotKey(
            self._code, self._mods, self._hk_id, target, 0, ctypes.byref(self._ref)
        )
        if err != 0:
            raise OSError(f"RegisterEventHotKey 失败: {err}")

    def _on_hotkey(self, next_handler, event, user_data):
        try:
            self._on_trigger()
        except Exception:
            logger.exception("mac 热键回调异常")
        return 0  # noErr：事件已消费

    def stop(self):
        if self._ref:
            try:
                self._lib.UnregisterEventHotKey(self._ref)
            except Exception:
                pass
            self._ref = ctypes.c_void_p()


class HotkeyListener(QObject):
    """后台全局快捷键监听器，通过 Qt Signal 唤醒主线程"""

    triggered = Signal()

    def __init__(self, hotkey_str="<ctrl>+<alt>+t"):
        super().__init__()
        self.hotkey_str = hotkey_str
        self.listener = None
        self._carbon = None

    def start(self) -> bool:
        """启动全局热键。失败时返回 False，不抛出到主流程。"""
        if sys.platform == "darwin":
            try:
                self._carbon = _MacCarbonHotkey(self.hotkey_str, self.on_activate)
                logger.info("全局热键已注册（Carbon）: %s", self.hotkey_str)
                return True
            except Exception as e:
                logger.warning("Carbon 热键注册失败，回退 pynput: %s", e)
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
        if self._carbon is not None:
            try:
                self._carbon.stop()
            except Exception:
                pass
            self._carbon = None
        if self.listener:
            try:
                self.listener.stop()
            except Exception:
                pass
            self.listener = None
