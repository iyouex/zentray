# zentray/ui/web_host.py
"""
用 QWebEngineView 承载 Vue + Arco 前端页面。

业务逻辑仍在 Python API / TaskService；此模块只负责开窗与关闭回传。
"""
from __future__ import annotations

import json
import logging
import weakref
from typing import Any, Optional
from urllib.parse import urlencode

from PySide6.QtCore import QObject, QUrl, Qt, Signal
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


# 当前存活的 Vue 面板（单活策略，见 open_vue_route）
_ACTIVE_VUE_DIALOGS: "weakref.WeakSet[VueDialog]" = weakref.WeakSet()
# 关窗保活的面板：cancelled 关闭时 destroy 原生窗口但保留页面，再唤起
# （任意路由，_respawn_page 会重导航）无需 SPA 冷加载（实测 530ms → ~190ms）。
# 至多保活一个（WebEngine 页面常驻内存可观），新的保活会逐出旧的。
# ponytail: 只保活最近一个；若交替页签切换卡顿明显，再考虑按 route 扩容
_PARKED_VUE_DIALOG: Optional["VueDialog"] = None


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
        logger.debug("bridge result: %s", payload)
        self.result_payload = payload
        if isinstance(payload, dict) and payload.get("cancelled"):
            self.reject()
        else:
            self.accept()


def _park_or_dispose(dlg: "VueDialog") -> None:
    """面板结束时：cancelled 关闭的保活复用，其余确定性析构。

    deleteLater 让 QDialog/QWebEnginePage 在主线程事件循环里确定性析构，
    避免 Python 引用环交给 cyclic GC 在任意线程（HTTP 处理线程）析构 Qt 对象。
    """
    global _PARKED_VUE_DIALOG
    dlg._modal_active = False
    _ACTIVE_VUE_DIALOGS.discard(dlg)
    if isinstance(dlg.result_payload, dict) and dlg.result_payload.get("cancelled"):
        # destroy 丢弃原生窗口句柄：零 Wayland 存在，不会与后续面板互相触发
        # 合成器 configure 拉锯；widget 与页面保留，供再唤起时重导航复用。
        dlg.destroy()
        if _PARKED_VUE_DIALOG is not None and _PARKED_VUE_DIALOG is not dlg:
            _PARKED_VUE_DIALOG.deleteLater()
        _PARKED_VUE_DIALOG = dlg
    else:
        dlg.deleteLater()


def _respawn_page(dlg: "VueDialog", route: str, query: dict) -> None:
    """保活复用时把 SPA 导回目标路由，并派发 zentray:reopen 触发视图重挂载。

    前端 App.vue 以递增 router-view 的 key 响应该事件，等价于重新挂载当前
    页面组件（onMounted 重新拉数据），避免保活面板展示陈旧数据。
    """
    page = getattr(dlg, "page", None)
    if page is None:
        return
    from zentray.api.server import get_api_server

    base = get_api_server().start()
    q = dict(query)
    q["api"] = base
    frag = route if route.startswith("/") else f"/{route}"
    page.runJavaScript(
        "location.hash=" + json.dumps(f"#{frag}?{urlencode(q)}") + ";"
        "window.dispatchEvent(new Event('zentray:reopen'));"
    )


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
    from zentray.ui.dialog_utils import run_modal_loop

    # 同路由复用：面板被最小化/失焦后再次唤起时直接恢复已有面板。
    # 销毁重建会让 WebEngine 重新加载整个 SPA，实测约 2 秒白窗延迟。
    for old in list(_ACTIVE_VUE_DIALOGS):
        if (
            getattr(old, "_modal_active", False)
            and getattr(old, "_vue_route", None) == route
            and getattr(old, "_vue_query", None) == (query or {})
        ):
            try:
                if old.isMinimized():
                    # Wayland 无客户端反最小化协议；且 hide() 只 unmap，Qt 会复用
                    # 同一个 xdg_toplevel，mutter 对该 toplevel 的最小化记忆仍在：
                    # 重新 map 仍受 1~2s 防抢焦点延迟，且重新关联时按旧记忆下发
                    # 折半 configure（920x600→460x300）触发守卫二次重建。
                    # destroy() 连原生窗口句柄一起丢弃（widget 与页面保留），
                    # showNormal 以全新 toplevel 映射，与冷启动开窗同路径：
                    # 实测 40~97ms 完成、无折半 configure、JS 状态存活。
                    old.destroy()
                    old.showNormal()
                elif not old.isVisible():
                    old.show()
                old.raise_()
                old.activateWindow()
            except RuntimeError:
                continue  # 包装已析构，走下面新建路径
            return True, old.result_payload
    # 单活策略：托盘菜单随时可开新面板；被最小化到任务栏的旧面板若与新面板并存，
    # 两者的混合 DPI 尺寸恢复会互相触发合成器 configure，形成无限减半拉锯（窗口狂闪）。
    for old in list(_ACTIVE_VUE_DIALOGS):
        try:
            old.reject()
        except RuntimeError:
            pass
    _ACTIVE_VUE_DIALOGS.clear()

    # 保活命中：cancelled 关过的面板直接复现（页面已加载，无冷启动）。
    # 不要求路由相同：_respawn_page 会把 SPA 重导航到目标路由并触发视图
    # 重挂载，标题/尺寸也按本次调用修正——否则“开着 action 弹窗→任务栏
    # 点击要 /tasks”这类路由变化仍要付整程 SPA 冷加载。
    global _PARKED_VUE_DIALOG
    parked, _PARKED_VUE_DIALOG = _PARKED_VUE_DIALOG, None
    if parked is not None:
        try:
            parked._vue_route = route
            parked._vue_query = query or {}
            parked._modal_active = True
            _ACTIVE_VUE_DIALOGS.add(parked)
            parked.setWindowTitle(title)
            parked.resize(width, height)
            _respawn_page(parked, route, query or {})
            # 重新进入模态循环：run_modal_loop 内 show() 以全新 toplevel
            # 映射；结束时 _park_or_dispose 继续接管保活/析构。
            ok = run_modal_loop(parked)
            return ok, parked.result_payload
        except RuntimeError:
            pass  # C++ 对象已析构，走新建路径

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
    dlg._vue_route = route
    dlg._vue_query = query or {}
    dlg._modal_active = True
    _ACTIVE_VUE_DIALOGS.add(dlg)
    dlg.finished.connect(lambda: _park_or_dispose(dlg))
    ok = run_modal_loop(dlg)
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
