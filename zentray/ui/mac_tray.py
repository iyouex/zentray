# zentray/ui/mac_tray.py
"""
macOS 托盘后端：NSStatusItem（菜单栏 icon + 标题文字轮播）+ NSMenu + 系统通知。

按 docs/design/mac-interaction-design.md §12 实现。PyObjC 全部延迟导入：
非 darwin 平台 import 本模块零副作用（类对象在实例化路径上才创建）。

依赖（macOS 上安装）：pip install "zentray[mac]"
  pyobjc-framework-Cocoa / pyobjc-framework-UserNotifications
"""
from __future__ import annotations

import logging
import subprocess
import uuid

from zentray.resources import get_resource_path

from .tray import TrayImplementation, _short_label

logger = logging.getLogger(__name__)

# 菜单栏 extra 图标尺寸（pt；@2x 文件会以 2x 像素密度渲染保证 Retina 清晰）
_MENU_BAR_ICON_PT = 18.0

_MenuTarget = None
_NotifDelegate = None


def _ensure_classes():
    """延迟定义 NSObject 子类（AppKit 可用时才可定义）。"""
    global _MenuTarget, _NotifDelegate
    if _MenuTarget is not None:
        return
    from Foundation import NSObject

    class _MenuTargetImpl(NSObject):
        """NSMenuItem target：菜单点击 → Qt action_received（主线程）。"""

        tray = None
        actions = None  # tag -> action_id

        def onMenuAction_(self, sender):  # noqa: N802（objc selector 命名）
            aid = (self.actions or {}).get(int(sender.tag()))
            if aid and self.tray is not None:
                self.tray.action_received.emit(aid)

    class _NotifDelegateImpl(NSObject):
        """UNUserNotificationCenterDelegate：点击横幅执行回调 + 前台也显示。"""

        tray = None

        def userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_(  # noqa: N802,E501
            self, center, response, handler
        ):
            try:
                cb = self.tray._notif_callbacks.pop(response.identifier(), None)
                if cb is not None:
                    # 可能在后台线程到达：TrayImplementation 是主线程 QObject，
                    # AutoConnection 会排队回主线程执行
                    self.tray.notification_clicked.emit(cb)
            finally:
                handler()

        def userNotificationCenter_willPresentNotification_withCompletionHandler_(  # noqa: N802,E501
            self, center, notification, handler
        ):
            try:
                from UserNotifications import (
                    UNNotificationPresentationOptionBanner,
                    UNNotificationPresentationOptionList,
                    UNNotificationPresentationOptionSound,
                )

                opts = (
                    UNNotificationPresentationOptionBanner
                    | UNNotificationPresentationOptionList
                    | UNNotificationPresentationOptionSound
                )
            except Exception:  # macOS 10.x 无 Banner 选项，退回旧 Alert
                from UserNotifications import (
                    UNNotificationPresentationOptionAlert,
                )

                opts = UNNotificationPresentationOptionAlert
            handler(opts)

    _MenuTarget, _NotifDelegate = _MenuTargetImpl, _NotifDelegateImpl


def apply_mac_agent_behavior() -> bool:
    """无 Dock 图标 / 无主菜单栏（运行期等价 LSUIElement=1，agent 形态）。"""
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

        NSApplication.sharedApplication().setActivationPolicy_(
            NSApplicationActivationPolicyAccessory
        )
        return True
    except Exception:
        logger.exception("macOS accessory 模式设置失败（将有 Dock 图标，不影响功能）")
        return False


