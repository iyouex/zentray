"""zentray:// 拖拽桥不得依赖 QWebEnginePage.view()。

回归背景：PySide6 6.11.1 已移除 QWebEnginePage.view()，acceptNavigationRequest
内 self.view() 每次抛 AttributeError，导致 Vue 弹窗无法拖拽（运行日志实证）。
_BridgePage 以 `_BridgePage(self.view)` 将 view 作为 QObject 父节点，应改用 self.parent()。
"""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from pathlib import Path

import zentray.ui.web_host as web_host

_SRC = Path(web_host.__file__).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["zentray-test"])
    return app


def test_bridge_page_never_calls_removed_view_api():
    assert "self.view()" not in _SRC, "PySide6 6.11 已移除 QWebEnginePage.view()，用 self.parent() 获取视图"


def test_pick_bridge_deferred_via_single_shot():
    """pick- 导航必须在导航回调外弹对话框（QTimer.singleShot(0) 推迟），
    否则模态对话框在回调内重入 WebEngine。"""
    assert 's.startswith("zentray://pick-")' in _SRC
    assert "QTimer.singleShot(0, lambda: self._run_pick(kind, payload))" in _SRC
    assert "_run_pick" in _SRC
    assert "zentray:pick-result" in _SRC, "结果须以 CustomEvent 回填前端"


def test_bridge_page_constructed_with_view_as_parent():
    # _BridgePage(self.view) 必须保留：这是 self.parent() 能拿到视图的前提
    assert "_BridgePage(self.view)" in _SRC


def test_open_vue_route_single_active_policy():
    """开新 Vue 面板必须先 reject 旧的：被最小化遗忘的旧面板与新面板并存时，
    两者的混合 DPI 尺寸恢复会互相触发合成器 configure，形成无限减半拉锯。"""
    from pathlib import Path
    import zentray.ui.web_host as web_host

    src = Path(web_host.__file__).read_text(encoding="utf-8")
    assert "_ACTIVE_VUE_DIALOGS" in src
    assert "old.reject()" in src
    assert "_ACTIVE_VUE_DIALOGS.add(dlg)" in src


def test_open_vue_route_reuses_active_same_route_dialog(qapp):
    """同路由再次唤起必须复用存活面板（showNormal + raise），不得销毁重建：
    WebEngine 重新加载 SPA 实测约 2 秒白窗，是最小化后重新唤起迟钝的根因。"""
    import zentray.ui.web_host as web_host
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog

    created = []

    class StubDialog(QDialog):
        def __init__(self, route, **kw):
            super().__init__()
            self.result_payload = None
            created.append(self)

    orig = web_host.VueDialog
    web_host.VueDialog = StubDialog
    reinvoke_results = []
    try:
        # 首个面板的模态循环内：模拟用户再次点击托盘菜单同一路由
        QTimer.singleShot(
            50,
            lambda: reinvoke_results.append(web_host.open_vue_route("/settings")),
        )
        QTimer.singleShot(120, lambda: created[0].accept())
        ok, _ = web_host.open_vue_route("/settings")
        assert ok
    finally:
        web_host.VueDialog = orig
        web_host._ACTIVE_VUE_DIALOGS.clear()
        for d in created:
            d.deleteLater()

    assert len(created) == 1, "同路由再次唤起不应新建对话框（应复用）"
    assert reinvoke_results == [(True, None)], "复用路径应立即返回成功"


def test_open_vue_route_remap_restores_minimized_dialog(qapp):
    """Wayland 无客户端反最小化协议，且 hide() 后 Qt 复用同一 xdg_toplevel，
    mutter 的最小化记忆仍导致防抢焦点延迟与折半 configure。复用最小化面板时
    必须走 destroy→showNormal 重映射（全新 toplevel，widget/页面保留）。"""
    import zentray.ui.web_host as web_host
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog

    created = []
    calls = []

    class StubMinimizedDialog(QDialog):
        def __init__(self, route, **kw):
            super().__init__()
            self.result_payload = None
            created.append(self)

        def isMinimized(self):  # noqa: N802
            return True

        def destroy(self, destroyWindow=True, destroySubWindows=True):  # noqa: N803
            calls.append("destroy")

        def showNormal(self):  # noqa: N802
            calls.append("showNormal")

    orig = web_host.VueDialog
    web_host.VueDialog = StubMinimizedDialog
    reinvoke_results = []
    try:
        QTimer.singleShot(
            50,
            lambda: reinvoke_results.append(web_host.open_vue_route("/settings")),
        )
        QTimer.singleShot(120, lambda: created[0].accept())
        ok, _ = web_host.open_vue_route("/settings")
        assert ok
    finally:
        web_host.VueDialog = orig
        web_host._ACTIVE_VUE_DIALOGS.clear()
        for d in created:
            d.deleteLater()

    assert len(created) == 1, "最小化面板再唤起不应新建对话框（应重映射复用）"
    assert reinvoke_results == [(True, None)], "重映射路径应立即返回成功"
    assert calls == ["destroy", "showNormal"], (
        f"必须先 destroy 丢弃旧 xdg_toplevel 再 showNormal 重映射，实际调用序列: {calls}"
    )


def test_open_vue_route_parks_cancelled_dialog_and_reuses(qapp):
    """cancelled 关窗必须保活（destroy 原生窗口但保留面板），再唤起——
    即使路由不同——复用保活面板（重导航、重新进入模态循环、不新建）；
    非 cancelled 结束才确定性析构。
    根因：关窗即销毁会让下次唤起走全新 SPA 冷加载（实测 ~530ms+渲染进程重建，
    用户感知 2 秒+），保活复用降至 ~190ms。"""
    import zentray.ui.web_host as web_host
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog

    created, calls = [], []

    class StubParkDialog(QDialog):
        def __init__(self, route, **kw):
            super().__init__()
            self.result_payload = None
            created.append(self)

        def destroy(self, destroyWindow=True, destroySubWindows=True):  # noqa: N803
            calls.append("destroy")

    orig = web_host.VueDialog
    web_host.VueDialog = StubParkDialog
    try:
        # 首次打开：模拟用户点「关闭」→ cancelled
        def close_cancelled():
            d = created[0]
            d.result_payload = {"cancelled": True}
            d.reject()

        QTimer.singleShot(80, close_cancelled)
        ok, payload = web_host.open_vue_route("/tasks")
        assert (ok, payload) == (False, {"cancelled": True})
        assert calls == ["destroy"], f"cancelled 关窗应 destroy 保活，实际: {calls}"
        assert web_host._PARKED_VUE_DIALOG is created[0], "cancelled 关窗后面板应保活"

        # 跨路由再唤起（保活的是 /tasks，请求 /settings）：仍复用，不新建
        calls.clear()

        def close_with_result():
            d = created[0]
            d.result_payload = {"action": "select", "id": "t1"}
            d.accept()

        QTimer.singleShot(80, close_with_result)
        ok2, payload2 = web_host.open_vue_route("/settings")
        assert (ok2, payload2) == (True, {"action": "select", "id": "t1"}), (
            "复用路径的模态循环结束后必须把本次 payload 如实返回给调用方"
        )
        assert len(created) == 1, "再唤起（含跨路由）应复用保活面板，不应新建"
        assert calls == [], "复用路径无需再 destroy（toplevel 已在关窗时丢弃）"
        assert web_host._PARKED_VUE_DIALOG is None, "非 cancelled 结束后不再保活"
    finally:
        web_host.VueDialog = orig
        web_host._ACTIVE_VUE_DIALOGS.clear()
        web_host._PARKED_VUE_DIALOG = None
        for d in created:
            d.deleteLater()
