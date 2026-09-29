"""桥接写路径防冻结：_send 绝不能阻塞调用线程（Qt 主线程）。

修复前：_send 直接 stdin.write+flush——桥接 wedge 后 64KB 管道写满，
主线程永久阻塞，整个 UI（含插件面板）冻结，只能杀进程。
修复后：入有界队列由独立写线程消费，满则丢弃并限频告警。
"""
import queue
import time

from zentray.ui.tray import LinuxBridgeTray


class _FakeStdin:
    def write(self, s):
        time.sleep(30)  # 模拟写满/卡死的管道

    def flush(self):
        pass


class _FakeBridge:
    stdin = _FakeStdin()

    def poll(self):
        return None  # 桥接还“活着”（wedge 而非退出）


def _tray_with_full_queue() -> LinuxBridgeTray:
    """不走 __init__/_start_bridge（避免真起 GTK 桥接），只装配 _send 依赖。"""
    tray = LinuxBridgeTray.__new__(LinuxBridgeTray)
    tray.bridge_process = _FakeBridge()
    tray._drop_warn_at = 0.0
    tray._out_queue = queue.Queue(maxsize=2)
    tray._out_queue.put({"type": "state"})
    tray._out_queue.put({"type": "state"})
    return tray


def test_send_never_blocks_when_queue_full():
    tray = _tray_with_full_queue()
    t0 = time.monotonic()
    for _ in range(1000):
        tray._send({"type": "state", "text": "x" * 100})
    elapsed = time.monotonic() - t0
    assert elapsed < 1.0, f"队列满时 _send 阻塞了 {elapsed:.2f}s"


def test_send_noop_when_bridge_dead():
    tray = _tray_with_full_queue()
    tray.bridge_process = type("Dead", (), {"poll": staticmethod(lambda: 1)})()
    tray._send({"type": "state"})  # 不应抛异常
    assert tray._out_queue.qsize() == 2  # 也没入队
