"""UpdaterService 状态机：下载/取消/续传/校验/安装/重启标记/启动清理，以及本地假 GitHub 的真 socket 集成。

一切落盘都在 tmp_path：autouse fixture 把 updater.UPDATES_DIR 指过去，并统一按 Linux deb 命名，
用例在任何平台的 CI 上行为一致。
"""
import hashlib
import http.server
import json
import os
import stat
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from zentray.services import updater
from zentray.services.updater import UpdaterService, asset_url

NEW = "9.9.9"
# 2.375 MiB：两个整块 + 半块，能看出分块进度与续传起点
PAYLOAD = bytes(range(256)) * (2 * 4096 + 1536)
SIZE = len(PAYLOAD)
SHA = hashlib.sha256(PAYLOAD).hexdigest()
CHUNK = 1 << 20


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "UPDATES_DIR", tmp_path / "updates")
    monkeypatch.setattr(updater, "platform_suffix", lambda: "_amd64.deb")
    monkeypatch.setattr(updater, "_RETRY_BACKOFF_SECONDS", 0.01)


def _result(**overrides):
    result = {"version": NEW, "has_update": True, "asset_ready": True,
              "asset_url": asset_url(NEW), "asset_name": "zentray_9.9.9_amd64.deb",
              "asset_size": SIZE, "sha256": SHA, "notes_url": "", "published_at": "",
              "body": ""}
    result.update(overrides)
    return result


def _available(**overrides):
    svc = UpdaterService()
    svc._state, svc._version = "available", NEW
    svc._result = _result(**overrides)
    return svc


class _Stream:
    def __init__(self, chunks, status=200, headers=None):
        self._chunks, self.status_code, self.headers = chunks, status, headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size):
        yield from self._chunks


def _full_stream(data=PAYLOAD):
    return _Stream([data[i:i + CHUNK] for i in range(0, len(data), CHUNK)],
                   headers={"content-length": str(len(data))})


def _partial_stream(start, data=PAYLOAD):
    rest = data[start:]
    return _Stream([rest[i:i + CHUNK] for i in range(0, len(rest), CHUNK)], status=206,
                   headers={"Content-Range": f"bytes {start}-{len(data) - 1}/{len(data)}",
                            "content-length": str(len(rest))})


