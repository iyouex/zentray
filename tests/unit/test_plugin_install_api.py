"""插件预览校验 / 路径安全。"""
from pathlib import Path

from zentray.api.handlers import _safe_plugin_path, _validate_plugin_path


def test_validate_bundled_net_cleanup():
    root = Path(__file__).resolve().parents[2]
    path = root / "bundled_plugins" / "net-cleanup"
    code, body = _validate_plugin_path({"path": str(path)})
    assert code == 200
    assert body["ok"] is True
    assert body["preview"]["id"] == "net-cleanup"


def test_reject_outside_home(tmp_path, monkeypatch):
    # /etc 通常不在允许范围
    path, err = _safe_plugin_path("/etc")
    assert path is None
    assert err and "允许范围" in err
