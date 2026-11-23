"""应用内自更新单测（纯函数部分）：版本比较、清单检查与回退、完整性校验、解压、状态文件、helper 脚本。

本模块一切落盘都在 tmp_path：autouse fixture 把 updater.UPDATES_DIR 指到临时目录，
绝不触碰真实数据目录。
"""
import os
import shutil
import stat
import subprocess
import sys
import threading
import time
import zipfile
from unittest.mock import MagicMock

import pytest
import requests as _requests

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # 须在 Qt 实例化之前

from zentray.services import updater
from zentray.services.updater import (
    asset_url,
    check,
    extract_archive,
    is_newer,
    mark_notified,
    notified_versions,
    parse_version,
    platform_key,
    pop_swap_result,
    verify_package,
)

NEW = "9.9.9"
GOOD_SHA = "a" * 64


@pytest.fixture(autouse=True)
def isolated_updates_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "UPDATES_DIR", tmp_path / "updates")


# —— 工具：按 URL 分发的 requests 假实现 ————————————————————————————————————


def _json(data):
    m = MagicMock()
    m.status_code = 200
    m.json.return_value = data
    m.raise_for_status.return_value = None
    return m


def _redirect(tag):
    m = MagicMock()
    m.status_code = 302
    m.headers = {"Location": f"https://github.com/iyouex/zentray/releases/tag/{tag}"}
    return m


def _http_error(code):
    return _requests.HTTPError(f"{code} boom", response=MagicMock(status_code=code))


class _Net:
    """默认模拟「旧发布、无清单」：latest.json 404、API 匿名 403、HEAD 200。"""

    def __init__(self):
        self.manifest = None  # None → 404；"_garbage" → 非法 JSON
        self.redirect_tag = f"v{NEW}"
        self.redirect_error = None
        self.release = None  # None → 403
        self.api_error = None
        self.head_status = 200
        self.head_error = None
        self.gets, self.heads = [], []

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if url == updater.MANIFEST_URL:
            if self.manifest is None:
                raise _http_error(404)
            if self.manifest == "_garbage":
                raise ValueError("invalid json")
            return _json(self.manifest)
        if url == updater.HTML_LATEST:
            if self.redirect_error:
                raise self.redirect_error
            return _redirect(self.redirect_tag)
        if url == updater.RELEASES_API:
            if self.api_error:
                raise self.api_error
            if self.release is None:
                raise _http_error(403)
            return _json(self.release)
        raise AssertionError(f"unexpected GET {url}")

    def head(self, url, **kwargs):
        self.heads.append((url, kwargs))
        if self.head_error:
            raise self.head_error
        m = MagicMock()
        m.status_code = self.head_status
        m.headers = {"content-length": "115"}
        return m


@pytest.fixture
def net(monkeypatch):
    fake = _Net()
    monkeypatch.setattr(updater.requests, "get", fake.get)
    monkeypatch.setattr(updater.requests, "head", fake.head)
    return fake


def _asset(name):
    return {"name": name, "size": 1000,
            "browser_download_url": f"{updater.DOWNLOAD_PREFIX}v{NEW}/{name}"}


def _release(names=("zentray_9.9.9_amd64.deb",), tag=f"v{NEW}"):
    return {
        "tag_name": tag,
        "html_url": f"https://github.com/iyouex/zentray/releases/tag/{tag}",
        "published_at": "2026-10-13T00:00:00Z",
        "body": "## 主题\n- 更新内容",
        "assets": [_asset(n) for n in names],
    }


def _manifest(version=NEW, entry=None, **extra):
    base = {"url": asset_url(version), "size": 1000, "sha256": GOOD_SHA}
    base.update(entry or {})
    return {"version": version, "pub_date": "2026-11-23T00:00:00Z",
            "notes": "## 主题\n- 更新内容",
            "platforms": {platform_key(): base}, **extra}


# —— 版本比较 ———————————————————————————————————————————————————————————————


