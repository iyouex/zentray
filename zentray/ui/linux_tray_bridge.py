#!/usr/bin/env python3
"""AppIndicator 桥接进程：顶栏图标 + 文字标签（任务标题轮播）+ 右键菜单。

主程序通过 stdin 发 JSON 行控制：
  {"type":"label","text":"..."}
  {"type":"icon","icon":"app_icon"}
  {"type":"state","icon":"...","text":"..."}   # 原子更新：先图标后文字（避免丢 label）
  {"type":"menu","items":[...]}
  {"type":"quit"}

菜单点击通过 stdout 回报：
  {"action":"..."}
"""
import sys
import os
import json
import threading
import time

try:
    import gi

    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as AppIndicator
    except ValueError:
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3 as AppIndicator
    from gi.repository import Gtk, GLib, Gio
except Exception as e:
    print(json.dumps({"error": str(e)}), flush=True)
    sys.exit(1)


icon_dir = sys.argv[1] if len(sys.argv) > 1 else ""
_current_label = "ZenTray"
_current_icon = ""
# 固定 guide：给顶栏预留稳定宽度，避免 set_label 后被桌面隐藏
_LABEL_GUIDE = "W" * 28


def on_menu_item_clicked(item, action_id):
    print(json.dumps({"action": action_id}, ensure_ascii=False), flush=True)


def build_menu(menu_data):
    menu = Gtk.Menu()
    for item_data in menu_data:
        if item_data == "separator":
            menu.append(Gtk.SeparatorMenuItem())
            continue
        if not isinstance(item_data, dict):
            continue

        label_text = item_data.get("label", "")
        item = Gtk.MenuItem(label=label_text)

        if not item_data.get("enabled", True):
            item.set_sensitive(False)

        if "submenu" in item_data:
            submenu = build_menu(item_data["submenu"])
            item.set_submenu(submenu)
        else:
            item.connect("activate", on_menu_item_clicked, item_data.get("id", ""))

        menu.append(item)

    menu.show_all()
    return menu


def _resolve_icon(name: str):
    """返回 (icon_name, abs_path_or_None)。"""
    candidate = (name or "app_icon").strip() or "app_icon"
    path = None
    if icon_dir:
        path = os.path.join(icon_dir, f"{candidate}.png")
        if not os.path.exists(path):
            candidate = "app_icon"
            path = os.path.join(icon_dir, f"{candidate}.png")
        if not os.path.exists(path):
            path = None
    return candidate, path


def _apply_icon(name: str) -> None:
    """只改图标，不主动清 label（避免 set_icon('') 把文字抹掉）。"""
    global _current_icon
    candidate, path = _resolve_icon(name)
    if candidate == _current_icon and path:
        # 同名也再设一次，确保从 app_icon → pie 的重绘
        pass

    applied = False
    # 优先短名：new_with_path 已绑定 icon_dir，短名对 label 更友好
    try:
        indicator.set_icon(candidate)
        applied = True
    except Exception:
        pass
    if not applied and path:
        try:
            indicator.set_icon_full(path, candidate)
            applied = True
        except Exception:
            pass
    if applied:
        _current_icon = candidate


# 上次脉冲（清空再贴）的单调时钟时刻
_last_pulse = 0.0
# watcher 回归后延迟脉冲序列：解锁时 shell 重挂 item 与 libayatana 重注册的
# 先后不确定，单次脉冲可能落在 shell 挂载前进虚空（信号发出但无人接收，
# fork ⑮ 实测教训：只验证了信号发出，未验证 shell 挂载后收到）
_PULSE_REPEAT_MS = (500, 2000, 5000)
# 同值巩固间隔：轮播常连续重复同一标题，而 libayatana 同值 set_label 不发
# 信号 → shell 侧一旦丢失（锁屏销毁/扩展异常）同值重发永远 no-op。
# 超过该间隔的同值重贴改走脉冲路径，任何原因丢失最迟此时长内自愈。
_PULSE_MIN_INTERVAL = 60.0


def _pulse():
    """强制重贴当前标签：清空再贴，值必变化 → libayatana 必发信号。

    清空时保留 guide（宽度不塌陷，同帧贴回无可见闪烁）。
    """
    global _last_pulse
    _last_pulse = time.monotonic()
    text = _current_label
    guide = _LABEL_GUIDE if text else ""
    try:
        indicator.set_label("", guide)
        indicator.set_label(text, guide)
    except Exception:
        pass


