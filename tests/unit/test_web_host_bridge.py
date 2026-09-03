"""zentray:// 拖拽桥不得依赖 QWebEnginePage.view()。

回归背景：PySide6 6.11.1 已移除 QWebEnginePage.view()，acceptNavigationRequest
内 self.view() 每次抛 AttributeError，导致 Vue 弹窗无法拖拽（运行日志实证）。
_BridgePage 以 `_BridgePage(self.view)` 将 view 作为 QObject 父节点，应改用 self.parent()。
"""
from __future__ import annotations

from pathlib import Path

import zentray.ui.web_host as web_host

_SRC = Path(web_host.__file__).read_text(encoding="utf-8")


def test_bridge_page_never_calls_removed_view_api():
    assert "self.view()" not in _SRC, "PySide6 6.11 已移除 QWebEnginePage.view()，用 self.parent() 获取视图"


def test_bridge_page_constructed_with_view_as_parent():
    # _BridgePage(self.view) 必须保留：这是 self.parent() 能拿到视图的前提
    assert "_BridgePage(self.view)" in _SRC