def test_parse_version():
    assert parse_version("v0.7.6") == (0, 7, 6)
    assert parse_version("1.2") == (1, 2)
    assert parse_version("") == ()
    assert is_newer("v0.7.7", "0.7.6")
    assert not is_newer("v0.7.6", "0.7.6")
    assert not is_newer("v0.7.5", "0.7.6")
    assert not is_newer("", "0.7.6")


def test_platform_table_matches_release_naming():
    assert set(updater.PLATFORMS) == {"linux", "win32", "darwin"}
    assert asset_url("1.2.3", updater.PLATFORMS["linux"][1]) == (
        "https://github.com/iyouex/zentray/releases/download/v1.2.3/zentray_1.2.3_amd64.deb")


def test_unsupported_platform(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "freebsd14")
    with pytest.raises(RuntimeError, match="不支持"):
        updater.platform_suffix()


# —— 检查：SHA256 清单优先 ————————————————————————————————————————————————————


def test_check_manifest_newer_and_ready(net):
    net.manifest = _manifest()
    r = check()
    assert r["has_update"] and r["asset_ready"] and r["version"] == NEW
    assert r["asset_url"] == asset_url(NEW)
    assert r["asset_size"] == 1000 and r["sha256"] == GOOD_SHA
    assert r["body"] == "## 主题\n- 更新内容"
    assert r["notes_url"].endswith(f"/tag/v{NEW}")
    assert r["published_at"] == "2026-11-23T00:00:00Z"
    assert len(net.gets) == 1 and net.heads == []  # 一次请求搞定，不碰 API


def test_check_manifest_not_newer_skips_release_probe(net):
    net.manifest = _manifest(version="0.0.1")
    r = check()
    assert not r["has_update"] and not r["asset_ready"] and r["version"] == "0.0.1"
    assert len(net.gets) == 1


def test_check_manifest_missing_platform_is_not_ready(net):
    net.manifest = _manifest(platforms={})
    r = check()
    assert r["has_update"] and not r["asset_ready"]
    assert r["asset_url"] == "" and r["sha256"] == ""
    assert len(net.gets) == 1  # 清单是真相：不回退到无哈希的旧路径


@pytest.mark.parametrize("entry", [
    {"url": "https://evil.example/zentray_9.9.9_amd64.deb"},
    {"url": asset_url("9.9.8")},  # 版本与地址对不上
    {"sha256": "zz"},
    {"sha256": ""},
])
def test_check_manifest_rejects_bad_entry(net, entry):
    net.manifest = _manifest(entry=entry)
    r = check()
    assert r["has_update"] and not r["asset_ready"] and r["asset_url"] == ""


