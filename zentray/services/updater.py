"""应用内自更新：检查 GitHub Release → 下载平台安装包 → 校验 → 安装 → 确认后重启。

流程与状态（对齐 taomni updater 的逻辑）：
- 后端状态机是唯一真相源：idle | checking | uptodate | available | downloading |
  ready | installing | installed | error。
- 两道确认闸：用户点「下载并安装」才动；装完不自动重启，等用户点「立即重启」。
- 代次隔离：每次检查/下载一个代次（generation），取消或重开后旧线程的进度、完成、
  失败一律不回写，旧字节不安装。
- 安装失败：状态回到 ready 并带原因，已下载的包保留，可直接重试安装而不重新下载。
- 完整性：安装包落盘后依次校验大小 → SHA256 → 压缩包 CRC，任一不符即丢弃。

三平台策略（单实例锁 QLocalServer 随进程退出才释放，故一律「旧进程退出后再生效」）：
- Linux(deb): pkexec apt install（polkit 认证，root 安装不锁运行中进程）→ helper 等 pid 退出
- Windows(zip onedir): 解压到 <exe目录>.new → 旧进程退出后 bat 换目录（失败回滚）
- macOS(.app zip): 解压暂存 → 旧进程退出后 sh 顶替当前 .app（旧包先挪 .bak，失败回滚）
helper 只在存在重启标记时才拉起新进程；没有标记（用户选「稍后」）时只完成替换与清理，
下次启动即新版——应用不会在用户正常退出或关机时被擅自拉起。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

import requests

from zentray.config import DATA_DIR, VERSION

logger = logging.getLogger(__name__)

RELEASES_API = "https://api.github.com/repos/iyouex/zentray/releases/latest"
HTML_LATEST = "https://github.com/iyouex/zentray/releases/latest"
TAG_URL = "https://github.com/iyouex/zentray/releases/tag/"
# 下载 URL 白名单：仅接受本仓库 Release 资产地址（防任意 URL 下载）
DOWNLOAD_PREFIX = "https://github.com/iyouex/zentray/releases/download/"
# SHA256 清单：发布脚本在三端资产齐备后最后上传（scripts/compose_update_manifest.py）
MANIFEST_URL = "https://github.com/iyouex/zentray/releases/latest/download/latest.json"

UPDATES_DIR = DATA_DIR / "updates"

# 平台 → (latest.json 平台键, Release 资产文件名后缀)，与 CI/打包产物命名一致。
# scripts/compose_update_manifest.py 维护同一张表，单测断言两处一致。
PLATFORMS = {
    "linux": ("linux-amd64", "_amd64.deb"),
    "win32": ("windows-x64", "_windows_x64.zip"),
    "darwin": ("macos-arm64", "_macos_arm64.zip"),
}

# 这些状态下不重复发起检查/下载，静默检查也跳过
HOLD_STATES = ("checking", "downloading", "ready", "installing", "installed")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_PACKAGE_RE = re.compile(
    r"^zentray_(.+?)_(amd64\.deb|windows_x64\.zip|macos_arm64\.zip)$")
_MAX_DOWNLOAD_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 2.0  # 第 n 次失败后等 n 倍，封顶 5 秒
_CHUNK = 1 << 20
_NET_TIMEOUT = 10
# helper 等旧进程退出的上限（约 60 秒）：防 pid 被复用后永等
_HELPER_MAX_WAIT_SECONDS = 60


def parse_version(v: str) -> tuple:
    """'v0.7.6' → (0, 7, 6)；解析不出数字返回 ()（任何比较都判不新）。"""
    nums = re.findall(r"\d+", str(v or ""))
    return tuple(int(n) for n in nums[:3])


def is_newer(latest: str, current: str = VERSION) -> bool:
    return parse_version(latest) > parse_version(current)


def _platform() -> tuple[str, str]:
    if sys.platform.startswith("linux"):
        return PLATFORMS["linux"]
    if sys.platform == "win32":
        return PLATFORMS["win32"]
    if sys.platform == "darwin":
        return PLATFORMS["darwin"]
    raise RuntimeError(f"不支持自更新的平台: {sys.platform}")


def platform_suffix() -> str:
    """Release 资产文件名的平台后缀（与 CI 产物命名一致）。"""
    return _platform()[1]


def platform_key() -> str:
    """latest.json 里本平台的键。"""
    return _platform()[0]


def asset_name(version: str, suffix: str | None = None) -> str:
    return f"zentray_{version}{suffix or platform_suffix()}"


def asset_url(version: str, suffix: str | None = None) -> str:
    """本平台安装包的确定性 Release 地址——下载白名单的唯一合法形态。"""
    return f"{DOWNLOAD_PREFIX}v{version}/{asset_name(version, suffix)}"


# —— 检查：清单优先，旧发布无清单时回退 ————————————————————————————————


def _proxies(proxy: str) -> dict | None:
    """空代理 = requests 默认（环境变量）；GUI 进程读不到系统代理时由设置填入。"""
    p = (proxy or "").strip()
    return {"http": p, "https": p} if p else None


def _latest_tag(proxy: str) -> str | None:
    """经 releases/latest 网页 302 跳转取最新 tag；任何失败返回 None（退回 API 路径）。"""
    try:
        resp = requests.get(HTML_LATEST, allow_redirects=False, timeout=_NET_TIMEOUT,
                            proxies=_proxies(proxy))
        m = re.search(r"/releases/tag/(v[\w.\-]+)",
                      resp.headers.get("Location") or "")
        return m.group(1) if m else None
    except Exception:
        return None


def _try_release_json(proxy: str) -> dict | None:
    """尽力取 latest release 富信息（资产/说明/时间）；403 限额等任何失败仅返回 None。"""
    try:
        resp = requests.get(RELEASES_API, timeout=_NET_TIMEOUT, proxies=_proxies(proxy))
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def _to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _no_update(version: str, suffix: str) -> dict:
    return {
        "version": version, "has_update": False, "asset_ready": False,
        "asset_url": "", "asset_name": "", "asset_size": 0, "sha256": "",
        "notes_url": TAG_URL + f"v{version}", "published_at": "", "body": "",
    }


def manifest_result(manifest: dict, key: str, suffix: str) -> dict:
    """latest.json → 检查结果。

    清单是「可安装版本」的真相：版本不比当前新 → 无更新；本平台条目缺失或不合格 →
    asset_ready=False（不回退到无哈希的旧路径）。条目只提供大小与 SHA256，下载地址必须与
    确定性规则完全相等，清单不能把下载引到别处。
    """
    version = str(manifest.get("version") or "").lstrip("v")
    result = _no_update(version, suffix)
    result["published_at"] = str(manifest.get("pub_date") or "")
    result["body"] = str(manifest.get("notes") or "")[:4000]
    if not is_newer(version):
        return result
    result["has_update"] = True
    result["asset_name"] = asset_name(version, suffix)
    entry = (manifest.get("platforms") or {}).get(key)
    if not isinstance(entry, dict):
        logger.warning("更新清单缺少 %s 条目，按未就绪处理", key)
        return result
    url = str(entry.get("url") or "")
    sha256 = str(entry.get("sha256") or "").lower()
    if url != asset_url(version, suffix) or not _SHA256_RE.match(sha256):
        logger.warning("更新清单的 %s 条目不合格，按未就绪处理", key)
        return result
    result.update(asset_ready=True, asset_url=url,
                  asset_size=_to_int(entry.get("size")), sha256=sha256)
    return result


def _fetch_manifest(proxy: str) -> dict | None:
    """取 latest.json；任何失败（404 = 旧发布无清单、网络、JSON 非法）返回 None。"""
    try:
        resp = requests.get(MANIFEST_URL, timeout=_NET_TIMEOUT, proxies=_proxies(proxy))
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.debug("更新清单不可用，回退 Release 探测: %s", e)
        return None
    if (not isinstance(data, dict)
            or not parse_version(str(data.get("version") or ""))
            or not isinstance(data.get("platforms"), dict)):
        logger.debug("更新清单结构不合法，回退 Release 探测")
        return None
    return data


def _fallback_result(proxy: str) -> dict:
    """无清单的旧发布：网页 302 取 tag（不受 API 匿名限额）→ API 取资产 → HEAD 探测。"""
    suffix = platform_suffix()
    rel = None
    tag = _latest_tag(proxy)
    if tag is None:
        try:
            resp = requests.get(RELEASES_API, timeout=_NET_TIMEOUT,
                                proxies=_proxies(proxy))
            resp.raise_for_status()
            rel = resp.json()
            tag = str(rel.get("tag_name") or "")
        except Exception as e:
            raise RuntimeError(f"检查更新失败：{e}") from e
    version = tag.lstrip("v")
    result = _no_update(version, suffix)
    if not is_newer(version):
        return result
    result["has_update"] = True
    result["asset_name"] = asset_name(version, suffix)
    if rel is None:
        rel = _try_release_json(proxy)
    if rel is not None:
        asset = next((a for a in rel.get("assets", []) if isinstance(a, dict)
                      and a.get("name") == result["asset_name"]), None)
        url = str(asset.get("browser_download_url") or "") if asset else ""
        if url == asset_url(version, suffix):
            result.update(
                asset_ready=True, asset_url=url, asset_size=_to_int(asset.get("size")),
                notes_url=rel.get("html_url") or result["notes_url"],
                published_at=rel.get("published_at") or "",
                body=(rel.get("body") or "")[:800],
            )
        return result
    # API 拿不到（匿名 403 限额等）：下载地址确定性合成，HEAD 探测是否已上传
    url = asset_url(version, suffix)
    try:
        head = requests.head(url, allow_redirects=True, timeout=_NET_TIMEOUT,
                             proxies=_proxies(proxy))
    except Exception as e:
        raise RuntimeError(f"检查更新失败：{e}") from e
    if head.status_code < 400:
        result.update(asset_ready=True, asset_url=url,
                      asset_size=_to_int(head.headers.get("content-length")))
    return result


def check(proxy: str = "") -> dict:
    """查最新版本并返回检查结果；网络失败抛 RuntimeError。"""
    key, suffix = _platform()
    manifest = _fetch_manifest(proxy)
    if manifest is not None:
        return manifest_result(manifest, key, suffix)
    return _fallback_result(proxy)


# —— 完整性校验 ———————————————————————————————————————————————————————————


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(_CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def verify_package(path: Path, size: int = 0, sha256: str = "") -> str | None:
    """完整性校验，通过返回 None，否则返回首个失败原因：大小 → SHA256 → zip 全成员 CRC。"""
    try:
        actual = path.stat().st_size
    except OSError as e:
        return f"文件不可读（{e}）"
    if size and actual != size:
        return f"大小不符，期望 {size} 字节，实际 {actual} 字节"
    if sha256 and sha256_file(path).lower() != sha256.lower():
        return "SHA256 不符"
    if path.name.endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as zf:
                bad = zf.testzip()
        except (zipfile.BadZipFile, OSError) as e:
            return f"压缩包损坏（{e}）"
        if bad is not None:
            return f"压缩包成员损坏（{bad}）"
    return None


def extract_archive(zip_path: Path, dest: Path) -> None:
    """解压更新包到 dest。

    zipfile.extractall 不还原符号链接（macOS .app 内 framework 的 Versions/Current 等
    链接会变成含目标路径文本的普通文件），外部属性高 16 位才是 Unix mode；同时拒绝
    绝对路径、`..` 与穿越既有链接的成员（zip-slip）。
    """
    dest.mkdir(parents=True, exist_ok=True)
    root = str(dest.resolve())
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            parts = [p for p in name.split("/") if p not in ("", ".")]
            if (not parts or name.startswith("/") or ".." in parts
                    or ":" in name.split("/")[0]):
                raise RuntimeError(f"更新包含非法路径: {info.filename}")
            target = dest.joinpath(*parts)
            resolved = str(os.path.realpath(target))
            if resolved != root and not resolved.startswith(root + os.sep):
                raise RuntimeError(f"更新包含越界路径: {info.filename}")
            mode = (info.external_attr >> 16) & 0xFFFF
            target.parent.mkdir(parents=True, exist_ok=True)
            if stat.S_ISLNK(mode):
                if target.is_symlink() or target.is_file():
                    target.unlink()
                elif target.is_dir():
                    shutil.rmtree(target)
                os.symlink(zf.read(info).decode("utf-8", "surrogateescape"), target)
                continue
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out, _CHUNK)
            perm = stat.S_IMODE(mode)
            if perm:
                # 保写权限：Windows 上只读文件会让后续 rmtree 失败
                os.chmod(target, perm | 0o200)


# —— 状态文件（都在 UPDATES_DIR 下；测试整体替换该目录）——————————————————————


def _restart_flag() -> Path:
    """重启标记：restart() 写入，helper 见标记才拉起新进程。"""
    return UPDATES_DIR / "restart.flag"


def _notified_file() -> Path:
    """已通知过「发现新版」的版本，每个版本只通知一次（跨重启）。"""
    return UPDATES_DIR / "notified.json"


def _swap_result_file() -> Path:
    """换目录 / 替换 .app 的结果，由退出后的 helper 写入（ok=1|0 与 reason=…）。"""
    return UPDATES_DIR / "swap-result.txt"


def notified_versions() -> set:
    try:
        data = json.loads(_notified_file().read_text("utf-8"))
    except (OSError, ValueError):
        return set()
    items = data.get("notified") if isinstance(data, dict) else None
    return {str(v) for v in items} if isinstance(items, list) else set()


def mark_notified(version: str) -> None:
    versions = notified_versions()
    versions.add(version)
    path = _notified_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps({"notified": sorted(versions, key=parse_version)[-20:]}),
        encoding="utf-8")
    os.replace(tmp, path)


def pop_swap_result() -> dict | None:
    """读取并清除上次替换的结果；没有则返回 None。"""
    path = _swap_result_file()
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    path.unlink(missing_ok=True)
    fields = dict(line.split("=", 1) for line in lines if "=" in line)
    if not fields:
        return None
    return {"ok": fields.get("ok") == "1", "reason": fields.get("reason", "").strip()}


# —— helper 脚本（纯字符串构造，便于测试断言）———————————————————————————————


def _sh_quote(path) -> str:
    s = str(path)
    for ch in ('\\', '"', "$", "`"):
        s = s.replace(ch, "\\" + ch)
    return f'"{s}"'


def linux_restart_script(pid: int, exe: str, restart_flag: str) -> str:
    """旧进程退出后：有重启标记才拉起新版本（标记随之清除），否则静默退出。"""
    return (
        "#!/bin/sh\n"
        "i=0\n"
        f"while kill -0 {pid} 2>/dev/null && [ $i -lt {_HELPER_MAX_WAIT_SECONDS * 2} ]; do\n"
        "  sleep 0.5\n"
        "  i=$((i + 1))\n"
        "done\n"
        f"if [ -f {_sh_quote(restart_flag)} ]; then\n"
        f"  rm -f {_sh_quote(restart_flag)}\n"
        f"  exec {_sh_quote(exe)}\n"
        "fi\n"
    )


def windows_update_bat(pid: int, exe_path: str, exe_dir: str, new_dir: str,
                       old_bak: str, restart_flag: str, result_file: str,
                       cleanup_delay: int = 8) -> str:
    """旧 pid 退出 → 旧目录挪 .old（被占用则重试）→ .new 顶上（失败回滚）→ 有标记才启动。

    纯 ASCII 文本，由 _write_bat 按控制台代码页落盘。等待用 ping 不用 timeout——后者在
    stdin 被重定向时会立刻报错退出。替换失败时原程序保持可用，原因写入 result_file，
    下次启动由应用提示用户。
    """
    return (
        "@echo off\r\n"
        "setlocal\r\n"
        f'set "EXE_PATH={exe_path}"\r\n'
        f'set "EXE_DIR={exe_dir}"\r\n'
        f'set "NEW_DIR={new_dir}"\r\n'
        f'set "OLD_BAK={old_bak}"\r\n'
        f'set "FLAG={restart_flag}"\r\n'
        f'set "RESULT={result_file}"\r\n'
        "set /a WAITED=0\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" 2>nul | findstr /R /C:"\\<{pid}\\>" >nul\r\n'
        "if errorlevel 1 goto waited\r\n"
        "set /a WAITED+=1\r\n"
        f"if %WAITED% GEQ {_HELPER_MAX_WAIT_SECONDS} goto waited\r\n"
        "ping -n 2 127.0.0.1 >nul\r\n"
        "goto wait\r\n"
        ":waited\r\n"
        'set "WANT_RESTART=0"\r\n'
        'if exist "%FLAG%" set "WANT_RESTART=1"\r\n'
        'del /f /q "%FLAG%" >nul 2>&1\r\n'
        'if exist "%OLD_BAK%" rmdir /s /q "%OLD_BAK%" >nul 2>&1\r\n'
        "set /a TRY=0\r\n"
        ":move_old\r\n"
        'move /y "%EXE_DIR%" "%OLD_BAK%" >nul 2>&1\r\n'
        "if not errorlevel 1 goto moved_old\r\n"
        "set /a TRY+=1\r\n"
        "if %TRY% GEQ 10 goto dir_in_use\r\n"
        "ping -n 3 127.0.0.1 >nul\r\n"
        "goto move_old\r\n"
        ":dir_in_use\r\n"
        '>"%RESULT%" echo ok=0\r\n'
        '>>"%RESULT%" echo reason=dir_in_use\r\n'
        "goto finish\r\n"
        ":moved_old\r\n"
        'move /y "%NEW_DIR%" "%EXE_DIR%" >nul 2>&1\r\n'
        "if not errorlevel 1 goto finish\r\n"
        "set /a TRY=0\r\n"
        ":rollback\r\n"
        'move /y "%OLD_BAK%" "%EXE_DIR%" >nul 2>&1\r\n'
        "if not errorlevel 1 goto rolled_back\r\n"
        "set /a TRY+=1\r\n"
        "if %TRY% GEQ 10 goto rollback_failed\r\n"
        "ping -n 3 127.0.0.1 >nul\r\n"
        "goto rollback\r\n"
        ":rolled_back\r\n"
        '>"%RESULT%" echo ok=0\r\n'
        '>>"%RESULT%" echo reason=swap_failed\r\n'
        "goto finish\r\n"
        ":rollback_failed\r\n"
        '>"%RESULT%" echo ok=0\r\n'
        '>>"%RESULT%" echo reason=rollback_failed\r\n'
        'set "WANT_RESTART=0"\r\n'
        "powershell -NoProfile -WindowStyle Hidden -Command \"Add-Type -AssemblyName "
        "PresentationFramework; [System.Windows.MessageBox]::Show('ZenTray update could not "
        "finish. To repair, rename the folder %OLD_BAK% to %EXE_DIR%', 'ZenTray update')\" "
        ">nul 2>&1\r\n"
        ":finish\r\n"
        'if "%WANT_RESTART%"=="1" (\r\n'
        '  start "" "%EXE_PATH%"\r\n'
        ")\r\n"
        f"ping -n {max(1, cleanup_delay) + 1} 127.0.0.1 >nul\r\n"
        'rmdir /s /q "%OLD_BAK%" >nul 2>&1\r\n'
        'del /f /q "%~f0" >nul 2>&1\r\n'
    )


_MACOS_SH = """#!/bin/sh
i=0
while kill -0 {pid} 2>/dev/null && [ $i -lt {ticks} ]; do
  sleep 0.5
  i=$((i + 1))
