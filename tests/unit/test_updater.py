"""应用内自更新单测：版本比较、资产选择、代理传递、下载状态机、helper 脚本内容。"""
from unittest.mock import MagicMock, patch

import pytest

from zentray.services import updater
from zentray.services.updater import (
    UpdaterService,
    is_newer,
    parse_version,
    platform_suffix,
)


def _release(assets=("zentray_9.9.9_amd64.deb",)):
    return {
        "tag_name": "v9.9.9",
        "html_url": "https://github.com/iyouex/zentray/releases/tag/v9.9.9",
        "published_at": "2026-10-13T00:00:00Z",
        "body": "## 主题\n- 更新内容",
        "assets": [
            {"name": n, "size": 1000, "browser_download_url":
             f"https://github.com/iyouex/zentray/releases/download/v9.9.9/{n}"}
            for n in assets
        ],
    }


def _resp(data, status=200):
    m = MagicMock()
    m.status_code = status
    m.returncode = 0  # subprocess.run 结果复用同一 mock（安装成功路径）
    m.json.return_value = data
    m.raise_for_status.return_value = None
    return m


# —— 版本比较 ——


def test_parse_version():
    assert parse_version("v0.7.6") == (0, 7, 6)
    assert parse_version("1.2") == (1, 2)
    assert parse_version("") == ()
    assert is_newer("v0.7.7", "0.7.6")
    assert not is_newer("v0.7.6", "0.7.6")
    assert not is_newer("v0.7.5", "0.7.6")
    assert not is_newer("", "0.7.6")


# —— 检查：资产选择与错误 ——


def test_check_picks_platform_asset():
    with patch.object(updater, "platform_suffix", return_value="_amd64.deb"), \
         patch.object(updater.requests, "get", return_value=_resp(_release())) as g:
        r = UpdaterService.instance().check()
    assert r["has_update"] and r["version"] == "9.9.9"
    assert r["asset_url"].endswith("zentray_9.9.9_amd64.deb")
    assert g.call_args.kwargs["proxies"] is None  # 空代理 = 默认（环境变量）