def test_check_manifest_proxy_passed_through(net):
    net.manifest = _manifest()
    check("http://127.0.0.1:7897")
    assert net.gets[0][1]["proxies"] == {
        "http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}


@pytest.mark.parametrize("manifest", [None, "_garbage", {"version": "x"},
                                      {"version": "1.2.3", "platforms": []}])
def test_check_manifest_unusable_falls_back_to_release_probe(net, manifest):
    net.manifest = manifest
    net.release = _release()
    r = check()
    assert r["has_update"] and r["asset_ready"] and r["version"] == NEW
    assert r["sha256"] == ""  # 回退路径没有哈希
    assert [url for url, _ in net.gets] == [
        updater.MANIFEST_URL, updater.HTML_LATEST, updater.RELEASES_API]


# —— 检查：旧发布无清单，回退 302 → API → HEAD ———————————————————————————————


def test_check_fallback_redirect_then_api_picks_platform_asset(net):
    net.release = _release()
    r = check()
    assert r["has_update"] and r["asset_ready"] and r["version"] == NEW
    assert r["asset_url"] == asset_url(NEW)
    assert r["asset_size"] == 1000
    assert r["notes_url"].endswith(f"/releases/tag/v{NEW}")
    assert r["published_at"] == "2026-10-13T00:00:00Z"
    assert r["body"] == "## 主题\n- 更新内容"


def test_check_fallback_proxy_passed_through(net):
    check("http://127.0.0.1:7897")
    assert net.gets and all(
        kwargs["proxies"] == {"http": "http://127.0.0.1:7897",
                              "https": "http://127.0.0.1:7897"}
        for _, kwargs in net.gets)
    assert net.heads[0][1]["proxies"] == {"http": "http://127.0.0.1:7897",
                                          "https": "http://127.0.0.1:7897"}


def test_check_no_update_skips_api_and_head(net):
    net.redirect_tag = "v0.0.1"
    r = check()
    assert not r["has_update"] and r["version"] == "0.0.1"
    assert [url for url, _ in net.gets] == [updater.MANIFEST_URL, updater.HTML_LATEST]
    assert net.heads == []


def test_check_rate_limited_synthesizes_url_and_heads(net):
    r = check()
    assert r["has_update"] and r["asset_ready"]
    assert r["asset_url"] == asset_url(NEW)
    assert r["asset_size"] == 115
    assert [url for url, _ in net.gets] == [
        updater.MANIFEST_URL, updater.HTML_LATEST, updater.RELEASES_API]
    assert net.heads[0][0] == asset_url(NEW)
    assert net.heads[0][1]["allow_redirects"] is True


def test_check_redirect_unavailable_uses_api_tag(net):
    net.redirect_error = OSError("boom")
    net.release = _release(tag=f"v{NEW}")
    r = check()
    assert r["has_update"] and r["asset_ready"] and r["version"] == NEW


def test_check_fallback_asset_missing_is_not_ready(net):
    net.release = _release(names=("zentray_9.9.9_windows_x64.zip",))
    r = check()
    assert r["has_update"] and not r["asset_ready"] and r["asset_url"] == ""


def test_check_fallback_rejects_unexpected_asset_url(net):
    net.release = _release()
    net.release["assets"][0]["browser_download_url"] = "https://evil.example/x.deb"
    r = check()
    assert r["has_update"] and not r["asset_ready"]


@pytest.mark.parametrize("status", [404, 403, 500])
def test_check_fallback_head_failure_is_not_ready(net, status):
    net.head_status = status
    r = check()
    assert r["has_update"] and not r["asset_ready"]


def test_check_head_network_error_raises(net):
    net.head_error = OSError("boom")
    with pytest.raises(RuntimeError, match="检查更新失败"):
        check()


def test_check_network_error_raises(net):
    net.redirect_error = OSError("boom")
    net.api_error = OSError("boom")
    with pytest.raises(RuntimeError, match="检查更新失败"):
        check()


# —— 完整性校验 ———————————————————————————————————————————————————————————————


def _make_zip(path, members, compression=zipfile.ZIP_STORED):
    with zipfile.ZipFile(path, "w", compression) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def test_verify_package_size_then_hash(tmp_path):
    import hashlib

    pkg = tmp_path / "x.deb"
    pkg.write_bytes(b"abc")
    assert verify_package(pkg) is None  # 没有期望值：只确认可读
    assert "大小不符" in verify_package(pkg, size=4)
    assert verify_package(pkg, size=3) is None
    assert "SHA256" in verify_package(pkg, size=3, sha256=GOOD_SHA)
    real = hashlib.sha256(b"abc").hexdigest()
    assert verify_package(pkg, size=3, sha256=real.upper()) is None  # 大小写不敏感


def test_verify_package_checks_zip_structure_and_every_member_crc(tmp_path):
    good = _make_zip(tmp_path / "good.zip", {"a.txt": b"hello-world", "d/b.txt": b"x"})
    assert verify_package(good) is None

    truncated = tmp_path / "truncated.zip"
    truncated.write_bytes(good.read_bytes()[:-3])  # 半包：中央目录读不出来
    assert "压缩包损坏" in verify_package(truncated)

    data = good.read_bytes()
    at = data.index(b"hello-world")
    corrupted = tmp_path / "corrupted.zip"
    corrupted.write_bytes(data[:at] + b"H" + data[at + 1:])  # 结构完好、内容坏一个字节
    assert "压缩包成员损坏（a.txt）" in verify_package(corrupted)


def test_verify_package_missing_file(tmp_path):
    assert "文件不可读" in verify_package(tmp_path / "missing.deb", size=1)


# —— 解压：还原符号链接与可执行位，拒绝越界路径 ————————————————————————————————



def _symlink_entry(zf, name, target):
    info = zipfile.ZipInfo(name)
    info.create_system = 3  # Unix：外部属性高 16 位才被当作 mode
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    zf.writestr(info, target)


def _unix_file(zf, name, mode, data=""):
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | mode) << 16
    zf.writestr(info, data)