done
want=0
if [ -f {flag} ]; then want=1; fi
rm -f {flag}
bak={bak}
rm -rf "$bak"
finish() {{
  printf 'ok=%s\\nreason=%s\\n' "$1" "$2" > {result}
  if [ "$want" = 1 ]; then open {app}; fi
  rm -f "$0"
  exit 0
}}
if ! mv {app} "$bak"; then finish 0 dir_in_use; fi
if mv {staged} {app}; then rm -rf "$bak"; finish 1 ""; fi
rm -rf {app}
mv "$bak" {app} || finish 0 rollback_failed
finish 0 swap_failed
"""


def macos_update_sh(pid: int, app_path: str, staged_app: str, restart_flag: str,
                    result_file: str) -> str:
    """旧进程退出后：旧 .app 先挪 .bak，新包顶上；顶替失败则挪回，原应用始终可用。"""
    return _MACOS_SH.format(
        pid=pid, ticks=_HELPER_MAX_WAIT_SECONDS * 2,
        flag=_sh_quote(restart_flag), bak=_sh_quote(app_path + ".bak"),
        result=_sh_quote(result_file), app=_sh_quote(app_path),
        staged=_sh_quote(staged_app))


def _oem_encoding() -> str | None:
    """cmd 解析批处理所用的控制台代码页（OEM）；非 Windows 返回 None。

    直接取系统代码页号（cp936 / cp437 / cp65001 …），这些编码名确定存在。
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        return f"cp{ctypes.windll.kernel32.GetOEMCP()}"
    except Exception:
        return "oem"


