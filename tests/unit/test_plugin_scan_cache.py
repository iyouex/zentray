"""扫描缓存：目录未变时 /api/plugins 式的新建 loader 直接命中，改动即刻失效。"""
import time
from pathlib import Path

from zentray.plugins import loader as loader_mod
from zentray.plugins.loader import PluginLoader


def _make_plugin(root: Path, pid: str, name: str):
    d = root / pid
    d.mkdir(parents=True)
    (d / "plugin.yaml").write_text(
        f"""id: {pid}
name: {name}
version: 0.1.0
type: script
api_version: 1
entry: run.sh
""",
        encoding="utf-8",
    )
    run = d / "run.sh"
    run.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    run.chmod(0o755)
    return d


def test_scan_cache_hit_and_invalidate(tmp_path, monkeypatch):
    monkeypatch.setattr(loader_mod, "_scan_cache", {"sig": None, "at": 0.0, "plugins": (), "failures": ()})
    user = tmp_path / "user"
    user.mkdir()
    _make_plugin(user, "p1", "v1")

    a = PluginLoader().scan(user_dir=user)
    assert [p.manifest.name for p in a] == ["v1"]

    # 未变：新 loader 实例命中缓存（无磁盘走查），结果一致
    b = PluginLoader().scan(user_dir=user)
    assert [p.manifest.name for p in b] == ["v1"]

    # plugin.yaml 变更：签名失配，立即可见新值
    yaml = user / "p1" / "plugin.yaml"
    yaml.write_text(yaml.read_text(encoding="utf-8").replace("v1", "v2"), encoding="utf-8")
    c = PluginLoader().scan(user_dir=user)
    assert [p.manifest.name for p in c] == ["v2"]

    # 目录删除：同样即刻反映
    import shutil

    shutil.rmtree(user / "p1")
    monkeypatch.setattr(time, "monotonic", lambda: loader_mod._scan_cache["at"] + 999)  # 越过 TTL 兜底
    d = PluginLoader().scan(user_dir=user)
    assert d == []


def test_scan_cache_ttl_expiry_forces_rescan(tmp_path, monkeypatch):
    monkeypatch.setattr(loader_mod, "_scan_cache", {"sig": None, "at": 0.0, "plugins": (), "failures": ()})
    user = tmp_path / "user"
    user.mkdir()
    _make_plugin(user, "p1", "v1")
    assert PluginLoader().scan(user_dir=user)
    # 签名相同但超时：应重新走真扫描（可通过 _scan_cache["at"] 刷新验证）
    before = loader_mod._scan_cache["at"]
    fake_now = before + loader_mod._SCAN_TTL + 1
    monkeypatch.setattr(time, "monotonic", lambda: fake_now)
    assert PluginLoader().scan(user_dir=user)
    assert loader_mod._scan_cache["at"] == fake_now