def test_check_proxy_passed_through():
    with patch.object(updater, "platform_suffix", return_value="_amd64.deb"), \
         patch.object(updater.requests, "get", return_value=_resp(_release())) as g:
        UpdaterService.instance().check("http://127.0.0.1:7897")
    assert g.call_args.kwargs["proxies"] == {
        "http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}


def test_check_missing_platform_asset_when_newer():
    rel = _release(assets=("zentray_9.9.9_windows_x64.zip",))
    with patch.object(updater, "platform_suffix", return_value="_amd64.deb"), \
         patch.object(updater.requests, "get", return_value=_resp(rel)):
        with pytest.raises(RuntimeError, match="尚未上传"):
            UpdaterService.instance().check()


def test_check_network_error():
    with patch.object(updater.requests, "get", side_effect=OSError("boom")):
        with pytest.raises(RuntimeError, match="检查更新失败"):
            UpdaterService.instance().check()


# —— 检查：共享代理出口下 API 匿名 403 限额，网页 302 探测兜底 ——


def _redirect_resp(tag):
    m = MagicMock()
    m.status_code = 302
    m.headers = {"Location": f"https://github.com/iyouex/zentray/releases/tag/{tag}"}
    m.raise_for_status.return_value = None
    return m


def _rate_limited_resp():
    import requests as _r
    m = MagicMock()
    m.status_code = 403
    m.raise_for_status.side_effect = _r.HTTPError("403 rate limit exceeded")
    return m


def test_check_rate_limited_falls_back_to_redirect():
    head = MagicMock()
    head.status_code = 200
    head.headers = {"content-length": "115"}
    with patch.object(updater, "platform_suffix", return_value="_amd64.deb"), \
         patch.object(updater.requests, "get",
                      side_effect=[_redirect_resp("v9.9.9"), _rate_limited_resp()]) as g, \
         patch.object(updater.requests, "head", return_value=head):
        r = UpdaterService.instance().check()
    assert r["has_update"] and r["version"] == "9.9.9"
    assert r["asset_url"] == (
        "https://github.com/iyouex/zentray/releases/download/v9.9.9/zentray_9.9.9_amd64.deb")
    assert r["asset_size"] == 115
    assert g.call_count == 2  # 探测 + 一次 API（403 后不再重试）


def test_check_no_update_skips_api():
    with patch.object(updater.requests, "get",
                      return_value=_redirect_resp("v0.0.1")) as g, \
         patch.object(updater.requests, "head") as h:
        r = UpdaterService.instance().check()
    assert not r["has_update"] and r["version"] == "0.0.1"
    assert g.call_count == 1  # 已是最新：零 API 调用
    h.assert_not_called()


def test_check_rate_limited_asset_missing():
    head = MagicMock()
    head.status_code = 404
    with patch.object(updater, "platform_suffix", return_value="_amd64.deb"), \
         patch.object(updater.requests, "get",
                      side_effect=[_redirect_resp("v9.9.9"), _rate_limited_resp()]), \
         patch.object(updater.requests, "head", return_value=head):
        with pytest.raises(RuntimeError, match="尚未上传"):
            UpdaterService.instance().check()


# —— 下载：URL 白名单 + 状态机 ——


def _fake_stream_response(chunks, total):
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.headers = {"content-length": str(total)}
    m.iter_content.return_value = iter(chunks)
    return m


def test_download_rejects_foreign_url():
    with pytest.raises(RuntimeError, match="非法下载地址"):
        UpdaterService.instance().start_download("https://evil.example/x.deb", "9.9.9")


def test_download_proxy_passed_through(tmp_path):
    svc = UpdaterService.instance()
    with patch.object(updater, "UPDATES_DIR", tmp_path), \
         patch.object(updater.requests, "get",
                      return_value=_fake_stream_response([b"a" * 10], 10)) as g:
        svc.start_download(
            "https://github.com/iyouex/zentray/releases/download/v9.9.9/zentray_9.9.9_amd64.deb",
            "9.9.9", "http://127.0.0.1:7897")
        import time
        for _ in range(100):
            if svc.status()["state"] in ("ready", "error"):
                break
            time.sleep(0.02)
    assert g.call_args.kwargs["proxies"] == {
        "http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}


def test_download_state_machine(tmp_path):
    svc = UpdaterService.instance()
    with patch.object(updater, "UPDATES_DIR", tmp_path), \
         patch.object(updater, "platform_suffix", return_value="_amd64.deb"), \
         patch.object(updater.requests, "get",
                      return_value=_fake_stream_response([b"a" * 10, b"b" * 10], 40)):
        svc.start_download(
            "https://github.com/iyouex/zentray/releases/download/v9.9.9/zentray_9.9.9_amd64.deb",
            "9.9.9")
        # 下载在后台线程，轮询等其收敛
        import time
        for _ in range(100):
            if svc.status()["state"] in ("ready", "error"):
                break
            time.sleep(0.02)
    st = svc.status()
    assert st["state"] == "ready" and st["progress"] == 100
    assert st["path"].endswith("zentray_9.9.9_amd64.deb")
    from pathlib import Path
    assert Path(st["path"]).read_bytes() == b"a" * 10 + b"b" * 10


def test_install_requires_ready():
    svc = UpdaterService.instance()
    svc._state, svc._path = "idle", ""
    with pytest.raises(RuntimeError, match="尚未就绪"):
        svc.install_and_restart()


# —— helper 脚本内容（不真跑） ——


def test_linux_restart_script():
    s = updater.linux_restart_script(123, "/opt/zentray/zentray")
    assert "kill -0 123" in s and 'exec "/opt/zentray/zentray"' in s


def test_windows_bat_waits_replaces_restarts():
    s = updater.windows_update_bat(
        123, r"C:\Program Files\ZenTray", r"C:\Program Files\ZenTray\zentray.exe",
        r"C:\Program Files\ZenTray.new", r"C:\Program Files\ZenTray.old")
    assert 'PID eq 123' in s
    assert r'move /y "C:\Program Files\ZenTray" "C:\Program Files\ZenTray.old"' in s
    assert r'move /y "C:\Program Files\ZenTray.new" "C:\Program Files\ZenTray"' in s
    assert r'start "" "C:\Program Files\ZenTray\zentray.exe"' in s
    assert s.count("\r\n") >= 10  # bat 需 CRLF


def test_macos_sh_replaces_app():
    s = updater.macos_update_sh(123, "/Applications/ZenTray.app", "/tmp/_mac_stage/ZenTray.app")
    assert "kill -0 123" in s
    assert 'rm -rf "/Applications/ZenTray.app"' in s
    assert 'mv "/tmp/_mac_stage/ZenTray.app" "/Applications/ZenTray.app"' in s
    assert 'open "/Applications/ZenTray.app"' in s


def test_platform_suffix_unknown(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "freebsd14")
    with pytest.raises(RuntimeError, match="不支持"):
        platform_suffix()


def test_quit_scheduled_from_worker_thread():
    """回归：_quit 在 HTTP 线程被调，跨线程 QTimer.singleShot 静默失效——
    安装成功后应用永不退出、helper 永等（2026-10-14 实机复现）。
    断言 exec() 在守护超时前被工作线程投递的 quit 打断（旧实现会挂到守护超时）。"""
    import threading
    import time

    from PySide6.QtCore import QCoreApplication, QTimer

    app = QCoreApplication.instance() or QCoreApplication([])

    def invoke_from_worker():
        threading.Thread(target=UpdaterService._quit).start()

    QTimer.singleShot(0, invoke_from_worker)  # GUI 线程起事，工作线程投递 quit
    QTimer.singleShot(2000, app.quit)  # 守护：断链时防测试挂死
    t0 = time.monotonic()
    app.exec()
    assert time.monotonic() - t0 < 1.0, "quit 未从工作线程及时投递到 GUI 线程"


def test_install_no_double_helper(tmp_path, monkeypatch):
    """重启机制武装后重复点安装（含重装同版本）不再叠加 helper。"""
    svc = UpdaterService()
    svc._state = "ready"
    svc._path = str(tmp_path / "x.deb")
    spawned = []
    monkeypatch.setattr(UpdaterService, "_spawn_helper",
                        staticmethod(lambda argv: spawned.append(argv)))
    monkeypatch.setattr(UpdaterService, "_quit", staticmethod(lambda: None))
    monkeypatch.setattr(updater.subprocess, "run", lambda *a, **k: _resp(None))

    assert svc.install_and_restart() == {"restarting": True}
    assert svc.install_and_restart() == {"restarting": True}
    assert len(spawned) == 1