def _write_bat(path: Path, content: str) -> None:
    """按控制台代码页落盘：cmd 用系统代码页解析批处理，UTF-8 会让中文等非 ASCII 路径
    乱码（move 找不到目录）。非 Windows 平台没有这个代码页，退回 UTF-8（仅供测试）。"""
    encoding = _oem_encoding()
    path.write_bytes(content.encode(encoding or "utf-8"))


def _check_oem_representable(*values: str) -> None:
    """路径里有控制台代码页表示不了的字符时，helper 必然找不到目录——装之前就拒绝。"""
    encoding = _oem_encoding()
    if encoding is None:
        return
    try:
        for value in values:
            value.encode(encoding)
    except UnicodeEncodeError:
        raise RuntimeError(
            "安装路径含当前系统代码页无法表示的字符，无法自动替换，"
            "请手动下载安装包覆盖安装") from None


# —— 下载 ———————————————————————————————————————————————————————————————————


class _Cancelled(Exception):
    """下载被取消：静默退出，不回写任何状态。"""


def _range_start(content_range) -> int:
    """解析 Content-Range: bytes 100-999/1000 的起点；解析不出返回 -1。"""
    m = re.match(r"bytes\s+(\d+)-", content_range or "")
    return int(m.group(1)) if m else -1


def _stream_download(url: str, part: Path, expected_size: int, cancel: threading.Event,
                     proxy: str, report) -> None:
    """把 url 流式写入 part，已有的半包经 Range 续传；中断抛异常，由调用方重试。"""
    have = part.stat().st_size if part.exists() else 0
    if have and expected_size and have >= expected_size:
        if have > expected_size:
            part.unlink(missing_ok=True)  # 超长半包是脏数据，从头下
            have = 0
        else:
            return  # 字节已齐，只差校验
    headers = {"Range": f"bytes={have}-"} if have else {}
    with requests.get(url, stream=True, timeout=(_NET_TIMEOUT, 60), headers=headers,
                      proxies=_proxies(proxy)) as resp:
        resp.raise_for_status()
        resuming = bool(have) and resp.status_code == 206 \
            and _range_start(resp.headers.get("Content-Range")) == have
        start = have if resuming else 0  # 服务端不理会 Range 就从头下
        length = _to_int(resp.headers.get("content-length"))
        total = (start + length) if length else 0
        got = start
        report(got, total or expected_size)
        with open(part, "ab" if start else "wb") as out:
            for chunk in resp.iter_content(chunk_size=_CHUNK):
                if cancel.is_set():
                    raise _Cancelled()
                if chunk:
                    out.write(chunk)
                    got += len(chunk)
                    report(got, total or expected_size)
    if (total or expected_size) and got != (total or expected_size):
        raise RuntimeError(f"下载不完整（{got}/{total or expected_size} 字节）")


