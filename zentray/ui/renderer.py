# zentray/ui/renderer.py
"""
托盘渲染器 —— 封装底层托盘实现的 UI 渲染操作。

将原 TrayManager 中直接调用 backend 的逻辑集中管理，
使 TrayController 通过 Renderer 间接操作托盘显示。
"""
from zentray.ui.tray import TrayImplementation


class TrayRenderer:
    """托盘 UI 渲染器"""

    def __init__(self, backend: TrayImplementation):
        self.backend = backend

    def set_text(self, text: str) -> None:
        """更新状态栏显示文本"""
        self.backend.set_label(text)

    def set_icon(self, name: str) -> None:
        """更新托盘图标"""
        self.backend.set_icon(name)

    def set_state(self, icon: str, text: str) -> None:
        """原子更新图标 + 标题（避免 AppIndicator 换图标后丢文字）。"""
        if hasattr(self.backend, "set_state"):
            self.backend.set_state(icon, text)
        else:
            self.backend.set_icon(icon)
            self.backend.set_label(text)

    def update_menu(self, items: list) -> None:
        """更新右键菜单"""
        self.backend.update_menu(items)

    def show_notification(self, title: str, msg: str, on_click=None) -> None:
        """弹出系统通知；on_click 非空时点击通知触发（支持则常驻）"""
        self.backend.show_notification(title, msg, on_click)

    def shutdown(self) -> None:
        """关闭托盘"""
        self.backend.shutdown()
