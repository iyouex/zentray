"""Windows 更新 helper（update.bat）真执行：等旧进程退出、换目录、回滚、按标记才拉起。

只在 Windows 上跑（CI test-windows）。Linux/macOS 开发机执行不了 cmd 批处理，所以这里
是对 bat 逻辑唯一的真实验证；脚本内容断言见 test_updater.py。
"""
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from zentray.services import updater

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="仅 Windows：需要 cmd")

OLD, NEW = b"MZ-old", b"MZ-new"
# 在 OEM 代码页里占非 ASCII 字节的字符：UTF-8 与 CP437/CP936 对它的编码不同，
# 批处理若按错误的代码页落盘，路径就会对不上
NON_ASCII = "é"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(updater, "UPDATES_DIR", tmp_path / "updates")
    updater.UPDATES_DIR.mkdir(parents=True)


def _app(root: Path, marker: bytes, launcher: bool = False) -> Path:
    root.mkdir(parents=True)
    (root / "_internal").mkdir()
    (root / "ZenTray.exe").write_bytes(marker)
    (root / "_internal" / "lib.dat").write_bytes(b"lib" + marker)
    if launcher:
        # 「新版本」的可执行入口：留个标记就退出（真去启动 GUI 程序没法在 CI 里判断）
        (root / "ZenTray.cmd").write_bytes(
            b'@echo off\r\necho ran> "%~dp0ran.txt"\r\n')
    return root


def _short_lived_process():
    proc = subprocess.Popen('cmd /c ping -n 4 127.0.0.1 >nul',
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    threading.Thread(target=proc.wait, daemon=True).start()
    return proc


def _run_helper(pid: int, exe_dir: Path, new_dir: Path, launcher: bool):
    exe_path = exe_dir / ("ZenTray.cmd" if launcher else "ZenTray.exe")
    content = updater.windows_update_bat(
        pid, str(exe_path), str(exe_dir), str(new_dir), str(exe_dir) + ".old",
        str(updater._restart_flag()), str(updater._swap_result_file()), cleanup_delay=1)
    updater._check_oem_representable(str(exe_path), str(exe_dir), str(new_dir),
                                     str(exe_dir) + ".old")
    bat = updater.UPDATES_DIR / "update.bat"
    updater._write_bat(bat, content)
    return bat, subprocess.Popen(["cmd", "/c", str(bat)], cwd=str(updater.UPDATES_DIR),
                                 creationflags=subprocess.CREATE_NO_WINDOW)


def _wait_for(proc, timeout=60):
    proc.wait(timeout=timeout)


def _wait_until(condition, timeout=15, what="条件"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.2)
    raise AssertionError(f"{what}未在 {timeout}s 内成立")


def test_helper_waits_for_the_old_process_then_swaps_without_relaunching(tmp_path):
    apps = tmp_path / f"Apps{NON_ASCII}"
    exe_dir = _app(apps / "ZenTray", OLD)
    new_dir = _app(apps / "ZenTray.new", NEW)
    old = _short_lived_process()

    bat, helper = _run_helper(old.pid, exe_dir, new_dir, launcher=False)
    time.sleep(0.8)
    assert (exe_dir / "ZenTray.exe").read_bytes() == OLD  # 旧进程还活着：不许动运行中的目录

    _wait_for(helper)
    assert old.poll() is not None
    assert (exe_dir / "ZenTray.exe").read_bytes() == NEW  # 已换成新版本
    assert (exe_dir / "_internal" / "lib.dat").read_bytes() == b"lib" + NEW
    assert not new_dir.exists() and not (apps / "ZenTray.old").exists()  # 暂存与备份都清掉
    assert not bat.exists()  # 用后自删
    time.sleep(1.5)
    assert not (exe_dir / "ran.txt").exists()  # 没有重启标记：不拉起（「稍后」）
    assert not updater._swap_result_file().exists()  # 成功不留失败记录


def test_helper_relaunches_only_when_the_restart_flag_exists(tmp_path):
    apps = tmp_path / f"Apps{NON_ASCII}"
    exe_dir = _app(apps / "ZenTray", OLD)
    new_dir = _app(apps / "ZenTray.new", NEW, launcher=True)
    old = _short_lived_process()
    updater._restart_flag().write_text("restart\n")

    _bat, helper = _run_helper(old.pid, exe_dir, new_dir, launcher=True)
    _wait_for(helper)

    _wait_until(lambda: (exe_dir / "ran.txt").exists(), what="按标记拉起新版本")
    assert not updater._restart_flag().exists()  # 标记用后即清


def test_helper_rolls_back_and_reports_when_the_new_build_cannot_be_moved_in(tmp_path):
    apps = tmp_path / f"Apps{NON_ASCII}"
    exe_dir = _app(apps / "ZenTray", OLD)
    old = _short_lived_process()

    # .new 根本不在：旧目录挪走之后新目录顶不上来——必须原样挪回，应用保持可用
    _bat, helper = _run_helper(old.pid, exe_dir, apps / "ZenTray.new", launcher=False)
    _wait_for(helper)

    assert (exe_dir / "ZenTray.exe").read_bytes() == OLD
    assert not (apps / "ZenTray.old").exists()
    assert updater.pop_swap_result() == {"ok": False, "reason": "swap_failed"}


def test_batch_file_is_written_in_the_console_code_page(tmp_path):
    exe_dir = tmp_path / f"Apps{NON_ASCII}" / "ZenTray"
    _app(exe_dir, OLD)
    bat = updater.UPDATES_DIR / "update.bat"
    updater._write_bat(bat, f'@echo off\r\nset "EXE_DIR={exe_dir}"\r\n')
    raw = bat.read_bytes()
    encoding = updater._oem_encoding()
    assert encoding and NON_ASCII.encode(encoding) in raw
    assert NON_ASCII.encode("utf-8") not in raw  # UTF-8 的多字节序列在 cmd 眼里是乱码


def test_unencodable_path_is_refused_before_any_helper_is_written(monkeypatch):
    monkeypatch.setattr(updater, "_oem_encoding", lambda: "ascii")
    with pytest.raises(RuntimeError, match="无法表示的字符"):
        updater._check_oem_representable(f"/tmp/ZenTray{NON_ASCII}")
    updater._check_oem_representable("/tmp/ZenTray")  # 表示得了的路径不拦