class MacStatusItemTray(TrayImplementation):
    """菜单栏 NSStatusItem：彩色 icon + 标题文字（系统 13pt），单击弹 NSMenu。"""

    def __init__(self):
        super().__init__()
        from AppKit import (
            NSMenu,
            NSStatusBar,
            NSVariableStatusItemLength,
        )

        _ensure_classes()

        from zentray.resources import ensure_app_icons

        icon_dir = ensure_app_icons()
        app_icon = icon_dir / "app_icon.png"
        if not app_icon.exists():
            app_icon = get_resource_path("resources/icons/app_icon.png")
        self._icon_dir = icon_dir
        self._app_icon_path = str(app_icon) if app_icon.exists() else ""

        self._notif_callbacks: dict = {}
        self._auth_state = None  # None=未请求 / pending / granted / denied
        self._notif_delegate = None

        self._menu_target = _MenuTarget.alloc().init()
        self._menu_target.tray = self
        self._menu_target.actions = {}
        self._tag_seq = 0

        self._menu = NSMenu.alloc().init()
        self._menu.setAutoenablesItems_(False)  # enabled 由 items 数据控制
        self._add_disabled_item(self._menu, "加载中…")

        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        btn = self._status_item.button()
        img = self._load_image("app_icon")
        if img is not None:
            btn.setImage_(img)
        btn.setToolTip_("ZenTray")
        self._status_item.setMenu_(self._menu)  # 单击即弹菜单（设计 §4）
        self._last_icon = "app_icon"
        self._last_label = ""
        logger.info("托盘后端: MacStatusItemTray（菜单栏 icon+标题轮播）")

    # ==========================================
    # 顶栏状态
    # ==========================================

    def set_icon(self, name: str):
        icon = (name or "app_icon").strip() or "app_icon"
        if icon == self._last_icon:
            return
        img = self._load_image(icon)
        if img is not None:
            self._status_item.button().setImage_(img)
            self._last_icon = icon

    def set_label(self, text: str):
        label = _short_label(text) if text else ""
        btn = self._status_item.button()
        btn.setTitle_(label)
        # tooltip 放全量状态（设计 §2：悬停 1s 显示完整标题，不截 48 字符）
        tip = (text or "").replace("\n", " ").strip() or "ZenTray"
        btn.setToolTip_(tip[:200])
        self._last_label = label
        self.label_changed.emit(text or "")

    def set_state(self, icon: str, text: str):
        self.set_icon(icon)
        self.set_label(text)

    def _load_image(self, name: str):
        from AppKit import NSImage
        from Foundation import NSMakeSize

        for cand in (
            self._icon_dir / f"{name}@2x.png",
            self._icon_dir / f"{name}.png",
        ):
            if cand.is_file():
                img = NSImage.alloc().initWithContentsOfFile_(str(cand))
                if img is not None:
                    img.setSize_(NSMakeSize(_MENU_BAR_ICON_PT, _MENU_BAR_ICON_PT))
                    return img
        if self._app_icon_path:
            img = NSImage.alloc().initWithContentsOfFile_(self._app_icon_path)
            if img is not None:
                img.setSize_(NSMakeSize(_MENU_BAR_ICON_PT, _MENU_BAR_ICON_PT))
        return img

    # ==========================================
    # 菜单（与 QtStandardTray 相同的 items 格式）
    # ==========================================

    @staticmethod
    def _add_disabled_item(ns_menu, label: str):
        from AppKit import NSMenuItem

        m = NSMenuItem.alloc().init()
        m.setTitle_(label)
        m.setEnabled_(False)
        ns_menu.addItem_(m)

    def update_menu(self, items: list):
        self._menu.removeAllItems()
        self._menu_target.actions = {}
        self._tag_seq = 0
        if not items:
            self._add_disabled_item(self._menu, "（空）")
            return
        self._build_ns_menu(self._menu, items)

    def _build_ns_menu(self, ns_menu, items):
        from AppKit import NSMenu, NSMenuItem

        for item in items:
            if item == "separator":
                ns_menu.addItem_(NSMenuItem.separatorItem())
            elif isinstance(item, dict) and "submenu" in item:
                parent = NSMenuItem.alloc().init()
                parent.setTitle_(str(item.get("label", "")))
                sub = NSMenu.alloc().init()
                sub.setAutoenablesItems_(False)
                self._build_ns_menu(sub, item["submenu"] or [])
                parent.setSubmenu_(sub)
                ns_menu.addItem_(parent)
            elif isinstance(item, dict):
                m = NSMenuItem.alloc().init()
                m.setTitle_(str(item.get("label", "")))
                m.setEnabled_(bool(item.get("enabled", True)))
                aid = str(item.get("id", "") or "")
                if aid:
                    self._tag_seq += 1
                    self._menu_target.actions[self._tag_seq] = aid
                    m.setTag_(self._tag_seq)
                    m.setTarget_(self._menu_target)
                    m.setAction_("onMenuAction:")
                ns_menu.addItem_(m)

    # ==========================================
    # 系统通知（UNUserNotificationCenter；拒绝授权则静默降级）
    # ==========================================

    def show_notification(self, title: str, msg: str, on_click=None):
        try:
            self._post_un(str(title), str(msg), on_click)
            return
        except Exception:
            logger.exception("UN 通知发送失败，回退 osascript")
        try:
            t = str(title).replace("\\", "\\\\").replace('"', '\\"')
            b = str(msg).replace("\\", "\\\\").replace('"', '\\"')
            subprocess.Popen(
                ["osascript", "-e", f'display notification "{b}" with title "{t}"'],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    def _post_un(self, title: str, msg: str, on_click):
        from UserNotifications import (
            UNAuthorizationOptionAlert,
            UNAuthorizationOptionBadge,
            UNAuthorizationOptionSound,
            UNMutableNotificationContent,
            UNNotificationRequest,
            UNUserNotificationCenter,
        )

        center = UNUserNotificationCenter.currentNotificationCenter()
        if self._notif_delegate is None:
            self._notif_delegate = _NotifDelegate.alloc().init()
            self._notif_delegate.tray = self
            center.setDelegate_(self._notif_delegate)

        content = UNMutableNotificationContent.alloc().init()
        content.setTitle_(title)
        content.setBody_(msg[:4000])
        content.setThreadIdentifier_("ZenTray")  # 通知中心按 ZenTray 分组堆叠
        ident = str(uuid.uuid4())
        req = UNNotificationRequest.requestWithIdentifier_content_trigger_(
            ident, content, None
        )
        if on_click:
            self._notif_callbacks[ident] = on_click

        if self._auth_state == "granted":
            center.addNotificationRequest_withCompletionHandler_(
                req, lambda err: None
            )
        elif self._auth_state is None:
            self._auth_state = "pending"
            opts = (
                UNAuthorizationOptionAlert
                | UNAuthorizationOptionSound
                | UNAuthorizationOptionBadge
            )
            center.requestAuthorizationWithOptions_completionHandler_(
                opts,
                lambda granted, error: self._on_auth(granted, center, req, ident),
            )
        else:
            # 拒绝/待定：静默丢弃（设计 §9：同 Linux notify-send 不可用行为）
            self._notif_callbacks.pop(ident, None)

    def _on_auth(self, granted, center, req, ident):
        self._auth_state = "granted" if granted else "denied"
        if granted:
            center.addNotificationRequest_withCompletionHandler_(
                req, lambda err: None
            )
        else:
            self._notif_callbacks.pop(ident, None)
            logger.warning("macOS 通知授权被拒绝（系统设置 → 通知 → ZenTray 可重开）")

    def shutdown(self):
        try:
            from AppKit import NSStatusBar

            if self._status_item is not None:
                NSStatusBar.systemStatusBar().removeStatusItem_(self._status_item)
                self._status_item = None
        except Exception:
            logger.exception("移除 NSStatusItem 失败")
        self._notif_callbacks.clear()
