"""开机自启（Linux：~/.config/autostart/*.desktop；Windows：HKCU Run 注册表），
不依赖 installer 是否打入发行包。

API（is_enabled/set_enabled/status/resolve_launch_target）保持跨平台语义，
未来恢复其他平台时在此文件内按 sys.platform 加回对应实现即可。
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

APP_NAME = "ZenTray"
APP_DISPLAY_NAME = "ZenTray"
APP_DESCRIPTION = "个人效率工具 — 待办管理 + 番茄钟 + AI 复盘"

# Windows 自启：HKCU Run 键（免管理员；任务管理器 → 启动应用 可见可禁用）
_WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def resolve_launch_target() -> Tuple[str, str]:
    """
    返回 (exec_line, workdir)。
    exec_line 可直接写入 desktop Exec=。
    """
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        return str(exe), str(exe.parent)

    for candidate in (
        Path("/usr/bin/zentray"),
        Path("/opt/zentray/ZenTray/ZenTray"),   # deb onedir 布局
        Path.home() / ".local" / "bin" / "ZenTray" / "ZenTray",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve()), str(candidate.parent)

    project_root = Path(__file__).resolve().parents[2]
    run_sh = project_root / "run.sh"
    if run_sh.is_file() and sys.platform != "win32":
        return str(run_sh.resolve()), str(project_root)

    # 开发回退：python -m zentray.main
    py = Path(sys.executable).resolve()
    return f"{py} -m zentray.main", str(project_root)


def is_enabled(app_name: str = APP_NAME) -> bool:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0, winreg.KEY_READ
            ) as k:
                winreg.QueryValueEx(k, app_name)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            logger.exception("检查开机自启失败")
            return False
    try:
        return _desktop_path(app_name).is_file()
    except Exception:
        logger.exception("检查开机自启失败")
        return False


def set_enabled(enabled: bool, app_name: str = APP_NAME) -> Tuple[bool, str]:
    """开启或关闭自启。返回 (ok, message)。"""
    if enabled:
        return _enable(app_name)
    return _disable(app_name)


def _desktop_path(app_name: str) -> Path:
    return Path.home() / ".config" / "autostart" / f"{app_name}.desktop"


def _win_run_command() -> str:
    """Run 键 REG_SZ 命令行：解释器/可执行路径含空格时加引号。"""
    exec_line, _workdir = resolve_launch_target()
    parts = exec_line.split()
    if len(parts) == 1:
        return f'"{parts[0]}"' if " " in parts[0] else parts[0]
    # 开发态「py -m zentray.main」：引解释器，参数原样
    return f'"{parts[0]}" ' + " ".join(parts[1:])


def _enable(app_name: str) -> Tuple[bool, str]:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as k:
                winreg.SetValueEx(k, app_name, 0, winreg.REG_SZ, _win_run_command())
            return True, "已开启开机自启（注册表 HKCU Run）"
        except Exception as e:
            logger.exception("开启开机自启失败")
            return False, f"开启失败: {e}"
    exec_line, workdir = resolve_launch_target()
    try:
        desktop = _desktop_path(app_name)
        desktop.parent.mkdir(parents=True, exist_ok=True)
        # Exec 字段：单路径可直接写；带空格的命令原样写（desktop 规范允许）
        first = exec_line.split()[0]
        path_line = workdir if workdir else str(Path(first).parent)
        icon = "accessories-text-editor"
        for icon_candidate in (
            Path("/usr/share/icons/hicolor/256x256/apps/zentray.png"),
            Path(workdir) / "resources" / "icons" / "app_icon.png" if workdir else None,
        ):
            if icon_candidate and icon_candidate.is_file():
                icon = str(icon_candidate)
                break
        content = f"""[Desktop Entry]
Type=Application
Name={APP_DISPLAY_NAME}
Comment={APP_DESCRIPTION}
Exec={exec_line}
Path={path_line}
Icon={icon}
Terminal=false
Categories=Utility;Office;
StartupNotify=false
X-GNOME-Autostart-enabled=true
Hidden=false
"""
        desktop.write_text(content, encoding="utf-8")
        desktop.chmod(0o755)
        return True, f"已开启开机自启（{desktop}）"
    except Exception as e:
        logger.exception("开启开机自启失败")
        return False, f"开启失败: {e}"


def _disable(app_name: str) -> Tuple[bool, str]:
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _WIN_RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as k:
                winreg.DeleteValue(k, app_name)
            return True, "已关闭开机自启"
        except FileNotFoundError:
            return True, "已关闭开机自启"
        except Exception as e:
            logger.exception("关闭开机自启失败")
            return False, f"关闭失败: {e}"
    try:
        desktop = _desktop_path(app_name)
        if desktop.is_file():
            desktop.unlink()
        return True, "已关闭开机自启"
    except Exception as e:
        logger.exception("关闭开机自启失败")
        return False, f"关闭失败: {e}"


def status() -> dict:
    exec_line, workdir = resolve_launch_target()
    return {
        "enabled": is_enabled(),
        "launch_target": exec_line,
        "workdir": workdir,
        "platform": sys.platform,
    }