def _wait(svc, *states, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = svc.status()
        if snapshot["state"] in states:
            return snapshot
        time.sleep(0.01)
    raise AssertionError(f"state 未在 {timeout}s 内进入 {states}: {svc.status()}")


def _package():
    return updater.UPDATES_DIR / "zentray_9.9.9_amd64.deb"


def _seed_package(data):
    """下载前就把一个包放到磁盘上（模拟上次会话或旧版更新器留下的文件）。"""
    _package().parent.mkdir(parents=True, exist_ok=True)
    _package().write_bytes(data)


# —— 下载：前置条件 ————————————————————————————————————————————————————————————


def test_download_requires_a_prior_check():
    with pytest.raises(RuntimeError, match="请先检查更新"):
        UpdaterService().start_download()


def test_download_refuses_when_package_not_ready():
    with pytest.raises(RuntimeError, match="尚未就绪"):
        _available(asset_ready=False).start_download()


def test_download_refuses_when_available_version_changed():
    with pytest.raises(RuntimeError, match="版本已变化"):
        _available().start_download("0.0.1")


@pytest.mark.parametrize("state", ["downloading", "ready", "installing", "installed"])
def test_download_is_a_noop_while_an_update_is_in_flight(state):
    svc = _available()
    svc._state = state
    assert svc.start_download() == {"started": False, "state": state}


# —— 下载：落盘、校验、续传 ————————————————————————————————————————————————————————


def test_download_streams_to_disk_and_verifies_hash(monkeypatch):
    calls, seen = [], []
    monkeypatch.setattr(updater.requests, "get",
                        lambda url, **kw: calls.append((url, kw)) or _full_stream())
    svc = _available()
    svc.subscribe(lambda snapshot: seen.append((snapshot["state"], snapshot["progress"])))

    assert svc.start_download(NEW, "http://127.0.0.1:7897") == {
        "started": True, "state": "downloading"}
    done = _wait(svc, "ready")

    assert calls[0][0] == asset_url(NEW)  # 地址只来自服务端自己的检查结果
    assert calls[0][1]["proxies"] == {"http": "http://127.0.0.1:7897",
                                      "https": "http://127.0.0.1:7897"}
    assert Path(done["path"]).read_bytes() == PAYLOAD
    assert done["progress"] == 100 and done["downloaded"] == done["total"] == SIZE
    assert not list(updater.UPDATES_DIR.glob("*.part"))  # 半包转正，不留 .part
    progress = [p for state, p in seen if state == "downloading"]
    assert progress == sorted(progress) and max(progress) <= 99  # 单调不回退，校验前不到 100


def test_download_discards_package_when_hash_mismatches(monkeypatch):
    monkeypatch.setattr(updater.requests, "get", lambda url, **kw: _full_stream())
    svc = _available(sha256="b" * 64)
    svc.start_download()

    failed = _wait(svc, "error")

    assert "校验失败" in failed["error"] and "SHA256" in failed["error"]
    assert not _package().exists() and not list(updater.UPDATES_DIR.glob("*.part"))
    assert failed["result"]["has_update"]  # 仍可重试下载


def test_download_resumes_from_partial_bytes_after_an_interruption(monkeypatch):
    half = CHUNK + 123  # 故意不对齐分块
    headers_seen = []

    def fake_get(url, **kwargs):
        headers_seen.append(kwargs.get("headers"))
        if len(headers_seen) == 1:  # 首次：声明全量，发到一半断线
            return _Stream([PAYLOAD[:half]], headers={"content-length": str(SIZE)})
        return _partial_stream(half)

    monkeypatch.setattr(updater.requests, "get", fake_get)
    svc = _available()
    svc.start_download()

    done = _wait(svc, "ready")

    assert headers_seen == [{}, {"Range": f"bytes={half}-"}]
    assert Path(done["path"]).read_bytes() == PAYLOAD


def test_download_starts_over_when_server_ignores_range(monkeypatch):
    half = CHUNK + 123
    responses = iter([_Stream([PAYLOAD[:half]], headers={"content-length": str(SIZE)}),
                      _full_stream()])  # 第二次服务端不理会 Range，回了 200 全量
    monkeypatch.setattr(updater.requests, "get", lambda url, **kw: next(responses))
    svc = _available()
    svc.start_download()

    done = _wait(svc, "ready")

    assert Path(done["path"]).read_bytes() == PAYLOAD  # 没有在半包后面重复追加


def test_download_gives_up_after_retries_and_reports_failure(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        raise ConnectionError("reset by peer")

    monkeypatch.setattr(updater.requests, "get", fake_get)
    svc = _available()
    svc.start_download()

    failed = _wait(svc, "error")

    assert len(calls) == updater._MAX_DOWNLOAD_RETRIES
    assert "下载失败" in failed["error"] and "reset by peer" in failed["error"]


def test_existing_verified_package_is_reused_without_downloading(monkeypatch):
    _seed_package(PAYLOAD)
    monkeypatch.setattr(updater.requests, "get",
                        lambda url, **kw: pytest.fail("不应重新下载"))
    svc = _available()
    svc.start_download()

    assert _wait(svc, "ready", timeout=3)["path"] == str(_package())


def test_existing_package_that_fails_verification_is_replaced(monkeypatch):
    _seed_package(b"truncated leftover")
    monkeypatch.setattr(updater.requests, "get", lambda url, **kw: _full_stream())
    svc = _available()
    svc.start_download()
    _wait(svc, "ready")

    assert _package().read_bytes() == PAYLOAD


def test_package_that_cannot_be_verified_is_never_reused(monkeypatch):
    """回退路径既无哈希也无大小时，磁盘上的 deb 无从校验（可能是旧版更新器留下的半包）。"""
    _seed_package(PAYLOAD)
    calls = []
    monkeypatch.setattr(updater.requests, "get",
                        lambda url, **kw: calls.append(url) or _full_stream())
    svc = _available(sha256="", asset_size=0)
    svc.start_download()
    _wait(svc, "ready")

    assert calls == [asset_url(NEW)]


# —— 下载：取消与代次隔离 ————————————————————————————————————————————————————————


def test_cancel_makes_late_progress_and_completion_invisible(monkeypatch):
    gate, headers_seen = threading.Event(), []
    chunks = [PAYLOAD[:CHUNK], PAYLOAD[CHUNK:]]

    def fake_get(url, **kwargs):
        headers_seen.append(kwargs.get("headers"))
        if len(headers_seen) > 1:  # 取消后重新下载：从断点续传
            return _partial_stream(CHUNK)

        def trickle(chunk_size):
            yield chunks[0]
            gate.wait(10)  # 卡在网络上，直到测试放行
            yield chunks[1]

        stream = _Stream([], headers={"content-length": str(SIZE)})
        stream.iter_content = trickle
        return stream

    monkeypatch.setattr(updater.requests, "get", fake_get)
    svc = _available()
    states = []
    svc.subscribe(lambda snapshot: states.append(snapshot["state"]))
    svc.start_download()
    deadline = time.monotonic() + 5
    while svc.status()["downloaded"] < CHUNK and time.monotonic() < deadline:
        time.sleep(0.01)

    assert svc.cancel_download() == {"cancelled": True, "state": "available"}
    cancelled = svc.status()
    assert cancelled["progress"] == 0 and cancelled["error"] == ""
    assert cancelled["result"]["has_update"]  # 仍可重新下载

    gate.set()  # 旧线程此刻才拿到剩余字节
    svc._download_thread.join(5)
    assert svc.status()["state"] == "available"  # 旧的「完成」没有回写
    assert "ready" not in states and "error" not in states
    assert not _package().exists()  # 被取消的字节不会变成可安装的包

    svc.start_download()
    done = _wait(svc, "ready")
    assert headers_seen[1]["Range"] == f"bytes={CHUNK}-"  # 接着断点，没有从头下
    assert Path(done["path"]).read_bytes() == PAYLOAD


def test_cancel_makes_a_late_failure_invisible(monkeypatch):
    gate = threading.Event()

    def fake_get(url, **kwargs):
        def trickle(chunk_size):
            yield PAYLOAD[:CHUNK]
            gate.wait(10)
            raise ConnectionError("reset by peer")

        stream = _Stream([], headers={"content-length": str(SIZE)})
        stream.iter_content = trickle
        return stream

    monkeypatch.setattr(updater.requests, "get", fake_get)
    svc = _available()
    svc.start_download()
    deadline = time.monotonic() + 5
    while svc.status()["downloaded"] < CHUNK and time.monotonic() < deadline:
        time.sleep(0.01)

    svc.cancel_download()
    gate.set()
    svc._download_thread.join(5)

    assert svc.status() == {**svc.status(), "state": "available", "error": "", "progress": 0}


def test_cancel_outside_a_download_is_a_noop():
    assert _available().cancel_download() == {"cancelled": False, "state": "available"}
    assert UpdaterService().cancel_download() == {"cancelled": False, "state": "idle"}


# —— 检查：手动/静默、失败处理 ————————————————————————————————————————————————————


def _check_returning(result):
    return lambda proxy="": result


def _check_raising(proxy=""):
    raise RuntimeError("检查更新失败：boom")


def test_manual_check_reports_available(monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def gated_check(proxy=""):
        entered.set()
        release.wait(5)
        return _result()

    monkeypatch.setattr(updater, "check", gated_check)
    svc = UpdaterService()
    done = threading.Event()

    assert svc.start_check("http://127.0.0.1:7897", manual=True,
                           on_done=lambda result, error: done.set())["started"]
    assert entered.wait(5)
    assert svc.status()["state"] == "checking" and svc.status()["manual"] is True
    release.set()
    done.wait(5)
    assert svc.status()["state"] == "available"
    assert svc.status()["result"]["version"] == NEW


def test_check_passes_the_configured_proxy(monkeypatch):
    seen = []

    def fake_check(proxy=""):
        seen.append(proxy)
        return _result()

    monkeypatch.setattr(updater, "check", fake_check)
    svc = UpdaterService()
    svc.start_check("http://127.0.0.1:7897", manual=False)
    _wait(svc, "available")
    assert seen == ["http://127.0.0.1:7897"]


def test_manual_check_reports_uptodate(monkeypatch):
    monkeypatch.setattr(updater, "check",
                        _check_returning({**_result(), "has_update": False}))
    svc = UpdaterService()
    svc.start_check(manual=True)
    assert _wait(svc, "uptodate")["manual"] is True


@pytest.mark.parametrize("state", updater.HOLD_STATES)
def test_check_is_not_repeated_while_an_update_is_in_flight(monkeypatch, state):
    monkeypatch.setattr(updater, "check", lambda proxy="": pytest.fail("不应重复检查"))
    svc = UpdaterService()
    svc._state = state
    assert svc.start_check(manual=True) == {"started": False, "state": state}


def test_manual_check_failure_is_reported(monkeypatch):
    monkeypatch.setattr(updater, "check", _check_raising)
    svc = UpdaterService()
    svc.start_check(manual=True)
    assert _wait(svc, "error")["error"] == "检查更新失败：boom"


def test_silent_check_failure_stays_invisible(monkeypatch):
    monkeypatch.setattr(updater, "check", _check_raising)
    svc = UpdaterService()
    svc.start_check(manual=False)
    quiet = _wait(svc, "idle")
    assert quiet["error"] == "" and quiet["result"] is None


def test_manual_check_failure_keeps_a_previously_found_update(monkeypatch):
    monkeypatch.setattr(updater, "check", _check_raising)
    monkeypatch.setattr(updater.requests, "get", lambda url, **kw: _full_stream())
    svc = _available()
    svc.start_check(manual=True)
    assert _wait(svc, "error")["result"]["has_update"]  # 一次网络失败不该让新版消失
    svc.start_download()
    _wait(svc, "ready")


def test_stale_check_result_is_ignored(monkeypatch):
    started, done = threading.Event(), threading.Event()

    def slow_check(proxy=""):
        started.set()
        time.sleep(0.2)
        return _result()

    monkeypatch.setattr(updater, "check", slow_check)
    svc = UpdaterService()
    svc.start_check(manual=True, on_done=lambda result, error: done.set())
    assert started.wait(5)
    with svc._lock:  # 被新一轮取代
        svc._generation += 1
        svc._state = "idle"
    done.wait(5)
    assert svc.status()["state"] == "idle" and svc.status()["result"] is None


# —— 安装与重启确认 ——————————————————————————————————————————————————————————————


@pytest.fixture
def packaged(monkeypatch):
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)


def _stub_platform_installs(monkeypatch, behavior=None):
    """平台安装器打桩：本组只测安装状态机；桩保留「安装成功后武装 helper」的语义。"""
    calls = []

    def fake_install(self, path):
        calls.append(Path(path))
        if behavior is not None:
            behavior()
        self._spawn_helper(["stub-installer"])

    for name in ("_install_linux", "_install_windows", "_install_macos"):
        monkeypatch.setattr(UpdaterService, name, fake_install)
    return calls


def _ready(monkeypatch):
    _seed_package(PAYLOAD)
    svc = UpdaterService()
    svc._state, svc._path, svc._version = "ready", str(_package()), NEW
    svc._result = _result()
    spawned = []
    monkeypatch.setattr(UpdaterService, "_spawn_helper",
                        staticmethod(lambda argv: spawned.append(argv)))
    return svc, spawned


def test_install_requires_ready_package():
    with pytest.raises(RuntimeError, match="尚未就绪"):
        UpdaterService().install()


def test_install_is_refused_in_a_dev_environment(monkeypatch):
    svc, spawned = _ready(monkeypatch)
    calls = _stub_platform_installs(monkeypatch)
    with pytest.raises(RuntimeError, match="开发环境"):
        svc.install()
    assert svc.status()["state"] == "ready" and "开发环境" in svc.status()["error"]
    assert spawned == [] and calls == [] and _package().exists()


def test_install_failure_keeps_the_package_ready_for_retry(monkeypatch, packaged):
    svc, spawned = _ready(monkeypatch)
    pending = [RuntimeError("已取消系统认证，可手动安装")]

    def fail_once():
        if pending:
            raise pending.pop()

    calls = _stub_platform_installs(monkeypatch, behavior=fail_once)
    with pytest.raises(RuntimeError):
        svc.install()
    failed = svc.status()
    assert failed["state"] == "ready"
    assert failed["error"] == "安装失败：已取消系统认证，可手动安装"
    assert _package().exists() and spawned == []  # 包还在，可以重试

    assert svc.install() == {"installed": True}  # 重试用的是同一个包
    assert svc.status()["state"] == "installed" and svc.status()["error"] == ""
    assert calls == [_package(), _package()]


def test_install_discards_a_package_that_no_longer_verifies(monkeypatch, packaged):
    svc, spawned = _ready(monkeypatch)
    calls = _stub_platform_installs(monkeypatch)
    _package().write_bytes(b"tampered after download")  # 目录已由 _ready() 建好
    with pytest.raises(RuntimeError, match="复核不通过"):
        svc.install()
    assert svc.status()["state"] == "error" and "复核不通过" in svc.status()["error"]
    assert not _package().exists() and calls == [] and spawned == []


def test_install_arms_the_helper_only_once(monkeypatch, packaged):
    svc, spawned = _ready(monkeypatch)
    _stub_platform_installs(monkeypatch)
    assert svc.install() == {"installed": True}
    assert svc.install() == {"installed": True}
    assert len(spawned) == 1


def test_start_install_runs_in_background_and_reports_failure(monkeypatch, packaged):
    svc, spawned = _ready(monkeypatch)

    def boom():
        raise RuntimeError("boom")

    _stub_platform_installs(monkeypatch, behavior=boom)
    assert svc.start_install() == {"started": True, "state": "installing"}
    assert svc.start_install() == {"started": False, "state": "installing"}
    failed = _wait(svc, "ready")
    assert failed["error"] == "安装失败：boom" and _package().exists()


def test_restart_happens_only_on_request_after_install(monkeypatch, packaged):
    quitted = []
    monkeypatch.setattr(UpdaterService, "_quit", staticmethod(lambda: quitted.append(1)))
    with pytest.raises(RuntimeError, match="尚未安装更新"):
        UpdaterService().restart()
    with pytest.raises(RuntimeError, match="尚未安装更新"):
        UpdaterService().defer_restart()

    svc, spawned = _ready(monkeypatch)
    _stub_platform_installs(monkeypatch)
    svc.install()
    assert not updater._restart_flag().exists() and quitted == []  # 装完不自动重启

    assert svc.restart() == {"restarting": True}
    assert updater._restart_flag().exists() and quitted == [1]

    assert svc.defer_restart() == {"deferred": True, "state": "installed"}  # 「稍后」
    assert not updater._restart_flag().exists() and len(spawned) == 1


# —— 平台安装（真解包/真脚本生成，只桩掉进程启动）———————————————————————————————


def _capture_popen(monkeypatch):
    spawned = []
    monkeypatch.setattr(updater.subprocess, "Popen",
                        lambda argv, **kw: spawned.append((argv, kw)))
    return spawned


def test_linux_install_maps_pkexec_outcomes(monkeypatch, packaged):
    monkeypatch.setattr(updater.sys, "platform", "linux")
    spawned = _capture_popen(monkeypatch)
    run = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr(updater.subprocess, "run", run)
    deb = Path("/home/u/updates/zentray_9.9.9_amd64.deb")

    UpdaterService()._install_linux(deb)

    assert run.call_args.args[0] == ["pkexec", "apt", "install", "-y", str(deb)]
    script = spawned[0][0][2]
    assert spawned[0][0][:2] == ["sh", "-c"]
    assert f"kill -0 {os.getpid()}" in script and updater._restart_flag().name in script

    run.return_value = MagicMock(returncode=126)  # 用户关掉了认证窗口
    with pytest.raises(RuntimeError, match="已取消系统认证.*sudo apt install"):
        UpdaterService()._install_linux(deb)
    run.return_value = MagicMock(returncode=100)
    with pytest.raises(RuntimeError, match="系统安装失败"):
        UpdaterService()._install_linux(deb)
    run.side_effect = FileNotFoundError()
    with pytest.raises(RuntimeError, match="pkexec"):
        UpdaterService()._install_linux(deb)
    run.side_effect = subprocess.TimeoutExpired("pkexec", 600)
    with pytest.raises(RuntimeError, match="超时"):
        UpdaterService()._install_linux(deb)
    assert len(spawned) == 1  # 失败时绝不武装 helper


def test_windows_install_stages_a_new_dir_and_arms_a_flag_gated_bat(tmp_path, monkeypatch):
    apps = tmp_path / "Apps" / "ZenTray"
    apps.mkdir(parents=True)
    (apps / "ZenTray.exe").write_bytes(b"old")
    monkeypatch.setattr(updater.sys, "executable", str(apps / "ZenTray.exe"))
    spawned = _capture_popen(monkeypatch)
    with zipfile.ZipFile(tmp_path / "pkg.zip", "w") as zf:
        zf.writestr("ZenTray/ZenTray.exe", b"new")
        zf.writestr("ZenTray/_internal/lib.dat", b"lib")

    UpdaterService()._install_windows(tmp_path / "pkg.zip")

    new_dir = tmp_path / "Apps" / "ZenTray.new"
    assert (new_dir / "ZenTray.exe").read_bytes() == b"new"  # 单一顶层目录已拍平
    assert (new_dir / "_internal" / "lib.dat").read_bytes() == b"lib"
    assert (apps / "ZenTray.exe").read_bytes() == b"old"  # 运行中的目录原样不动
    bat = updater.UPDATES_DIR / "update.bat"
    assert spawned[0][0] == ["cmd", "/c", str(bat)]
    text = bat.read_bytes().decode("utf-8")  # 纯 ASCII 脚本，任何代码页下都能读回
    assert str(updater._restart_flag()) in text and 'start ""' in text


def test_windows_install_refuses_a_zip_without_the_main_program(tmp_path, monkeypatch):
    apps = tmp_path / "Apps" / "ZenTray"
    apps.mkdir(parents=True)
    monkeypatch.setattr(updater.sys, "executable", str(apps / "ZenTray.exe"))
    monkeypatch.setattr(updater.subprocess, "Popen",
                        lambda argv, **kw: pytest.fail("不应武装 helper"))
    with zipfile.ZipFile(tmp_path / "pkg.zip", "w") as zf:
        zf.writestr("ZenTray/readme.txt", "x")
    with pytest.raises(RuntimeError, match="未找到主程序"):
        UpdaterService()._install_windows(tmp_path / "pkg.zip")


@pytest.mark.skipif(sys.platform == "win32", reason="需要符号链接")
def test_macos_install_restores_bundle_symlinks_and_arms_helper(tmp_path, monkeypatch):
    exe = tmp_path / "Applications" / "ZenTray.app" / "Contents" / "MacOS" / "ZenTray"
    monkeypatch.setattr(updater.sys, "executable", str(exe))
    spawned = _capture_popen(monkeypatch)
    framework = "ZenTray.app/Contents/Frameworks/Foo.framework"
    with zipfile.ZipFile(tmp_path / "pkg.zip", "w") as zf:
        zf.writestr("ZenTray.app/Contents/MacOS/ZenTray", b"Mach-O")
        zf.writestr(f"{framework}/Versions/A/Foo", b"Mach-O")
        link = zipfile.ZipInfo(f"{framework}/Versions/Current")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(link, "A")

    UpdaterService()._install_macos(tmp_path / "pkg.zip")

    staged = updater.UPDATES_DIR / "_mac_stage" / "ZenTray.app"
    assert os.readlink(staged / "Contents/Frameworks/Foo.framework/Versions/Current") == "A"
    script = updater.UPDATES_DIR / "update.sh"
    assert spawned == [((["/bin/sh", str(script)]), {"start_new_session": True})]
    assert script.stat().st_mode & stat.S_IXUSR
    text = script.read_text()
    assert str(exe.parents[2]) in text and str(updater._restart_flag()) in text


# —— 启动清理 ————————————————————————————————————————————————————————————————


def test_cleanup_stale_removes_leftovers_but_keeps_newer_packages():
    root = updater.UPDATES_DIR
    root.mkdir()
    (root / "zentray_0.7.9_amd64.deb").write_bytes(b"old")
    _package().write_bytes(b"newer than running version")  # 目录在上面已建
    (root / "zentray_9.9.9_amd64.deb.3.part").write_bytes(b"half")
    (root / "zentray_0.7.9_amd64.deb.2.part").write_bytes(b"half")
    for name in ("_mac_stage", "_win_stage"):
        (root / name).mkdir()
    (root / "update.bat").write_text("x")
    (root / "update.sh").write_text("x")
    updater._restart_flag().write_text("restart")
    updater.mark_notified("1.0.0")

    updater.cleanup_stale()

    assert sorted(p.name for p in root.iterdir()) == [
        "notified.json", "zentray_9.9.9_amd64.deb"]


def test_cleanup_stale_tolerates_a_missing_directory():
    updater.cleanup_stale()
    assert not updater.UPDATES_DIR.exists()


def test_cleanup_stale_removes_platform_leftovers_of_a_packaged_app(tmp_path, monkeypatch):
    monkeypatch.setattr(updater.sys, "frozen", True, raising=False)
    apps = tmp_path / "Apps"
    app = apps / "ZenTray"
    app.mkdir(parents=True)
    for name in ("ZenTray.new", "ZenTray.old"):
        (apps / name).mkdir()
    monkeypatch.setattr(updater.sys, "platform", "win32")
    monkeypatch.setattr(updater.sys, "executable", str(app / "ZenTray.exe"))

    updater.cleanup_stale()

    assert sorted(p.name for p in apps.iterdir()) == ["ZenTray"]

    bundle = apps / "ZenTray.app" / "Contents" / "MacOS"
    bundle.mkdir(parents=True)
    (apps / "ZenTray.app.bak").mkdir()
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    monkeypatch.setattr(updater.sys, "executable", str(bundle / "ZenTray"))

    updater.cleanup_stale()

    assert sorted(p.name for p in apps.iterdir()) == ["ZenTray", "ZenTray.app"]


def test_cleanup_stale_leaves_a_dev_checkout_alone(tmp_path, monkeypatch):
    app = tmp_path / "venv" / "bin"
    app.mkdir(parents=True)
    (app.parent / "venv.old").mkdir()
    monkeypatch.setattr(updater.sys, "executable", str(app / "python"))

    updater.cleanup_stale()

    assert (app.parent / "venv.old").exists()


# —— 真 socket 集成：本地假 GitHub（清单 + 支持 Range 的资产）———————————————————————


def test_end_to_end_against_a_local_release_server(monkeypatch):
    hits, first_asset_request = [], {"yes": True}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            range_header = self.headers.get("Range")
            hits.append((self.path, range_header))
            if self.path.endswith("latest.json"):
                manifest = {"version": NEW, "notes": "## 主题\n- 更新内容",
                            "platforms": {updater.platform_key(): {
                                "url": asset_url(NEW), "size": SIZE, "sha256": SHA}}}
                self._reply(200, json.dumps(manifest).encode())
            elif range_header:
                start = int(range_header.split("=")[1].split("-")[0])
                self._reply(206, PAYLOAD[start:],
                            {"Content-Range": f"bytes {start}-{SIZE - 1}/{SIZE}"})
            elif first_asset_request["yes"]:
                first_asset_request["yes"] = False  # 首次连接发完一个整块就断开
                self.send_response(200)
                self.send_header("Content-Length", str(SIZE))
                self.end_headers()
                self.wfile.write(PAYLOAD[:CHUNK])
            else:
                self._reply(200, PAYLOAD)

        def _reply(self, status, body, headers=None):
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/releases"
    try:
        monkeypatch.setattr(updater, "MANIFEST_URL", f"{base}/latest/download/latest.json")
        monkeypatch.setattr(updater, "DOWNLOAD_PREFIX", f"{base}/download/")
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                     "ALL_PROXY", "all_proxy"):
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("NO_PROXY", "127.0.0.1")

        svc = UpdaterService()
        svc.start_check()
        found = _wait(svc, "available")
        assert found["result"]["sha256"] == SHA
        assert found["result"]["asset_url"] == asset_url(NEW)

        svc.start_download()
        done = _wait(svc, "ready")
        assert Path(done["path"]).read_bytes() == PAYLOAD
        asset_requests = [r for path, r in hits if not path.endswith("latest.json")]
        assert asset_requests == [None, f"bytes={CHUNK}-"]  # 断线后从断点续传

        # 重启应用后再更新到同一版本：磁盘上的包校验通过，免重下
        again = UpdaterService()
        again.start_check()
        _wait(again, "available")
        again.start_download()
        _wait(again, "ready")
        assert len(hits) == 4
    finally:
        server.shutdown()
        server.server_close()
