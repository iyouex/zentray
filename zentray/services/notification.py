"""统一通知客户端：多渠道（应用弹窗 + WxPusher）。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from zentray.services.wxpusher import WxPusherService

logger = logging.getLogger(__name__)


class NotificationClient:
    """多渠道通知出口。"""

    def __init__(
        self,
        app_token: Optional[str] = None,
        uid: Optional[str] = None,
    ):
        # 兼容旧构造：单 WxPusher
        self._legacy_token = app_token
        self._legacy_uid = uid

    @classmethod
    def from_settings(cls) -> "NotificationClient":
        return cls()

    def is_configured(self) -> bool:
        from zentray.services.settings_manager import SettingsManager

        return SettingsManager().is_notification_configured()

    def send(
        self, title: str, content: str, channels: Optional[List[str]] = None
    ) -> dict:
        """向已启用且已配置的渠道发送。

        channels：渠道类型白名单（app_popup/wxpusher，可多选）；
        None/空 = 全部已启用渠道（默认行为）。
        """
        from zentray.services.settings_manager import SettingsManager

        sm = SettingsManager()
        n = sm.notification
        sel = set(channels) if channels else None
        results: Dict[str, Any] = {"channels": {}}
        any_ok = False

        # 应用弹窗：由调用方（托盘）监听；此处只标记
        if n.app_popup_enabled() and (sel is None or "app_popup" in sel):
            results["channels"]["app_popup"] = {
                "status": "ok",
                "message": "app_popup",
            }
            any_ok = True

        # WxPusher 多条
        wx_list = (
            n.wxpusher_channels() if (sel is None or "wxpusher" in sel) else []
        )
        if not wx_list and self._legacy_token and self._legacy_uid:
            wx_list = []  # 走 legacy 下方
        for ch in wx_list:
            wx = WxPusherService(
                app_token=ch.wxpusher_app_token, uid=ch.wxpusher_uid
            )
            if not wx.is_configured():
                results["channels"][ch.id or ch.name] = {
                    "status": "error",
                    "message": "未配置 Token/UID",
                }
                continue
            r = wx.send_message(content=content, summary=title)
            results["channels"][ch.id or ch.name] = r
            code = r.get("code")
            if code == 1000 or code == 0:
                any_ok = True

        # 兼容旧单字段
        if (sel is None or "wxpusher" in sel) and (
            self._legacy_token
            or (n.wxpusher_app_token and n.wxpusher_uid and not wx_list)
        ):
            wx = WxPusherService(
                app_token=self._legacy_token or n.wxpusher_app_token,
                uid=self._legacy_uid or n.wxpusher_uid,
            )
            if wx.is_configured():
                r = wx.send_message(content=content, summary=title)
                results["channels"]["legacy_wxpusher"] = r
                code = r.get("code")
                if code == 1000 or code == 0:
                    any_ok = True

        if any_ok:
            results["status"] = "ok"
            # 标记是否需要本地弹窗（含渠道筛选）
            results["app_popup"] = n.app_popup_enabled() and (
                sel is None or "app_popup" in sel
            )
            return results

        logger.warning("No notification channel succeeded: %s", results)
        results["status"] = "error"
        results["message"] = "没有可用的通知渠道（请检查设置）"
        results["app_popup"] = n.app_popup_enabled() and (
            sel is None or "app_popup" in sel
        )
        return results