@pytest.mark.skipif(sys.platform == "win32", reason="Windows 发行包不含符号链接")
def test_extract_restores_symlinks_and_exec_bits(tmp_path):
    zpath = tmp_path / "pkg.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        _unix_file(zf, "App/bin/run", 0o755, "#!/bin/sh\n")
        _unix_file(zf, "App/docs/readme.txt", 0o644, "hi")
        _symlink_entry(zf, "App/Current", "bin")
    out = tmp_path / "out"
    extract_archive(zpath, out)
    assert os.readlink(out / "App" / "Current") == "bin"
    assert (out / "App" / "Current" / "run").read_text() == "#!/bin/sh\n"  # 链接可用
    assert (out / "App" / "bin" / "run").stat().st_mode & 0o111
    assert not (out / "App" / "docs" / "readme.txt").stat().st_mode & 0o111


def test_extract_creates_missing_directories_and_accepts_backslash_names(tmp_path):
    # Compress-Archive 不单独写目录项，且历史上用反斜杠做分隔符
    zpath = tmp_path / "pkg.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("ZenTray\\ZenTray.exe", "MZ")
        zf.writestr("ZenTray\\_internal\\lib.dat", "x")
        zf.writestr("ZenTray/", "")
    out = tmp_path / "out"
    extract_archive(zpath, out)
    assert (out / "ZenTray" / "ZenTray.exe").read_text() == "MZ"
    assert (out / "ZenTray" / "_internal" / "lib.dat").read_text() == "x"


def test_extract_keeps_files_writable(tmp_path):
    zpath = tmp_path / "pkg.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        _unix_file(zf, "ro.txt", 0o444, "x")
    out = tmp_path / "out"
    extract_archive(zpath, out)
    assert (out / "ro.txt").stat().st_mode & 0o200


@pytest.mark.parametrize("name", ["../evil.txt", "/abs/evil.txt", "C:/evil.txt",
                                  "app/../../evil.txt"])
def test_extract_rejects_unsafe_paths(tmp_path, name):
    zpath = tmp_path / "pkg.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(name, "x")
    with pytest.raises(RuntimeError, match="非法路径"):
        extract_archive(zpath, tmp_path / "out")
    assert not (tmp_path / "evil.txt").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="需要符号链接")
