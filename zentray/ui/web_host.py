# zentray/ui/web_host.py
"""
用 QWebEngineView 承载 Vue + Arco 前端页面。

业务逻辑仍在 Python API / TaskService；此模块只负责开窗与关闭回传。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib.parse import urlencode

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout

logger = logging.getLogger(__name__)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEnginePage

    _HAS_WEBENGINE = True
except Exception:
    _HAS_WEBENGINE = False
    QWebEngineView = None  # type: ignore
    QWebEnginePage = object  # type: ignore


if _HAS_WEBENGINE:

    class _BridgePage(QWebEnginePage):
        """拦截 zentray:// 协议，用于前端关闭窗口及平滑拖拽移动。"""

        result_received = Signal(object)

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):  # noqa: N802
            s = url.toString()
            if s.startswith(("zentray://start_drag", "zentray://move")):
                logger.debug("bridge nav: %s", s[:80])
            if s.startswith("zentray://start_drag"):
                # PySide6 6.11 已移除 QWebEnginePage.view()；_BridgePage 以 view 为父构造
                view = self.parent()
                if view:
                    dlg = view.window()
                    if dlg:
                        from zentray.ui.dialog_utils import mark_dialog_moved

                        mark_dialog_moved(dlg)
                        handle = dlg.windowHandle()
                        if handle:
                            try:
                                handle.startSystemMove()
                            except Exception as e:
                                logger.debug("Failed startSystemMove from Vue: %s", e)
                return False
            if s.startswith("zentray://move"):
                from urllib.parse import parse_qs, urlparse

                q = parse_qs(urlparse(s).query)
                try:
                    dx = int((q.get("dx") or ["0"])[0])
                    dy = int((q.get("dy") or ["0"])[0])
                    view = self.parent()
                    if view:
                        dlg = view.window()
                        if dlg:
                            from zentray.ui.dialog_utils import mark_dialog_moved

                            mark_dialog_moved(dlg)
                            dlg.move(dlg.x() + dx, dlg.y() + dy)
                except Exception as e:
                    logger.debug("Failed to handle zentray://move: %s", e)
                return False
            if s.startswith("zentray://close"):
                payload = {}
                if "payload=" in s:
                    from urllib.parse import unquote, parse_qs, urlparse

                    q = parse_qs(urlparse(s).query)
                    raw = (q.get("payload") or [""])[0]
                    try:
                        payload = json.loads(unquote(raw))
                    except Exception:
                        payload = {"raw": raw}
                self.result_received.emit(payload)
                return False
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)

else:
    _BridgePage = None  # type: ignore


class VueDialog(QDialog):
    """
    打开 Vue 路由页面。

    前端关闭：location.href = 'zentray://close?payload=' + encodeURIComponent(JSON.stringify(obj))
    """

    def __init__(
        self,
        route: str = "/",
        *,
        query: Optional[dict] = None,
        title: str = "ZenTray",
        width: int = 860,
        height: int = 560,
        parent=None,
        frameless: bool = False,
        stay_on_top: bool = False,
        transparent: bool = False,
        modal: bool = True,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.result_payload: Any = None
        self.setModal(modal)

        from zentray.ui.dialog_utils import apply_dialog_chrome, schedule_center

        apply_dialog_chrome(
            self,
            width=width,
            height=height,
            stay_on_top=stay_on_top,
            tool=frameless,
        )
        if transparent:
            self.setAttribute(Qt.WA_TranslucentBackground, True)

        if not _HAS_WEBENGINE:
            layout = QVBoxLayout(self)
            from PySide6.QtWidgets import QLabel

            layout.addWidget(
                QLabel(
                    "当前环境未安装 Qt WebEngine，无法加载 Vue 界面。\n"
                    "请使用带 WebEngine 的 PySide6，或设置 ZENTRAY_UI=qt 回退原生对话框。"
                )
            )
            schedule_center(self)
            return

        from zentray.api.server import get_api_server, vue_ui_available

        if not vue_ui_available():
            layout = QVBoxLayout(self)
            from PySide6.QtWidgets import QLabel

            layout.addWidget(
                QLabel(
                    "未找到 Vue 构建产物 web/dist。\n"
                    "请在项目 web/ 目录执行：\n  npm install && npm run build\n"
                    "或设置 ZENTRAY_UI=qt 使用原生对话框。"
                )
            )
            schedule_center(self)
            return

        server = get_api_server()
        base = server.start()
        q = dict(query or {})
        q["api"] = base
        frag = route if route.startswith("/") else f"/{route}"
        url = f"{base}/#{frag}?{urlencode(q)}"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = QWebEngineView(self)
        if transparent:
            self.view.page().setBackgroundColor(Qt.transparent) if False else None
            try:
                from PySide6.QtGui import QColor

                self.view.page().setBackgroundColor(QColor(0, 0, 0, 0))
            except Exception:
                pass
        self.page = _BridgePage(self.view)
        self.page.result_received.connect(self._on_bridge_result)
        self.view.setPage(self.page)
        if transparent:
            try:
                from PySide6.QtGui import QColor

                self.page.setBackgroundColor(QColor(0, 0, 0, 0))
            except Exception:
                pass
        self.view.load(QUrl(url))
        layout.addWidget(self.view)
        schedule_center(self)
        logger.info("Vue dialog open: %s", url)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        from zentray.ui.dialog_utils import schedule_center

        schedule_center(self)

    def _on_bridge_result(self, payload: object) -> None:
        self.result_payload = payload
        if isinstance(payload, dict) and payload.get("cancelled"):
            self.reject()
        else:
            self.accept()


def open_vue_route(
    route: str,
    *,
    query: Optional[dict] = None,
    title: str = "ZenTray",
    width: int = 860,
    height: int = 560,
    parent=None,
    frameless: bool = False,
    stay_on_top: bool = False,
    transparent: bool = False,
    modal: bool = True,
) -> tuple[bool, Any]:
    """模态打开 Vue 页。返回 (accepted, payload)。"""
    dlg = VueDialog(
        route,
        query=query,
        title=title,
        width=width,
        height=height,
        parent=parent,
        frameless=frameless,
        stay_on_top=stay_on_top,
        transparent=transparent,
        modal=modal,
    )
    ok = bool(dlg.exec())
    # deleteLater：让 QDialog/QWebEnginePage 在主线程事件循环里确定性析构，
    # 避免 Python 引用环交给 cyclic GC 在任意线程（HTTP 处理线程）析构 Qt 对象
    dlg.deleteLater()
    return ok, dlg.result_payload


def use_vue_ui() -> bool:
    """是否使用 Vue 前端（有 dist 且 WebEngine 可用）。"""
    import os

    if os.environ.get("ZENTRAY_UI", "").lower() in ("qt", "native", "0", "false"):
        return False
    if not _HAS_WEBENGINE:
        return False
    from zentray.api.server import vue_ui_available

    return vue_ui_available()