def _apply_label(text: str) -> None:
    """设置顶栏文字。text 为空字符串时隐藏标签（启动占位）。

    同值且距上次脉冲不足 _PULSE_MIN_INTERVAL 时跳过（set_label 同值是
    no-op）；同值但已超间隔时走脉冲（清空再贴，值必变化必发信号）。
    """
    global _current_label
    if text is None:
        text = ""
    text = str(text).replace("\n", " ").strip()
    if len(text) > 48:
        text = text[:47] + "…"
    same = text == _current_label
    if same and _last_pulse and (time.monotonic() - _last_pulse) < _PULSE_MIN_INTERVAL:
        return
    _current_label = text

    if same:
        _pulse()
        return
    try:
        if text:
            # guide 固定宽度，防止桌面因 guide 变化把 label 挤没
            indicator.set_label(text, _LABEL_GUIDE)
        else:
            # 空标签：仅图标阶段
            indicator.set_label("", "")
    except Exception:
        try:
            indicator.set_label(text, "")
        except Exception:
            pass
    try:
        indicator.set_title(text or "ZenTray")
    except Exception:
        pass
    try:
        indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
    except Exception:
        pass


def _set_icon_safe(name: str):
    _apply_icon(name)
    # 关键图标后必须重贴 label，否则 Ayatana/Unity 常把文字丢掉
    _apply_label(_current_label)
    return False


def _set_label_safe(text: str):
    _apply_label(text if text is not None else _current_label)
    return False


def _set_state_safe(icon: str, text: str):
    """原子：先图标后文字，保证轮播时两者同时在。"""
    if icon:
        _apply_icon(icon)
    _apply_label(text if text is not None else "")
    return False


def _set_menu_safe(items):
    # Gtk 部件必须在 GTK 主线程创建：历史上在 read_stdin 线程里 build_menu，
    # 跨线程 Xlib 调用可死锁整个桥接 → 主进程管道写满 → UI 冻结。
    try:
        indicator.set_menu(build_menu(items or []))
    except Exception:
        pass
    # 换菜单后也巩固一次 label
    _apply_label(_current_label)
    return False


def _repin():
    """以当前值强制脉冲重贴（不受巩固窗口限制）。"""
    _pulse()
    return False


def _watcher_appeared(_conn, _name, _owner):
    # 多次延迟脉冲：覆盖 shell 重挂 item 与 libayatana 重注册的时序竞态
    for delay in _PULSE_REPEAT_MS:
        GLib.timeout_add(delay, _repin)


# 初始：应用图标 + 无标题（启动占位，等主进程发 state）
_id_name = "app_icon"
if icon_dir:
    indicator = AppIndicator.Indicator.new_with_path(
        "zentray",
        _id_name,
        AppIndicator.IndicatorCategory.APPLICATION_STATUS,
        icon_dir,
    )
else:
    indicator = AppIndicator.Indicator.new(
        "zentray",
        "emblem-default",
        AppIndicator.IndicatorCategory.APPLICATION_STATUS,
    )

indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
_apply_icon("app_icon")
_apply_label("")  # 启动仅图标

# 空菜单占位
_empty = Gtk.Menu()
_empty.append(Gtk.MenuItem(label="加载中…"))
_empty.show_all()
indicator.set_menu(_empty)

# 监听 StatusNotifierWatcher 回归（解锁/扩展重启）：强制脉冲重贴标签
Gio.bus_watch_name(
    Gio.BusType.SESSION,
    "org.kde.StatusNotifierWatcher",
    Gio.BusNameWatcherFlags.NONE,
    _watcher_appeared,
    None,
)


def read_stdin():
    for line in sys.stdin:
        try:
            data = json.loads(line)
            t = data.get("type")
            if t == "state":
                GLib.idle_add(
                    _set_state_safe,
                    data.get("icon") or "app_icon",
                    data.get("text") if "text" in data else "",
                )
            elif t == "label":
                GLib.idle_add(_set_label_safe, data.get("text") or "")
            elif t == "menu":
                GLib.idle_add(_set_menu_safe, data.get("items") or [])
            elif t == "icon":
                GLib.idle_add(_set_icon_safe, data.get("icon") or "app_icon")
            elif t == "quit":
                GLib.idle_add(Gtk.main_quit)
                break
        except Exception:
            pass


threading.Thread(target=read_stdin, daemon=True).start()
Gtk.main()