def test_extract_rejects_writing_through_a_symlink_member(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    zpath = tmp_path / "pkg.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        _symlink_entry(zf, "hole", str(outside))
        zf.writestr("hole/evil.txt", "x")
    with pytest.raises(RuntimeError, match="越界路径"):
        extract_archive(zpath, tmp_path / "out")
    assert not (outside / "evil.txt").exists()


# —— 状态文件 ————————————————————————————————————————————————————————————————


def test_notified_once_per_version_capped_and_persisted():
    assert notified_versions() == set()
    for version in ("0.7.24", "0.7.25", "0.7.26"):
        assert version not in notified_versions()
        mark_notified(version)
        assert version in notified_versions()  # 从文件重读，跨重启有效
    for i in range(30):
        mark_notified(f"0.8.{i}")
    kept = notified_versions()
    assert len(kept) == 20 and "0.8.29" in kept and "0.7.24" not in kept


def test_notified_state_tolerates_corruption():
    updater.UPDATES_DIR.mkdir(parents=True)
    updater._notified_file().write_text("{not json")
    assert notified_versions() == set()


def test_swap_result_roundtrip():
    assert pop_swap_result() is None
    updater.UPDATES_DIR.mkdir(parents=True)
    updater._swap_result_file().write_text("ok=0\nreason=swap_failed\n")
    assert pop_swap_result() == {"ok": False, "reason": "swap_failed"}
    assert pop_swap_result() is None  # 读后即清


# —— helper 脚本 ——————————————————————————————————————————————————————————————


def _short_lived_process():
    proc = subprocess.Popen(["sleep", "0.4"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # 测试进程不回收的话，退出的子进程成了僵尸，kill -0 恒为真（真实场景由 init 回收）
    threading.Thread(target=proc.wait, daemon=True).start()
    return proc


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh")
def test_linux_restart_script_only_relaunches_with_flag(tmp_path):
    exe = tmp_path / "fake-zentray"
    exe.write_text(f"#!/bin/sh\ntouch '{tmp_path / 'restarted'}'\n")
    exe.chmod(0o755)
    flag = updater._restart_flag()
    updater.UPDATES_DIR.mkdir(parents=True)
    script = tmp_path / "helper.sh"

    # 无标记（「稍后」或正常退出）：等旧进程退出后静默离开
    old = _short_lived_process()
    script.write_text(updater.linux_restart_script(old.pid, str(exe), str(flag)))
    subprocess.run(["sh", str(script)], check=True, timeout=20)
    assert not (tmp_path / "restarted").exists()

    # 有标记：旧进程退出后拉起新版本，标记用后即清
    flag.write_text("restart")
    old = _short_lived_process()
    script.write_text(updater.linux_restart_script(old.pid, str(exe), str(flag)))
    subprocess.run(["sh", str(script)], check=True, timeout=20)
    assert (tmp_path / "restarted").exists() and not flag.exists()


def _bat(cleanup_delay=8, **overrides):
    args = dict(pid=4242, exe_path=r"C:\Apps\ZenTray\ZenTray.exe",
                exe_dir=r"C:\Apps\ZenTray", new_dir=r"C:\Apps\ZenTray.new",
                old_bak=r"C:\Apps\ZenTray.old",
                restart_flag=r"C:\u\updates\restart.flag",
                result_file=r"C:\u\updates\swap-result.txt")
    args.update(overrides)
    return updater.windows_update_bat(cleanup_delay=cleanup_delay, **args)


def test_windows_bat_waits_for_exact_pid_with_an_upper_bound():
    s = _bat()
    assert 'tasklist /FI "PID eq 4242"' in s
    assert r'findstr /R /C:"\<4242\>"' in s  # 整词匹配：不会误中内存占用等数字
    assert "if %WAITED% GEQ 60 goto waited" in s
    assert "timeout /t" not in s and "ping -n " in s  # stdin 被重定向时 timeout 会直接报错


def test_windows_bat_swaps_with_rollback_and_only_starts_with_flag():
    s = _bat()
    assert s.isascii() and s.count("\n") == s.count("\r\n") == s.count("\r")
    assert r'set "EXE_DIR=C:\Apps\ZenTray"' in s  # 路径只在头部经变量传入
    move_old = s.index(r'move /y "%EXE_DIR%" "%OLD_BAK%"')
    move_new = s.index(r'move /y "%NEW_DIR%" "%EXE_DIR%"')
    move_back = s.index(r'move /y "%OLD_BAK%" "%EXE_DIR%"')
    assert move_old < move_new < move_back
    for reason in ("dir_in_use", "swap_failed", "rollback_failed"):
        assert f'>>"%RESULT%" echo reason={reason}' in s
    assert 'if exist "%FLAG%" set "WANT_RESTART=1"' in s
    assert s.index('if "%WANT_RESTART%"=="1" (') < s.index('start "" "%EXE_PATH%"')


def test_windows_bat_cleans_up_after_the_swap():
    s = _bat(cleanup_delay=3)
    assert s.index("ping -n 4 127.0.0.1") < s.rindex(r'rmdir /s /q "%OLD_BAK%"')  # 收尾的那次
    assert s.rstrip().endswith(r'del /f /q "%~f0" >nul 2>&1')


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh")
def test_macos_update_sh_moves_old_app_aside_before_replacing():
    s = updater.macos_update_sh(123, "/Applications/ZenTray.app",
                                "/tmp/_stage/ZenTray.app", "/u/restart.flag", "/u/swap.txt")
    assert "kill -0 123" in s and "-lt 120" in s
    aside = s.index('mv "/Applications/ZenTray.app" "$bak"')
    staged = s.index('mv "/tmp/_stage/ZenTray.app" "/Applications/ZenTray.app"')
    back = s.index('mv "$bak" "/Applications/ZenTray.app"')
    assert aside < staged < back
    assert s.index('rm -rf "/Applications/ZenTray.app"') > staged  # 顶替之前绝不删旧包
    assert 'if [ "$want" = 1 ]; then open "/Applications/ZenTray.app"; fi' in s


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX sh")
def test_macos_update_sh_keeps_a_working_app_on_failure(tmp_path):
    app = tmp_path / "ZenTray.app"
    staged = tmp_path / "_stage" / "ZenTray.app"

    def layout(staged_marker):
        shutil.rmtree(app, ignore_errors=True)  # 上一场景的旧包可能还在
        app.mkdir()
        (app / "marker").write_text("old")
        if staged_marker is not None:
            staged.mkdir(parents=True)
            (staged / "marker").write_text(staged_marker)

    def run_helper():
        old = _short_lived_process()
        script = updater.UPDATES_DIR / "update.sh"
        script.write_text(updater.macos_update_sh(
            old.pid, str(app), str(staged), str(updater._restart_flag()),
            str(updater._swap_result_file())))
        subprocess.run(["sh", str(script)], check=True, timeout=20)
        assert not script.exists()  # 用后自删

    updater.UPDATES_DIR.mkdir(parents=True)

    layout("new")
    run_helper()
    assert (app / "marker").read_text() == "new"  # 顶替成功
    assert not (tmp_path / "ZenTray.app.bak").exists()
    assert pop_swap_result() == {"ok": True, "reason": ""}

    layout(None)  # 新包缺失：顶替失败
    run_helper()
    assert (app / "marker").read_text() == "old"  # 旧应用原样挪回，仍可用
    assert not (tmp_path / "ZenTray.app.bak").exists()
    assert pop_swap_result() == {"ok": False, "reason": "swap_failed"}

    if os.geteuid() != 0:  # root 无视目录权限
        layout("new")
        tmp_path.chmod(0o555)  # 旧包挪不动（如 /Applications 无写权限）
        try:
            run_helper()
        finally:
            tmp_path.chmod(0o755)
        assert (app / "marker").read_text() == "old"  # 动不了旧包就什么都不改
        assert pop_swap_result() == {"ok": False, "reason": "dir_in_use"}


@pytest.mark.skipif(sys.platform == "win32", reason="非 Windows 没有 OEM 代码页")
def test_write_bat_falls_back_to_utf8_off_windows(tmp_path):
    bat = tmp_path / "update.bat"
    updater._write_bat(bat, 'set "A=中文路径"\r\n')
    assert bat.read_bytes() == 'set "A=中文路径"\r\n'.encode("utf-8")
    updater._check_oem_representable("中文路径")  # 没有 OEM 代码页就不拦


# —— 退出投递 ————————————————————————————————————————————————————————————————


def test_quit_scheduled_from_worker_thread():
    """回归：_quit 在 HTTP 线程被调，跨线程 QTimer.singleShot 静默失效——
    安装成功后应用永不退出、helper 永等（2026-10-14 实机复现）。
    断言 exec() 在守护超时前被工作线程投递的 quit 打断（旧实现会挂到守护超时）。"""
    from PySide6.QtCore import QCoreApplication, QTimer
    from PySide6.QtWidgets import QApplication

    from zentray.services.updater import UpdaterService

    # 已有实例就复用；否则建 GUI 应用（残留的非 GUI 实例会毒化后续用例的绘制）
    app = QCoreApplication.instance() or QApplication(["zentray-updater-tests"])

    def invoke_from_worker():
        threading.Thread(target=UpdaterService._quit).start()

    QTimer.singleShot(0, invoke_from_worker)  # GUI 线程起事，工作线程投递 quit
    QTimer.singleShot(2000, app.quit)  # 守护：断链时防测试挂死
    started = time.monotonic()
    app.exec()
    assert time.monotonic() - started < 1.0, "quit 未从工作线程及时投递到 GUI 线程"
