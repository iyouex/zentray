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
