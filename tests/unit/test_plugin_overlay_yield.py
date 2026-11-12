# tests/unit/test_plugin_overlay_yield.py
"""覆盖副本让位：origin 标记写入 / loader 遮蔽检测 / 让位 API 备份接管。"""
import json
import shutil
from pathlib import Path

from zentray.api.handlers import (
    ApiContext,
    _plugins_list,
    _scanned_loader,
    _update_plugin,
    _yield_plugin_to_bundled,
    set_api_context,
)
from zentray.plugins.loader import PluginLoader
from zentray.resources import get_resource_path

BUNDLED_TOOLBOX = Path(get_resource_path("bundled_plugins")) / "text-toolbox"


def _user_dir(tmp_data_dir) -> Path:
    from zentray.services.settings_manager import SettingsManager

    d = SettingsManager().get_ops_user_plugins_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_user_copy(user_dir: Path, marker: dict | None) -> None:
    dest = user_dir / "text-toolbox"
    shutil.copytree(BUNDLED_TOOLBOX, dest)
    if marker is not None:
        dest.joinpath(".zentray-origin.json").write_text(
            json.dumps(marker), encoding="utf-8"
        )


def test_update_bundled_writes_origin_marker(tmp_data_dir):
    """编辑示例插件复制副本时写入 origin 标记（含复制时应用版本）。"""
    from zentray.config import VERSION

    set_api_context(ApiContext(plugin_loader=PluginLoader()))
    code, body = _update_plugin("text-toolbox", {"name": "文本工具箱改名"})
    assert code == 200, body
    marker = _user_dir(tmp_data_dir).joinpath("text-toolbox", ".zentray-origin.json")
    assert marker.is_file()
    assert json.loads(marker.read_text(encoding="utf-8")) == {
        "copied_from_bundled_version": str(VERSION)
    }


def test_loader_detects_shadow_and_stale_marker(tmp_data_dir, tmp_path):
    """同 id 用户副本遮蔽内置：无标记→仅 shadow；旧版本标记→update_available；
    同版本标记→仅 shadow。"""
    from zentray.config import VERSION

    bundled_root = tmp_path / "b"
    bundled_root.mkdir()
    shutil.copytree(BUNDLED_TOOLBOX, bundled_root / "text-toolbox")

    def scan(marker):
        user = tmp_path / "u"
        if user.exists():
            shutil.rmtree(user)
        user.mkdir()
        _make_user_copy(user, marker)
        loader = PluginLoader()
        loader.scan(bundled_dir=bundled_root, user_dir=user)
        return loader.get("text-toolbox")

    p = scan(None)
    assert p.bundled_shadow is True and p.bundled_update_available is False

    p = scan({"copied_from_bundled_version": "0.0.1"})
    assert p.bundled_shadow is True and p.bundled_update_available is True

    p = scan({"copied_from_bundled_version": str(VERSION)})
    assert p.bundled_shadow is True and p.bundled_update_available is False


def test_plugins_list_exposes_shadow_fields(tmp_data_dir):
    set_api_context(ApiContext(plugin_loader=PluginLoader()))
    _make_user_copy(_user_dir(tmp_data_dir), {"copied_from_bundled_version": "0.0.1"})
    items = {i["id"]: i for i in _plugins_list(scan_always=True)["items"]}
    assert items["text-toolbox"]["bundled_shadow"] is True
    assert items["text-toolbox"]["bundled_update_available"] is True
    assert items["text-toolbox"]["source"] == "user"


def test_yield_backs_up_and_bundled_takes_over(tmp_data_dir):
    set_api_context(ApiContext(plugin_loader=PluginLoader()))
    user_dir = _user_dir(tmp_data_dir)
    _make_user_copy(user_dir, {"copied_from_bundled_version": "0.0.1"})

    code, body = _yield_plugin_to_bundled("text-toolbox")
    assert code == 200, body
    backup = Path(body["backup"])
    assert backup.is_dir() and backup.name == "text-toolbox"
    assert "plugins-disabled" in str(backup.parent)
    assert "yielded-" in str(backup.parent.name)
    assert not (user_dir / "text-toolbox").exists()  # 原位已移走
    # 重扫后内置接管
    p = _scanned_loader().get("text-toolbox")
    assert p.source == "bundled"
    assert body["plugins"]["items"]


def test_yield_rejects_bundled_plugin(tmp_data_dir):
    set_api_context(ApiContext(plugin_loader=PluginLoader()))
    code, body = _yield_plugin_to_bundled("text-toolbox")
    assert code == 400
    assert "覆盖副本" in body["error"]