def is_packaged() -> bool:
    """是否为打包后的发行版（源码/venv 运行时自更新没有意义，helper 也无从拉起）。"""
    return bool(getattr(sys, "frozen", False))


class _PackageInvalid(RuntimeError):
    """安装前复核不通过：安装包已丢弃，须重新下载。"""


class UpdaterService:
    """检查/下载/安装的状态机（单例；网络与安装在后台线程，状态写入加锁）。"""

    _instance = None

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # idle | checking | uptodate | available | downloading | ready | installing
        # | installed | error
        self._state = "idle"
        self._helper_spawned = False  # 退出后接管的 helper 已武装（待重启）
        self._progress = 0  # 0-100；总量未知时为 0，改看 downloaded / total
        self._downloaded = 0
        self._total = 0
        self._error = ""
        self._version = ""  # 待下载 / 已下载 / 已安装的目标版本
        self._path = ""
        self._result = None  # 最近一次检查结果
        self._manual = False  # 最近一次检查是否用户触发
        self._generation = 0
        self._cancel = threading.Event()
        self._download_thread = None
        self._listeners = []

    @classmethod
    def instance(cls) -> "UpdaterService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def subscribe(self, callback) -> None:
        """订阅状态变化（回调可能在后台线程触发；UI 侧须自行切回主线程）。"""
        with self._lock:
            self._listeners.append(callback)

    def status(self) -> dict:
        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict:
        return {
            "state": self._state, "progress": self._progress,
            "downloaded": self._downloaded, "total": self._total,
            "error": self._error, "version": self._version, "path": self._path,
            "manual": self._manual,
            "result": dict(self._result) if self._result else None,
            "restart_armed": self._helper_spawned,
        }

    def _transition(self, **fields) -> None:
        """加锁改状态（state=… 对应 self._state），并在锁外通知订阅者。"""
        with self._lock:
            for name, value in fields.items():
                if not hasattr(self, "_" + name):
                    raise AttributeError(f"UpdaterService 无状态字段 {name!r}")
                setattr(self, "_" + name, value)
            snapshot = self._snapshot_locked()
        self._emit(snapshot)

    def _emit(self, snapshot: dict) -> None:
        for callback in list(self._listeners):
            try:
                callback(snapshot)
            except Exception:
                logger.exception("更新状态回调异常")

    def _current(self, generation: int, cancel: threading.Event) -> bool:
        """该代次是否仍是当前任务（未被取消、未被新一轮取代）。"""
        with self._lock:
            return generation == self._generation and not cancel.is_set()

    # —— 检查 ——

    def start_check(self, proxy: str = "", manual: bool = True, on_done=None) -> dict:
        """异步检查（后台线程）。检查/下载/安装进行中、包已就绪或待重启时不重复发起。"""
        with self._lock:
            if self._state in HOLD_STATES:
                return {"started": False, "state": self._state}
            previous = (self._state, self._error)
            self._generation += 1
            generation = self._generation
            self._manual = manual
            self._state, self._error = "checking", ""
            snapshot = self._snapshot_locked()
        self._emit(snapshot)
        threading.Thread(
            target=self._check_worker,
            args=(generation, proxy, manual, previous, on_done),
            daemon=True,
        ).start()
        return {"started": True, "state": "checking"}

    def _check_worker(self, generation, proxy, manual, previous, on_done) -> None:
        result, error = None, ""
        try:
            result = check(proxy)
        except Exception as e:
            error = str(e)
            logger.warning("检查更新失败: %s", error)
        with self._lock:
            if generation == self._generation and self._state == "checking":
                if result is not None:
                    self._result = result
                    self._state = "available" if result["has_update"] else "uptodate"
                    self._error = ""
                elif manual:
                    self._state, self._error = "error", error
                else:
                    # 静默检查失败不打扰：回到检查前的状态
                    self._state, self._error = previous
                snapshot = self._snapshot_locked()
            else:
                snapshot = None
        if snapshot is not None:
            self._emit(snapshot)
        if on_done is not None:
            try:
                on_done(result, error)
            except Exception:
                logger.exception("更新检查回调异常")

    # —— 下载 ——

    def start_download(self, version: str = "", proxy: str = "") -> dict:
        """异步下载最近一次检查到的安装包。

        地址、大小、哈希只取服务端自己的检查结果，不信任调用方传来的值。
        """
        with self._lock:
            if self._state in ("downloading", "ready", "installing", "installed"):
                return {"started": False, "state": self._state}
            if self._state == "checking":
                raise RuntimeError("正在检查更新，请稍候")
            result = self._result
            if not result or not result.get("has_update"):
                raise RuntimeError("请先检查更新")
            if not result.get("asset_ready"):
                raise RuntimeError("新版本的安装包尚未就绪，请稍后再试")
            if version and version != result["version"]:
                raise RuntimeError("可更新的版本已变化，请重新检查更新")
            self._generation += 1
            generation = self._generation
            self._cancel = threading.Event()
            cancel = self._cancel
            result = dict(result)
            self._state, self._error = "downloading", ""
            self._progress, self._downloaded = 0, 0
            self._total = _to_int(result.get("asset_size"))
            self._version = result["version"]
            self._path = ""
            snapshot = self._snapshot_locked()
        self._emit(snapshot)
        threading.Thread(
            target=self._download_worker,
            args=(generation, result, proxy, cancel),
            daemon=True,
        ).start()
        return {"started": True, "state": "downloading"}

    def cancel_download(self) -> dict:
        """取消下载：立即作废当前代次（旧线程此后的进度/完成/失败全部忽略）。

        半包 .part 留着，下次下载从断点续传；最终仍要过完整性校验才会被采用。
        """
        with self._lock:
            if self._state != "downloading":
                return {"cancelled": False, "state": self._state}
            self._generation += 1
            self._cancel.set()
            self._state, self._error = "available", ""
            self._progress, self._downloaded = 0, 0
            snapshot = self._snapshot_locked()
        self._emit(snapshot)
        return {"cancelled": True, "state": "available"}

    def _download_worker(self, generation: int, result: dict, proxy: str,
                         cancel: threading.Event) -> None:
        size, sha256 = _to_int(result.get("asset_size")), str(result.get("sha256") or "")
        dest = UPDATES_DIR / result["asset_name"]
        # 每个代次一个半包文件：被取消的旧线程即使还阻塞在网络读上，也写不到新任务的文件
        part = UPDATES_DIR / f"{dest.name}.{generation}.part"

        def report(got: int, total: int) -> None:
            if self._current(generation, cancel):
                self._transition(
                    downloaded=got, total=total,
                    progress=min(99, got * 100 // total) if total else 0)

        try:
            UPDATES_DIR.mkdir(parents=True, exist_ok=True)
            previous, self._download_thread = self._download_thread, threading.current_thread()
            if previous is not None and previous.is_alive():
                previous.join(timeout=3.0)
            orphans = sorted(UPDATES_DIR.glob(dest.name + ".*.part"))
            if previous is not None and previous.is_alive():
                orphans = []  # 旧线程还握着它的半包：不动它，本次从零下
            adopted = part.exists()
            for stale in orphans:
                if stale == part:
                    continue
                try:
                    if not adopted:  # 接着上一轮（已取消/已中断）的断点续传
                        os.replace(stale, part)
                        adopted = True
                        continue
                except OSError:
                    pass
                stale.unlink(missing_ok=True)
            if not self._current(generation, cancel):
                return
            # 磁盘上已有同版本的包：能校验且通过就直接复用，否则丢弃重下
            reusable = dest.exists() and bool(size or sha256 or dest.suffix == ".zip")
            problem = verify_package(dest, size, sha256) if reusable else None
            if reusable and problem is None:
                self._download_done(generation, cancel, dest, result["version"], size)
                return
            if dest.exists():
                logger.info("丢弃校验不通过的旧更新包 %s: %s", dest.name, problem or "无法校验")
                dest.unlink(missing_ok=True)
            error = ""
            for attempt in range(1, _MAX_DOWNLOAD_RETRIES + 1):
                if not self._current(generation, cancel):
                    return
                try:
                    _stream_download(result["asset_url"], part, size, cancel, proxy, report)
                    break
                except _Cancelled:
                    return
                except Exception as e:
                    error = str(e)
                    logger.warning("更新包下载失败（第 %d 次）: %s", attempt, error)
                    if cancel.wait(min(_RETRY_BACKOFF_SECONDS * attempt, 5.0)):
                        return
            else:
                raise RuntimeError(f"下载失败：{error}")
            if not self._current(generation, cancel):
                return
            problem = verify_package(part, size, sha256)
            if problem is not None:
                part.unlink(missing_ok=True)
                raise RuntimeError(f"更新包校验失败（{problem}），已丢弃，请重试")
            os.replace(part, dest)
            self._download_done(generation, cancel, dest, result["version"], size)
        except _Cancelled:
            return
        except Exception as e:
            logger.warning("更新包下载未完成: %s", e)
            if self._current(generation, cancel):
                self._transition(state="error", error=str(e))

    def _download_done(self, generation: int, cancel: threading.Event, dest: Path,
                       version: str, size: int) -> None:
        if not self._current(generation, cancel):
            return
        total = size or dest.stat().st_size
        self._transition(state="ready", progress=100, downloaded=total, total=total,
                         path=str(dest), version=version, error="")

    # —— 安装并（经确认后）重启 ——

    def start_install(self) -> dict:
        """异步安装（后台线程，Linux 的 polkit 认证可能等很久）；失败原因进状态。"""
        with self._lock:
            if self._helper_spawned or self._state == "installing":
                return {"started": False, "state": self._state}
            if self._state != "ready" or not self._path:
                raise RuntimeError("安装包尚未就绪，请先下载")
            self._state, self._error = "installing", ""
            path, result = self._path, dict(self._result or {})
            snapshot = self._snapshot_locked()
        self._emit(snapshot)
        threading.Thread(target=self._install_worker, args=(path, result), daemon=True).start()
        return {"started": True, "state": "installing"}

    def _install_worker(self, path: str, result: dict) -> None:
        try:
            self._install_and_record(path, result)
        except RuntimeError:
            pass  # 原因已记入状态
        except Exception as e:
            logger.exception("更新安装异常")
            self._transition(state="ready", error=f"安装失败：{e}")

    def install(self) -> dict:
        """平台分派安装并武装 helper（不退出）——退出由 restart() 在用户确认后触发。"""
        with self._lock:
            if self._helper_spawned:
                return {"installed": True}  # 已安装待重启（重复点击不叠加 helper）
            if self._state != "ready" or not self._path:
                raise RuntimeError("安装包尚未就绪，请先下载")
            self._state, self._error = "installing", ""
            path, result = self._path, dict(self._result or {})
        return self._install_and_record(path, result)

    def _install_and_record(self, path: str, result: dict) -> dict:
        try:
            self._install_package(Path(path), result)
        except _PackageInvalid as e:
            Path(path).unlink(missing_ok=True)
            self._transition(state="error", error=str(e), path="")
            raise
        except Exception as e:
            logger.warning("更新安装失败: %s", e)
            # 包还在、已校验：留在 ready，用户可重试安装或手动安装，不必重新下载
            self._transition(state="ready", error=f"安装失败：{e}")
            raise
        self._transition(state="installed", helper_spawned=True, progress=100, error="")
        return {"installed": True}

    def _install_package(self, path: Path, result: dict) -> None:
        if not is_packaged():
            raise RuntimeError("开发环境不支持应用内安装，请前往发布页下载安装包")
        problem = verify_package(path, _to_int(result.get("asset_size")),
                                 str(result.get("sha256") or ""))
        if problem is not None:
            raise _PackageInvalid(f"安装包复核不通过（{problem}），请重新下载")
        if sys.platform.startswith("linux"):
            self._install_linux(path)
        elif sys.platform == "win32":
            self._install_windows(path)
        elif sys.platform == "darwin":
            self._install_macos(path)
        else:
            raise RuntimeError(f"不支持自更新的平台: {sys.platform}")

    def restart(self) -> dict:
        """用户确认后退出当前进程（helper 等进程退出后拉起新版本）。"""
        with self._lock:
            if not self._helper_spawned:
                raise RuntimeError("尚未安装更新")
            flag = _restart_flag()
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text("restart\n", encoding="utf-8")
        self._quit()
        return {"restarting": True}

    def defer_restart(self) -> dict:
        """「稍后」：不写重启标记。helper 仍会在退出后完成替换与清理，但不拉起应用。"""
        with self._lock:
            if not self._helper_spawned:
                raise RuntimeError("尚未安装更新")
            _restart_flag().unlink(missing_ok=True)
            state = self._state
        return {"deferred": True, "state": state}

    def _install_linux(self, deb: Path) -> None:
        hint = f"可手动安装已下载的包：sudo apt install {deb}"
        try:
            completed = subprocess.run(
                ["pkexec", "apt", "install", "-y", str(deb)],
                capture_output=True, text=True, timeout=600,
            )
        except FileNotFoundError:
            raise RuntimeError(f"未找到 pkexec，{hint}") from None
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"系统安装超时，{hint}") from None
        if completed.returncode != 0:
            # pkexec 126 / 127 = 用户关掉了认证窗口或未获授权
            why = "已取消系统认证" if completed.returncode in (126, 127) else "系统安装失败"
            raise RuntimeError(f"{why}，{hint}")
        # 新版本已落盘（路径不变），等旧进程退出后按重启标记决定是否拉起
        self._spawn_helper(
            ["sh", "-c", linux_restart_script(os.getpid(), sys.executable,
                                              str(_restart_flag()))])

    def _install_windows(self, zip_path: Path) -> None:
        exe_path = Path(sys.executable).resolve()
        exe_dir = exe_path.parent
        new_dir = exe_dir.with_name(exe_dir.name + ".new")
        old_bak = exe_dir.with_name(exe_dir.name + ".old")
        try:
            for folder in (new_dir, old_bak):
                if folder.exists():
                    shutil.rmtree(folder)
            new_dir.mkdir(parents=True)
            extract_archive(zip_path, new_dir)
            # onedir zip 若含单一顶层目录（Compress-Archive -Path dist/ZenTray），取其内容
            inner = list(new_dir.iterdir())
            if len(inner) == 1 and inner[0].is_dir():
                top = inner[0]
                for child in list(top.iterdir()):
                    child.replace(new_dir / child.name)
                top.rmdir()
            if not (new_dir / exe_path.name).is_file():
                raise RuntimeError("更新包内未找到主程序，请重新下载")
            _check_oem_representable(str(exe_path), str(exe_dir), str(new_dir),
                                     str(old_bak))
        except PermissionError:
            raise RuntimeError(
                "无写入权限，无法替换程序目录，请以管理员身份运行或手动安装") from None
        bat = UPDATES_DIR / "update.bat"
        UPDATES_DIR.mkdir(parents=True, exist_ok=True)
        _write_bat(bat, windows_update_bat(
            os.getpid(), str(exe_path), str(exe_dir), str(new_dir), str(old_bak),
            str(_restart_flag()), str(_swap_result_file())))
        # CREATE_NO_WINDOW：不闪控制台黑窗
        subprocess.Popen(["cmd", "/c", str(bat)], cwd=str(UPDATES_DIR),
                         creationflags=0x08000000)

    def _install_macos(self, zip_path: Path) -> None:
        # sys.executable = …/ZenTray.app/Contents/MacOS/ZenTray
        exe = Path(sys.executable).resolve()
        app_path = exe.parents[2]
        if not app_path.name.endswith(".app"):
            raise RuntimeError("应用不在 .app 包内，无法自动替换，请手动下载安装")
        stage = UPDATES_DIR / "_mac_stage"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir(parents=True)
        extract_archive(zip_path, stage)
        staged_app = stage / app_path.name
        if not (staged_app / "Contents" / "MacOS" / exe.name).is_file():
            raise RuntimeError(f"更新包内未找到可启动的 {app_path.name}，请重新下载")
        sh_path = UPDATES_DIR / "update.sh"
        sh_path.write_text(
            macos_update_sh(os.getpid(), str(app_path), str(staged_app),
                            str(_restart_flag()), str(_swap_result_file())),
            encoding="utf-8")
        sh_path.chmod(sh_path.stat().st_mode | stat.S_IXUSR)
        subprocess.Popen(["/bin/sh", str(sh_path)], start_new_session=True)

    @staticmethod
    def _spawn_helper(argv: list) -> None:
        subprocess.Popen(argv, start_new_session=True)

    @staticmethod
    def _quit() -> None:
        # 本方法在 HTTP 处理线程被调：QTimer.singleShot 跨线程启动定时器静默失效
        # （应用永不退出、helper 永等），须用 queued invocation 投递到 GUI 线程
        from PySide6.QtCore import QMetaObject, Qt
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app:
            QMetaObject.invokeMethod(app, "quit", Qt.ConnectionType.QueuedConnection)


def cleanup_stale() -> None:
    """启动时清理上次更新的残留（应用刚启动，不可能有下载/安装在进行）。"""
    try:
        _cleanup_stale()
    except Exception:
        logger.warning("清理更新残留失败", exc_info=True)


def _cleanup_stale() -> None:
    root = Path(UPDATES_DIR)
    if root.is_dir():
        for stale in root.glob("*.part"):
            stale.unlink(missing_ok=True)
        for name in ("_win_stage", "_mac_stage"):
            shutil.rmtree(root / name, ignore_errors=True)
        for name in ("update.bat", "update.sh"):
            (root / name).unlink(missing_ok=True)
        _restart_flag().unlink(missing_ok=True)
        try:
            _platform()
        except RuntimeError:
            return
        # 只留「比当前运行版本新」的安装包：下次检查到同一版本可免重新下载
        for package in root.glob("zentray_*"):
            matched = _PACKAGE_RE.match(package.name)
            if matched and not is_newer(matched.group(1)):
                package.unlink(missing_ok=True)
    if not is_packaged():
        return
    exe = Path(sys.executable).resolve()
    if sys.platform == "win32":
        folder = exe.parent
        for leftover in (folder.with_name(folder.name + ".new"),
                         folder.with_name(folder.name + ".old")):
            shutil.rmtree(leftover, ignore_errors=True)
    elif sys.platform == "darwin" and exe.parents[2].name.endswith(".app"):
        app = exe.parents[2]
        shutil.rmtree(app.with_name(app.name + ".bak"), ignore_errors=True)


def tray_hint(snapshot: dict) -> str:
    """托盘菜单里的更新提示文案；空串 = 不显示该项。

    发现新版后一直显示（下载中、已就绪、出错都算），直到装完变为「重启以完成更新」。
    """
    state = snapshot.get("state")
    if state == "installed":
        return f"⬆️ 重启以完成更新 v{snapshot.get('version', '')}"
    result = snapshot.get("result") or {}
    if state in ("available", "downloading", "ready", "error") and result.get("has_update"):
        return f"⬆️ 新版本 v{result.get('version', '')}"
    return ""
