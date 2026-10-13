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


def test_console_close_channel_present():
    """关窗主通道走 console 拦截：页面失焦时 Chromium 会无限期挂起
    zentray://close 导航（插件报告通知气泡夺焦后点 X 假死，实测 91s
    不投递），console 消息不经导航管线、不受焦点影响。"""
    assert "def javaScriptConsoleMessage" in _SRC
    assert '"zentray:close:"' in _SRC
    assert "__zentrayCloseAck__" in _SRC, "宿主须回写 ACK，前端据此跳过导航兜底"
    assert "if self.result_payload is not None:" in _SRC, "console+导航双通道须防重入"


def test_size_channel_and_apply_host_height():
    """浮层高度自适应（quick-add AI 预览）：前端 console 上报 zentray:size:，
    宿主 apply_host_height 调窗并同步 _chrome_size（Resize 守卫按它判折半，
    若沿用开窗时的旧高度，预览展开/收起会被守卫拽回 96px）。"""
    assert '"zentray:size:"' in _SRC
    assert "def apply_host_height" in _SRC
    assert "apply_host_height(dlg, h)" in _SRC
    # 顺序：_chrome_size 先于 resize 更新（Resize 事件在 resize() 内同步投递）
    assert _SRC.index('setattr(dlg, "_chrome_size"') < _SRC.index("dlg.resize(dlg.width(), h)")
    # 前端契约：client.js 上报函数 + QuickAdd 挂 ResizeObserver 与 ESC 兜底
    root = Path(web_host.__file__).parents[2]
    client = (root / "web" / "src" / "api" / "client.js").read_text(encoding="utf-8")
    assert "zentray:size:" in client, "前端须以 console 上报内容高度"
    qa = (root / "web" / "src" / "views" / "QuickAdd.vue").read_text(encoding="utf-8")
    assert "reportHostHeight" in qa, "QuickAdd 须观察内容高度并上报"
    assert "onGlobalKeydown" in qa, "ESC 兜底：焦点不在输入框时窗口级监听走同一阶梯"


def test_apply_host_height_resizes_and_updates_chrome_size(qapp):
    """调高生效、超屏夹紧、±2px 抖动不动；_chrome_size 必须在 resize 前更新——
    Resize 事件在 resize() 内同步投递，守卫持旧目标会把收窗误判为合成器折半。"""
    from PySide6.QtWidgets import QDialog

    from zentray.ui.web_host import apply_host_height

    dlg = QDialog()
    dlg.resize(640, 96)
    try:
        apply_host_height(dlg, 300)
        assert dlg.height() == 300
        assert getattr(dlg, "_chrome_size", None) == (640, 300)

        # 先更 _chrome_size 后 resize：目标必须与新高度一致（顺序回归断言）
        apply_host_height(dlg, 120)
        assert dlg.height() == 120
        assert getattr(dlg, "_chrome_size", None) == (640, 120)

        # 过大请求夹到 0.92 可用高度以内
        apply_host_height(dlg, 1_000_000)
        screen = qapp.primaryScreen()
        assert dlg.height() <= int(screen.availableGeometry().height() * 0.92) + 1

        # ±2px 内不动（防抖）
        before = dlg.height()
        apply_host_height(dlg, before + 1)
        assert dlg.height() == before
    finally:
        dlg.deleteLater()


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
    """关窗（cancelled/accept 一律）必须保活（destroy 原生窗口但保留面板），
    再唤起——即使路由不同——复用保活面板（重导航、重新进入模态循环、不新建）；
    透明浮层（quick-add 形态）单独占用 overlay 槽，与 normal 槽互不挤占。
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
            self._vue_transparent = bool(kw.get("transparent"))
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
        assert web_host._PARKED_VUE_DIALOGS.get("normal") is created[0], (
            "cancelled 关窗后面板应进 normal 保活槽"
        )

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
        assert calls == ["destroy"], "复用会话结束应再次保活（destroy 丢句柄留页面）"
        assert web_host._PARKED_VUE_DIALOGS.get("normal") is created[0], (
            "accept 结束同样保活——这是弹窗延迟修复的核心契约"
        )

        # 再唤起仍复用同一面板（跨会话复用，而非只保活一轮）
        QTimer.singleShot(80, close_cancelled)
        web_host.open_vue_route("/tasks")
        assert len(created) == 1, "第三次唤起仍应复用，不应新建"

        # 透明浮层（quick-add）：overlay 槽独立，不与 normal 槽互抢
        def close_overlay():
            d = created[1]
            d.result_payload = {"cancelled": True}
            d.reject()

        QTimer.singleShot(80, close_overlay)
        web_host.open_vue_route(
            "/quick-add", frameless=True, stay_on_top=True, transparent=True
        )
        assert len(created) == 2, "overlay 槽为空时应新建透明浮层面板"
        assert web_host._PARKED_VUE_DIALOGS.get("overlay") is created[1], (
            "透明浮层关闭后应进 overlay 保活槽"
        )
        assert web_host._PARKED_VUE_DIALOGS.get("normal") is created[0], (
            "overlay 新建/保活不应挤占 normal 槽"
        )

        # overlay 复现：复用的是 overlay 槽面板，而非 normal 槽
        QTimer.singleShot(80, close_overlay)
        web_host.open_vue_route(
            "/quick-add", frameless=True, stay_on_top=True, transparent=True
        )
        assert len(created) == 2, "透明浮层再唤起应复用 overlay 槽，不应新建"
    finally:
        web_host.VueDialog = orig
        web_host._ACTIVE_VUE_DIALOGS.clear()
        web_host._PARKED_VUE_DIALOGS.clear()
        for d in created:
            d.deleteLater()
