"""示例（内置）插件的编辑（复制到用户目录）与删除（隐藏清单）。"""
from pathlib import Path

import yaml

from zentray.api.handlers import _delete_plugin, _plugins_list, _update_plugin

ROOT = Path(__file__).resolve().parents[2]


def _items() -> dict:
    return {i["id"]: i for i in _plugins_list(scan_always=True)["items"]}


def test_update_bundled_copies_to_user_dir(tmp_data_dir):
    code, body = _update_plugin(
        "ai-news-digest", {"name": "AI 资讯改名", "description": "改后描述"}
    )
    assert code == 200, body
    items = _items()
    assert items["ai-news-digest"]["source"] == "user"
    assert items["ai-news-digest"]["name"] == "AI 资讯改名"
    # 用户副本 yaml 改写、其余字段保留；包内原文件未动
    user_yaml = tmp_data_dir / "plugins" / "ai-news-digest" / "plugin.yaml"
    raw = yaml.safe_load(user_yaml.read_text(encoding="utf-8"))
    assert raw["name"] == "AI 资讯改名"
    assert raw["id"] == "ai-news-digest"
    bundled_raw = yaml.safe_load(
        (ROOT / "bundled_plugins" / "ai-news-digest" / "plugin.yaml").read_text("utf-8")
    )
    assert bundled_raw["name"] != "AI 资讯改名"


def test_update_bundled_existing_user_copy_rejected(tmp_data_dir):
    dest = tmp_data_dir / "plugins" / "ai-news-digest"
    dest.mkdir(parents=True)
    code, body = _update_plugin("ai-news-digest", {"name": "x"})
    assert code == 400
    assert "已存在" in body["error"]


def test_delete_bundled_hides_without_touching_package(tmp_data_dir):
    code, body = _delete_plugin("ai-news-digest")
    assert code == 200, body
    assert "ai-news-digest" not in _items()
    from zentray.services.settings_manager import SettingsManager

    assert "ai-news-digest" in SettingsManager().ops.hidden_bundled
    # 包内文件保留；隐藏后同 id 用户副本仍可见（覆盖语义）
    assert (ROOT / "bundled_plugins" / "ai-news-digest" / "plugin.yaml").is_file()
    _delete_plugin("text-toolbox")
    import shutil

    shutil.copytree(ROOT / "bundled_plugins" / "text-toolbox", tmp_data_dir / "plugins" / "text-toolbox")
    assert "text-toolbox" in _items()
    assert _items()["text-toolbox"]["source"] == "user"
