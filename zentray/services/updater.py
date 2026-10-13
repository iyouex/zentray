"""应用内自更新：检查 GitHub Release → 下载平台安装包 → 平台分派安装并重启。

三平台策略（单实例锁 QLocalServer 随进程退出才释放，故一律「旧进程退出后再启动」）：
- Linux(deb): pkexec apt install（polkit 认证，root 安装不锁运行中进程）→ helper 等 pid 退出 → 重启
- Windows(zip onedir): 解压到 <exe目录>.new → update.bat 等旧 pid 退出 → 换目录 → 启动 → 清理
- macOS(.app zip): 解压暂存 → update.sh 等旧 pid 退出 → 顶替当前 .app → open 启动
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

import requests

from zentray.config import DATA_DIR, VERSION

logger = logging.getLogger(__name__)

RELEASES_API = "https://api.github.com/repos/iyouex/zentray/releases/latest"
# 下载 URL 白名单：仅接受本仓库 Release 资产地址（防任意 URL 下载）
DOWNLOAD_PREFIX = "https://github.com/iyouex/zentray/releases/download/"

UPDATES_DIR = DATA_DIR / "updates"


def parse_version(v: str) -> tuple:
    """'v0.7.6' → (0, 7, 6)；解析不出数字返回 ()（任何比较都判不新）。"""
    nums = re.findall(r"\d+", str(v or ""))
    return tuple(int(n) for n in nums[:3])


def is_newer(latest: str, current: str = VERSION) -> bool:
    return parse_version(latest) > parse_version(current)


def platform_suffix() -> str:
    """Release 资产文件名的平台后缀（与 CI 产物命名一致）。"""
    if sys.platform.startswith("linux"):
        return "_amd64.deb"
    if sys.platform == "win32":
        return "_windows_x64.zip"
    if sys.platform == "darwin":
        return "_macos_arm64.zip"
    raise RuntimeError(f"不支持自更新的平台: {sys.platform}")


def _proxies(proxy: str) -> dict | None:
    """空代理 = requests 默认（环境变量）；GUI 进程读不到系统代理时由设置填入。"""
    p = (proxy or "").strip()
    return {"http": p, "https": p} if p else None


# —— helper 脚本（纯字符串构造，便于测试断言） ————————————————


def linux_restart_script(pid: int, exe: str) -> str:
    return (
        "#!/bin/sh\n"
        f"while kill -0 {pid} 2>/dev/null; do sleep 0.5; done\n"
        f'exec "{exe}"\n'
    )


def windows_update_bat(pid: int, exe_dir: str, exe_path: str,
                       new_dir: str, old_bak: str) -> str:
    return (
        "@echo off\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul\r\n'
        "if not errorlevel 1 (\r\n"
        "  timeout /t 1 /nobreak >nul\r\n"
        "  goto wait\r\n"
        ")\r\n"
        f'move /y "{exe_dir}" "{old_bak}"\r\n'
        f'move /y "{new_dir}" "{exe_dir}"\r\n'
        f'start "" "{exe_path}"\r\n'
        "timeout /t 8 /nobreak >nul\r\n"
        f'rmdir /s /q "{old_bak}"\r\n'
        'del "%~f0"\r\n'
    )


def macos_update_sh(pid: int, app_path: str, staged_app: str) -> str:
    return (
        "#!/bin/sh\n"
        f"while kill -0 {pid} 2>/dev/null; do sleep 0.5; done\n"
        f'rm -rf "{app_path}"\n'
        f'mv "{staged_app}" "{app_path}"\n'
        f'open "{app_path}"\n'
        'rm -f "$0"\n'
    )


class UpdaterService:
    """检查/下载/安装的状态机（单例；下载在后台线程，其余同步）。"""

    _instance = None

    def __init__(self):
        self._lock = threading.Lock()
        self._state = "idle"  # idle | downloading | ready | installing | error
        self._progress = 0
        self._error = ""
        self._version = ""
        self._path = ""

    @classmethod
    def instance(cls) -> "UpdaterService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # —— 检查 ——

    def check(self, proxy: str = "") -> dict:
        """查 latest release，返回是否有更新与资产信息；失败抛 RuntimeError。"""
        try:
            resp = requests.get(RELEASES_API, timeout=10, proxies=_proxies(proxy))
            resp.raise_for_status()
            rel = resp.json()
        except Exception as e:
            raise RuntimeError(f"检查更新失败：{e}") from e
        tag = str(rel.get("tag_name") or "")
        version = tag.lstrip("v")
        want = f"zentray_{version}{platform_suffix()}"
        asset = next(
            (a for a in rel.get("assets", []) if a.get("name") == want), None
        )
        if is_newer(tag) and asset is None:
            raise RuntimeError(
                f"新版本 v{version} 的本平台安装包尚未上传（CI 构建中），请稍后再试"
            )
        return {
            "version": version,
            "has_update": is_newer(tag),
            "asset_url": (asset or {}).get("browser_download_url") or "",
            "asset_name": (asset or {}).get("name") or "",
            "asset_size": (asset or {}).get("size") or 0,
            "notes_url": rel.get("html_url") or "",
            "published_at": rel.get("published_at") or "",
            "body": (rel.get("body") or "")[:800],
        }

    # —— 下载 ——

    def start_download(self, url: str, version: str, proxy: str = "") -> None:
        if not url.startswith(DOWNLOAD_PREFIX):
            raise RuntimeError("非法下载地址（仅接受本仓库 Release 资产）")
        with self._lock:
            if self._state == "downloading":
                raise RuntimeError("已有下载进行中")
            self._state, self._progress, self._error = "downloading", 0, ""
            self._version, self._path = version, ""
        t = threading.Thread(
            target=self._download, args=(url, version, proxy), daemon=True
        )
        t.start()

    def _download(self, url: str, version: str, proxy: str) -> None:
        dest = UPDATES_DIR / f"zentray_{version}{platform_suffix()}"
        try:
            UPDATES_DIR.mkdir(parents=True, exist_ok=True)
            resp = requests.get(url, stream=True, timeout=60, proxies=_proxies(proxy))
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or 0)
            got = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
                    got += len(chunk)
                    if total:
                        self._progress = min(99, got * 100 // total)
            self._path, self._state, self._progress = str(dest), "ready", 100
        except Exception as e:
            self._state, self._error = "error", f"下载失败：{e}"
            logger.warning("更新包下载失败: %s", e)

    def status(self) -> dict:
        with self._lock:
            return {
                "state": self._state,
                "progress": self._progress,
                "error": self._error,
                "version": self._version,
                "path": self._path,
            }

    # —— 安装并重启 ——

    def install_and_restart(self) -> dict:
        """平台分派安装；成功后安排退出（helper 接管等待-替换/重启）。"""
        with self._lock:
            if self._state != "ready" or not self._path:
                raise RuntimeError("安装包尚未就绪，请先下载")
            self._state = "installing"
        path = Path(self._path)
        try:
            if sys.platform.startswith("linux"):
                self._install_linux(path)
            elif sys.platform == "win32":
                self._install_windows(path)
            elif sys.platform == "darwin":
                self._install_macos(path)
            else:
                raise RuntimeError(f"不支持自更新的平台: {sys.platform}")
        except Exception:
            with self._lock:
                self._state = "error"
            raise
        self._quit()
        return {"restarting": True}

    def _install_linux(self, deb: Path) -> None:
        r = subprocess.run(
            ["pkexec", "apt", "install", "-y", str(deb)],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            raise RuntimeError(
                "系统认证安装失败，可手动安装已下载的包："
                f"sudo apt install {deb}"
            )
        # 新版本已落盘（路径不变），等旧进程退出后重启
        self._spawn_helper(
            ["sh", "-c", linux_restart_script(os.getpid(), sys.executable)]
        )

    def _install_windows(self, zip_path: Path) -> None:
        exe_path = Path(sys.executable).resolve()
        exe_dir = exe_path.parent
        new_dir = exe_dir.with_name(exe_dir.name + ".new")
        old_bak = exe_dir.with_name(exe_dir.name + ".old")
        for d in (new_dir, old_bak):
            if d.exists():
                shutil.rmtree(d)
        stage = UPDATES_DIR / "_win_stage"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True)
        # shortcut: onedir zip 若含单一顶层目录，取其内容为 .new，避免多包一层
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(stage)
        inner = [p for p in stage.iterdir()]
        src = inner[0] if len(inner) == 1 and inner[0].is_dir() else stage
        shutil.move(str(src), str(new_dir))
        if stage.exists():
            shutil.rmtree(stage)
        bat = UPDATES_DIR / "update.bat"
        bat.write_text(
            windows_update_bat(os.getpid(), str(exe_dir), str(exe_path),
                               str(new_dir), str(old_bak)),
            encoding="utf-8",
        )
        # CREATE_NO_WINDOW：不闪控制台黑窗
        subprocess.Popen(
            ["cmd", "/c", str(bat)], cwd=str(UPDATES_DIR),
            creationflags=0x08000000,
        )

    def _install_macos(self, zip_path: Path) -> None:
        # sys.executable = …/ZenTray.app/Contents/MacOS/zentray
        app_path = Path(sys.executable).resolve().parents[2]
        stage = UPDATES_DIR / "_mac_stage"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(stage)
        staged_app = stage / app_path.name
        if not staged_app.exists():
            raise RuntimeError(f"更新包内未找到 {app_path.name}")
        sh_path = UPDATES_DIR / "update.sh"
        sh_path.write_text(
            macos_update_sh(os.getpid(), str(app_path), str(staged_app)),
            encoding="utf-8",
        )
        import stat

        sh_path.chmod(sh_path.stat().st_mode | stat.S_IXUSR)
        subprocess.Popen(["/bin/sh", str(sh_path)], start_new_session=True)

    @staticmethod
    def _spawn_helper(argv: list) -> None:
        subprocess.Popen(argv, start_new_session=True)

    @staticmethod
    def _quit() -> None:
        # 推迟到事件循环退出，避免在 API 处理栈内同步重入（同 zentray://close 范式）
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            QTimer.singleShot(0, app.quit)
